"""
Tests for POL CRM - RFM Security, Access Control, and Persistent Background Job Tracking.
Verifies server-side authorization enforcement, duplicate job prevention, and status recovery.
"""

import unittest
from unittest.mock import patch, MagicMock
from pol_crm.tests.frappe_mock import setup_mock_frappe, reset_mock_frappe

mock_frappe = setup_mock_frappe()

from pol_crm.rfm.rfm_calculator import (
    recalculate_all_customers_rfm,
    calculate_rfm_for_customer,
    get_rfm_job_status,
    reset_rfm_job_lock,
    enqueue_rfm_calculation_job,
    execute_background_rfm_job,
)
from pol_crm.rfm import job_tracker


class TestRFMSecurityAndPermissions(unittest.TestCase):
    def setUp(self):
        reset_mock_frappe()
        mock_frappe.flags.in_test = False
        mock_frappe.session = MagicMock()
        mock_frappe.session.user = "sales_rep@example.com"
        mock_frappe.PermissionError = Exception

    def tearDown(self):
        mock_frappe.flags.in_test = True

    def test_recalculate_all_forbidden_for_non_system_manager(self):
        """recalculate_all_customers_rfm throws PermissionError when invoked by non-System Manager."""
        mock_frappe.only_for.side_effect = mock_frappe.PermissionError("Not authorized")

        with self.assertRaises(mock_frappe.PermissionError):
            recalculate_all_customers_rfm()

        mock_frappe.only_for.assert_called_with("System Manager")

    def test_recalculate_all_allowed_for_system_manager(self):
        """recalculate_all_customers_rfm succeeds when caller has System Manager role."""
        mock_frappe.only_for.return_value = None
        mock_frappe.session.user = "sysman@example.com"
        mock_frappe.db.count.return_value = 100

        with patch("pol_crm.rfm.rfm_calculator._execute_bulk_sql_rfm_calculation", return_value={"status": "success"}):
            res = recalculate_all_customers_rfm(async_run=False)
            self.assertEqual(res.get("status"), "success")

    def test_calculate_single_customer_requires_customer_write_permission(self):
        """calculate_rfm_for_customer rejects users without Customer write permission."""
        mock_frappe.has_permission.return_value = False
        mock_frappe.throw = MagicMock(side_effect=mock_frappe.PermissionError("Permission Denied"))

        with self.assertRaises(mock_frappe.PermissionError):
            calculate_rfm_for_customer("CUST-001")

        mock_frappe.has_permission.assert_called_with("Customer", "write")

    def test_sync_custom_fields_requires_system_manager(self):
        """sync_custom_fields enforces System Manager permission when invoked via web request."""
        from pol_crm.rfm.rfm_calculator import sync_custom_fields
        mock_frappe.only_for.side_effect = mock_frappe.PermissionError("Not authorized")

        with self.assertRaises(mock_frappe.PermissionError):
            sync_custom_fields()

        mock_frappe.only_for.assert_called_with("System Manager")


class TestJobTrackerAndIdempotency(unittest.TestCase):
    def setUp(self):
        reset_mock_frappe()
        self.mock_singles = {}

        def mock_sql(*args, **kwargs):
            if not args:
                return []
            query = args[0]
            params = args[1] if len(args) > 1 else kwargs.get("values")
            q = query.strip().upper()

            if "SELECT FIELD, VALUE" in q:
                return [{"field": k, "value": v} for k, v in self.mock_singles.items()]
            elif "SELECT 1 FROM `TABSINGLES`" in q:
                field = params[1] if params else None
                return [[1]] if field in self.mock_singles else []
            elif "INSERT INTO `TABSINGLES`" in q:
                field = params[1]
                val = params[2]
                self.mock_singles[field] = val
                return []
            elif "UPDATE `TABSINGLES`" in q:
                val = params[0]
                field = params[2]
                self.mock_singles[field] = val
                return []
            return []

        mock_frappe.db.sql.side_effect = mock_sql

    def test_job_lock_acquisition_and_duplicate_prevention(self):
        """Lock prevents concurrent duplicate job execution."""
        # Acquire first lock
        acquired, status = job_tracker.acquire_job_lock("job-1", "ALL", "Administrator", 1000)
        self.assertTrue(acquired)
        self.assertEqual(status["status"], "IN_PROGRESS")
        self.assertEqual(status["job_id"], "job-1")

        # Second attempt should be denied
        acquired2, status2 = job_tracker.acquire_job_lock("job-2", "ALL", "SalesUser", 1000)
        self.assertFalse(acquired2)
        self.assertEqual(status2["status"], "IN_PROGRESS")
        self.assertEqual(status2["job_id"], "job-1")

    def test_job_progress_and_completion(self):
        """Progress updates and completion status persist correctly."""
        job_tracker.acquire_job_lock("job-10", "SELECTED", "Administrator", 50)
        
        # Update progress to 50%
        status = job_tracker.update_job_progress("job-10", progress_percent=50, processed_records=25, scored_customers=20)
        self.assertEqual(status["progress_percent"], 50)
        self.assertEqual(status["processed_records"], 25)

        # Complete job
        final_status = job_tracker.complete_job("job-10", status="SUCCESS", scored_customers=48, total_customers=50)
        self.assertEqual(final_status["status"], "SUCCESS")
        self.assertEqual(final_status["progress_percent"], 100)
        self.assertEqual(final_status["scored_customers"], 48)

    def test_job_status_recovery_after_refresh(self):
        """get_job_status retrieves exact state simulating page refresh."""
        job_tracker.acquire_job_lock("job-99", "ALL", "Manager", 39000)
        job_tracker.update_job_progress("job-99", 65, 25000, 1800)

        # Simulate fresh client call after refresh
        recovered = job_tracker.get_job_status()
        self.assertEqual(recovered["job_id"], "job-99")
        self.assertEqual(recovered["status"], "IN_PROGRESS")
        self.assertEqual(recovered["progress_percent"], 65)
        self.assertEqual(recovered["total_records"], 39000)

    def test_job_lock_reset(self):
        """Resetting lock returns state to IDLE."""
        job_tracker.acquire_job_lock("job-stuck", "ALL", "Admin", 100)
        status = job_tracker.clear_job_lock()
        self.assertEqual(status["status"], "IDLE")

        # Can now acquire a new lock
        acquired, _ = job_tracker.acquire_job_lock("job-new", "ALL", "Admin", 100)
        self.assertTrue(acquired)


class TestRolePermissionMatrix(unittest.TestCase):
    def test_doctype_permissions_json(self):
        """Verify role permissions in DocType JSON schemas."""
        import json
        import glob
        import os

        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        doctypes_to_check = {
            "Mkt Scenario": {"Marketing Manager": ["read", "write", "create", "delete"], "Sales User": ["read"]},
            "Loyalty Offer": {"Marketing Manager": ["read", "write", "create"], "Sales User": ["read", "create"]},
            "Mkt Message Log": {"Marketing Manager": ["read", "export"], "Sales User": ["read"]},
            "RFM Settings": {"Marketing Manager": ["read"]},
            "Messaging Settings": {"Marketing Manager": ["read"]},
        }

        for path in glob.glob(f"{base_dir}/**/doctype/*/*.json", recursive=True):
            with open(path) as f:
                data = json.load(f)
            dt_name = data.get("name")
            if dt_name in doctypes_to_check:
                expected_roles = doctypes_to_check[dt_name]
                perms_by_role = {}
                for perm in data.get("permissions", []):
                    role = perm.get("role")
                    rights = [k for k in ["read", "write", "create", "delete", "export"] if perm.get(k)]
                    perms_by_role[role] = rights

                for role, expected_rights in expected_roles.items():
                    self.assertIn(role, perms_by_role, f"Role {role} missing in {dt_name}")
                    for right in expected_rights:
                        self.assertIn(right, perms_by_role[role], f"Right {right} missing for {role} in {dt_name}")


if __name__ == "__main__":
    unittest.main()
