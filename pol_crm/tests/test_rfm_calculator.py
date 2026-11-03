"""
Unit & Integration Tests for Story 1 (Issue #2):
RFM Scoring Engine, Segment Transitions & Lifecycle Sync Tests.
"""

import unittest
from unittest.mock import MagicMock, patch
from pol_crm.tests.frappe_mock import setup_mock_frappe, reset_mock_frappe

mock_frappe = setup_mock_frappe()


import frappe
from pol_crm.rfm.rfm_calculator import (
    score_recency,
    score_frequency,
    score_monetary,
    derive_segment,
    get_rfm_settings,
    calculate_rfm_for_customer,
    on_segment_changed,
    on_sales_invoice_submit,
    on_sales_invoice_cancel,
    nightly_recalculate_all_customers_rfm,
    sync_customer_rfm_to_contacts,
    sync_contact_rfm_on_save,
    sync_deal_rfm_on_save,
    DEFAULT_RECENCY_THRESHOLDS,
    DEFAULT_FREQUENCY_THRESHOLDS,
    DEFAULT_MONETARY_THRESHOLDS,
)


class TestRFMScoring(unittest.TestCase):
    """Tests for raw score calculation against threshold boundaries."""

    def test_score_recency_defaults(self):
        th = DEFAULT_RECENCY_THRESHOLDS  # [30, 60, 90, 180]
        # Days <= 30 -> 5
        self.assertEqual(score_recency(0, th), 5)
        self.assertEqual(score_recency(15, th), 5)
        self.assertEqual(score_recency(30, th), 5)
        # 30 < Days <= 60 -> 4
        self.assertEqual(score_recency(31, th), 4)
        self.assertEqual(score_recency(60, th), 4)
        # 60 < Days <= 90 -> 3
        self.assertEqual(score_recency(61, th), 3)
        self.assertEqual(score_recency(90, th), 3)
        # 90 < Days <= 180 -> 2
        self.assertEqual(score_recency(91, th), 2)
        self.assertEqual(score_recency(180, th), 2)
        # Days > 180 -> 1
        self.assertEqual(score_recency(181, th), 1)
        self.assertEqual(score_recency(500, th), 1)

    def test_score_recency_custom_thresholds(self):
        custom_th = [7, 14, 30, 60]
        self.assertEqual(score_recency(5, custom_th), 5)
        self.assertEqual(score_recency(10, custom_th), 4)
        self.assertEqual(score_recency(20, custom_th), 3)
        self.assertEqual(score_recency(45, custom_th), 2)
        self.assertEqual(score_recency(100, custom_th), 1)

    def test_score_frequency_defaults(self):
        th = DEFAULT_FREQUENCY_THRESHOLDS  # [1, 3, 6, 12]
        # Count <= 1 -> 1
        self.assertEqual(score_frequency(0, th), 1)
        self.assertEqual(score_frequency(1, th), 1)
        # 1 < Count <= 3 -> 2
        self.assertEqual(score_frequency(2, th), 2)
        self.assertEqual(score_frequency(3, th), 2)
        # 3 < Count <= 6 -> 3
        self.assertEqual(score_frequency(4, th), 3)
        self.assertEqual(score_frequency(6, th), 3)
        # 6 < Count <= 12 -> 4
        self.assertEqual(score_frequency(7, th), 4)
        self.assertEqual(score_frequency(12, th), 4)
        # Count > 12 -> 5
        self.assertEqual(score_frequency(13, th), 5)
        self.assertEqual(score_frequency(50, th), 5)

    def test_score_frequency_custom_thresholds(self):
        custom_th = [1, 2, 4, 8]
        self.assertEqual(score_frequency(1, custom_th), 1)
        self.assertEqual(score_frequency(2, custom_th), 2)
        self.assertEqual(score_frequency(3, custom_th), 3)
        self.assertEqual(score_frequency(7, custom_th), 4)
        self.assertEqual(score_frequency(15, custom_th), 5)

    def test_score_monetary_defaults(self):
        th = DEFAULT_MONETARY_THRESHOLDS  # [1M, 3M, 8M, 20M]
        # Spend <= 1M -> 1
        self.assertEqual(score_monetary(0, th), 1)
        self.assertEqual(score_monetary(1_000_000, th), 1)
        # 1M < Spend <= 3M -> 2
        self.assertEqual(score_monetary(1_000_001, th), 2)
        self.assertEqual(score_monetary(3_000_000, th), 2)
        # 3M < Spend <= 8M -> 3
        self.assertEqual(score_monetary(3_000_001, th), 3)
        self.assertEqual(score_monetary(8_000_000, th), 3)
        # 8M < Spend <= 20M -> 4
        self.assertEqual(score_monetary(8_000_001, th), 4)
        self.assertEqual(score_monetary(20_000_000, th), 4)
        # Spend > 20M -> 5
        self.assertEqual(score_monetary(20_000_001, th), 5)
        self.assertEqual(score_monetary(100_000_000, th), 5)

    def test_score_monetary_custom_thresholds(self):
        custom_th = [500_000, 1_500_000, 5_000_000, 10_000_000]
        self.assertEqual(score_monetary(400_000, custom_th), 1)
        self.assertEqual(score_monetary(1_000_000, custom_th), 2)
        self.assertEqual(score_monetary(3_000_000, custom_th), 3)
        self.assertEqual(score_monetary(7_000_000, custom_th), 4)
        self.assertEqual(score_monetary(15_000_000, custom_th), 5)


class TestSegmentDerivationAll11Segments(unittest.TestCase):
    """
    Exhaustive verification of all 11 customer RFM segments:
    CHAMPIONS, CANT_LOSE, AT_RISK, LOYAL, POTENTIAL_LOYALIST,
    NEW_CUSTOMERS, PROMISING, NEED_ATTENTION, ABOUT_TO_SLEEP,
    HIBERNATING, and LOST.
    """

    def test_all_11_segments_derivation(self):
        cases = [
            # 1. CHAMPIONS: R >= 4, F >= 4, M >= 4
            (5, 5, 5, "CHAMPIONS"),
            (4, 4, 4, "CHAMPIONS"),
            (5, 4, 5, "CHAMPIONS"),
            (4, 5, 4, "CHAMPIONS"),

            # 2. CANT_LOSE: R <= 2, F >= 4, M >= 4
            (2, 5, 5, "CANT_LOSE"),
            (1, 4, 4, "CANT_LOSE"),
            (2, 4, 5, "CANT_LOSE"),
            (1, 5, 4, "CANT_LOSE"),

            # 3. AT_RISK: R <= 2, F >= 3, M >= 3 (not caught by CANT_LOSE)
            (2, 3, 3, "AT_RISK"),
            (1, 3, 4, "AT_RISK"),
            (2, 3, 5, "AT_RISK"),
            (1, 4, 3, "AT_RISK"),

            # 4. LOYAL: R >= 3, F >= 4 (not caught by CHAMPIONS)
            (3, 4, 2, "LOYAL"),
            (5, 4, 1, "LOYAL"),
            (3, 5, 5, "LOYAL"),
            (4, 4, 3, "LOYAL"),

            # 5. POTENTIAL_LOYALIST: R >= 3, 2 <= F <= 3, M >= 2
            (4, 2, 3, "POTENTIAL_LOYALIST"),
            (3, 3, 2, "POTENTIAL_LOYALIST"),
            (5, 2, 2, "POTENTIAL_LOYALIST"),
            (5, 3, 5, "POTENTIAL_LOYALIST"),
            (3, 2, 4, "POTENTIAL_LOYALIST"),

            # 6. NEW_CUSTOMERS: R == 5, F == 1
            (5, 1, 1, "NEW_CUSTOMERS"),
            (5, 1, 3, "NEW_CUSTOMERS"),
            (5, 1, 5, "NEW_CUSTOMERS"),

            # 7. PROMISING: R == 4, F == 1, M >= 2
            (4, 1, 2, "PROMISING"),
            (4, 1, 4, "PROMISING"),
            (4, 1, 5, "PROMISING"),

            # 8. NEED_ATTENTION: R == 3, 2 <= F <= 3 (and M < 2)
            (3, 2, 1, "NEED_ATTENTION"),
            (3, 3, 1, "NEED_ATTENTION"),

            # 9. ABOUT_TO_SLEEP: R == 2, 2 <= F <= 3 (and M < 3)
            (2, 2, 1, "ABOUT_TO_SLEEP"),
            (2, 2, 2, "ABOUT_TO_SLEEP"),
            (2, 3, 1, "ABOUT_TO_SLEEP"),
            (2, 3, 2, "ABOUT_TO_SLEEP"),

            # 10. HIBERNATING: R <= 2, F <= 2 (and not caught above)
            (1, 1, 1, "HIBERNATING"),
            (2, 1, 1, "HIBERNATING"),
            (1, 2, 2, "HIBERNATING"),
            (1, 2, 1, "HIBERNATING"),

            # 11. LOST: Fallback / catch-all
            (3, 1, 1, "LOST"),
            (4, 1, 1, "LOST"),
        ]

        seen_segments = set()
        for r, f, m, expected in cases:
            with self.subTest(r=r, f=f, m=m, expected=expected):
                result = derive_segment(r, f, m)
                self.assertEqual(result, expected, f"Failed for R={r}, F={f}, M={m}")
                seen_segments.add(result)

        # Assert all 11 unique segments were reached in this test suite
        self.assertEqual(len(seen_segments), 11, f"Missing segments: {11 - len(seen_segments)}")


class TestGetRFMSettings(unittest.TestCase):
    """Tests for configuration resolution from database or defaults."""

    def setUp(self):
        reset_mock_frappe()


    def test_get_settings_from_doctype(self):
        frappe.db.exists.side_effect = None
        frappe.db.exists.return_value = True
        mock_settings = MagicMock(
            r_threshold_1=15,
            r_threshold_2=45,
            r_threshold_3=75,
            r_threshold_4=150,
            f_threshold_1=2,
            f_threshold_2=5,
            f_threshold_3=10,
            f_threshold_4=20,
            m_threshold_1=500000,
            m_threshold_2=2000000,
            m_threshold_3=6000000,
            m_threshold_4=15000000,
        )
        frappe.get_single.return_value = mock_settings


        r, f, m = get_rfm_settings()
        self.assertEqual(r, [15, 45, 75, 150])
        self.assertEqual(f, [2, 5, 10, 20])
        self.assertEqual(m, [500000.0, 2000000.0, 6000000.0, 15000000.0])

    def test_get_settings_fallback_on_missing_doctype(self):
        frappe.db.exists.return_value = False
        r, f, m = get_rfm_settings()
        self.assertEqual(r, DEFAULT_RECENCY_THRESHOLDS)
        self.assertEqual(f, DEFAULT_FREQUENCY_THRESHOLDS)
        self.assertEqual(m, DEFAULT_MONETARY_THRESHOLDS)

    def test_get_settings_fallback_on_exception(self):
        frappe.db.exists.side_effect = Exception("DB connection timeout")
        r, f, m = get_rfm_settings()
        self.assertEqual(r, DEFAULT_RECENCY_THRESHOLDS)
        self.assertEqual(f, DEFAULT_FREQUENCY_THRESHOLDS)
        self.assertEqual(m, DEFAULT_MONETARY_THRESHOLDS)


class TestCalculateRFMForCustomer(unittest.TestCase):
    """End-to-end unit tests for customer RFM calculation and lifecycle hooks."""

    def setUp(self):
        reset_mock_frappe()


    def test_customer_does_not_exist(self):
        frappe.db.exists.side_effect = lambda dt, n=None: False
        result = calculate_rfm_for_customer("NON_EXISTENT")
        self.assertIsNone(result)

    def test_customer_with_zero_invoices_edge_case(self):
        """Edge case: Customer exists but has no submitted sales invoices."""
        frappe.db.exists.side_effect = lambda dt, n=None: True if dt == "Customer" else False
        frappe.db.sql.return_value = []  # No invoices


        with patch("pol_crm.rfm.rfm_calculator.sync_customer_rfm_to_contacts") as mock_sync:
            result = calculate_rfm_for_customer("CUST-NO-INVOICE")

            self.assertIsNotNone(result)
            self.assertEqual(result["custom_rfm_recency_score"], 1)
            self.assertEqual(result["custom_rfm_frequency_score"], 1)
            self.assertEqual(result["custom_rfm_monetary_score"], 1)
            self.assertEqual(result["custom_rfm_composite_score"], "111")
            self.assertIsNone(result["custom_rfm_segment"])
            self.assertEqual(result["custom_total_spent"], 0.0)
            self.assertEqual(result["custom_paid_invoices_count"], 0)

            # Assert database was updated
            frappe.db.set_value.assert_called_once_with(
                "Customer", "CUST-NO-INVOICE", result, update_modified=False
            )
            mock_sync.assert_called_once_with("CUST-NO-INVOICE", None)

    def test_customer_with_single_invoice(self):
        frappe.db.exists.side_effect = lambda dt, n=None: True if dt == "Customer" else False

        # 1 invoice, 5 days ago, 5,000,000 IRR
        mock_inv = MagicMock(posting_date="2026-10-13", grand_total=5000000.0)
        frappe.db.sql.return_value = [mock_inv]
        frappe.db.get_value.return_value = None  # No old segment


        with patch("pol_crm.rfm.rfm_calculator.nowdate", return_value="2026-10-18"), \
             patch("pol_crm.rfm.rfm_calculator.sync_customer_rfm_to_contacts") as mock_sync, \
             patch("pol_crm.rfm.rfm_calculator.on_segment_changed") as mock_on_change:

            result = calculate_rfm_for_customer("CUST-SINGLE")

            self.assertIsNotNone(result)
            # Days diff = 5 <= 30 -> R=5
            self.assertEqual(result["custom_rfm_recency_score"], 5)
            # Count = 1 <= 1 -> F=1
            self.assertEqual(result["custom_rfm_frequency_score"], 1)
            # Spend = 5M (3M < spend <= 8M) -> M=3
            self.assertEqual(result["custom_rfm_monetary_score"], 3)
            self.assertEqual(result["custom_rfm_composite_score"], "513")
            # R=5, F=1 -> NEW_CUSTOMERS
            self.assertEqual(result["custom_rfm_segment"], "NEW_CUSTOMERS")
            self.assertEqual(result["custom_paid_invoices_count"], 1)
            self.assertEqual(result["custom_total_spent"], 5000000.0)

            mock_sync.assert_called_once_with("CUST-SINGLE", "NEW_CUSTOMERS")
            mock_on_change.assert_not_called()

    def test_customer_with_multiple_invoices_and_segment_transition(self):
        frappe.db.exists.side_effect = lambda dt, n=None: True if dt == "Customer" else False
        # 15 invoices, grand total = 25,000,000 IRR, last purchase 10 days ago
        invoices = [MagicMock(posting_date="2026-10-08", grand_total=2000000.0)] * 15
        frappe.db.sql.return_value = invoices
        # Previous segment was NEW_CUSTOMERS
        frappe.db.get_value.return_value = "NEW_CUSTOMERS"

        with patch("pol_crm.rfm.rfm_calculator.nowdate", return_value="2026-10-18"), \
             patch("pol_crm.rfm.rfm_calculator.on_segment_changed") as mock_on_change:

            result = calculate_rfm_for_customer("CUST-CHAMP")

            # 10 days ago -> R=5
            # 15 invoices -> F=5
            # 30,000,000 -> M=5
            # R=5, F=5, M=5 -> CHAMPIONS
            self.assertEqual(result["custom_rfm_segment"], "CHAMPIONS")
            self.assertEqual(result["custom_paid_invoices_count"], 15)
            self.assertEqual(result["custom_total_spent"], 30000000.0)

            # Old segment was NEW_CUSTOMERS, changed to CHAMPIONS
            mock_on_change.assert_called_once_with("CUST-CHAMP", "NEW_CUSTOMERS", "CHAMPIONS")

    def test_customer_with_return_invoice_credit_note(self):
        """Verifies credit note/return invoice (is_return=1) does NOT increment purchase count and deducts from spend."""
        frappe.db.exists.side_effect = lambda dt, n=None: True if dt == "Customer" else False
        
        # 1 valid purchase on Oct 10 (10M), 1 return on Oct 16 (-3M)
        inv_purchase = {"posting_date": "2026-10-10", "grand_total": 10000000.0, "is_return": 0}
        inv_return = {"posting_date": "2026-10-16", "grand_total": -3000000.0, "is_return": 1}
        frappe.db.sql.return_value = [inv_return, inv_purchase]  # Ordered DESC by posting_date
        frappe.db.get_value.return_value = None

        with patch("pol_crm.rfm.rfm_calculator.nowdate", return_value="2026-10-18"):
            result = calculate_rfm_for_customer("CUST-RETURN-1")

            self.assertIsNotNone(result)
            # Purchase count must be 1 (NOT 2)
            self.assertEqual(result["custom_paid_invoices_count"], 1)
            # Total spent must be 10M - 3M = 7M
            self.assertEqual(result["custom_total_spent"], 7000000.0)
            # Last purchase date must be the purchase date (2026-10-10), NOT the return date (2026-10-16)
            self.assertEqual(result["custom_last_purchase_date"], "2026-10-10")
            # Days diff = 8 days -> R=5
            self.assertEqual(result["custom_rfm_recency_score"], 5)
            # Count = 1 -> F=1
            self.assertEqual(result["custom_rfm_frequency_score"], 1)
            # Spend = 7M (3M < spend <= 8M) -> M=3
            self.assertEqual(result["custom_rfm_monetary_score"], 3)
            # R=5, F=1 -> NEW_CUSTOMERS
            self.assertEqual(result["custom_rfm_segment"], "NEW_CUSTOMERS")

    def test_customer_with_only_returns(self):
        """Customer with only return invoices should be treated as having 0 valid purchases."""
        frappe.db.exists.side_effect = lambda dt, n=None: True if dt == "Customer" else False
        inv_return = {"posting_date": "2026-10-16", "grand_total": -2000000.0, "is_return": 1}
        frappe.db.sql.return_value = [inv_return]

        result = calculate_rfm_for_customer("CUST-ONLY-RETURN")
        self.assertIsNotNone(result)
        self.assertEqual(result["custom_paid_invoices_count"], 0)
        self.assertEqual(result["custom_total_spent"], 0.0)
        self.assertIsNone(result["custom_rfm_segment"])
        self.assertEqual(result["custom_rfm_composite_score"], "111")

    def test_calculate_rfm_bulk_customers(self):
        """Test calculating RFM for multiple customers at once."""
        res_list = calculate_rfm_for_customer(customer_names=["NON_EXISTENT_1", "NON_EXISTENT_2"])
        self.assertIn("NON_EXISTENT_1", res_list)
        self.assertIn("NON_EXISTENT_2", res_list)

        # Also test JSON-stringified customer_names
        import json
        res_json = calculate_rfm_for_customer(customer_names=json.dumps(["NON_EXISTENT_1"]))
        self.assertIn("NON_EXISTENT_1", res_json)


    def test_on_segment_changed_hook_dispatch(self):
        """Test that segment transition triggers the marketing automation runner."""
        with patch("pol_crm.marketing_automation.runner.trigger_segment_change_automations") as mock_runner:
            on_segment_changed("CUST-100", "POTENTIAL_LOYALIST", "CHAMPIONS")
            mock_runner.assert_called_once_with("CUST-100", "POTENTIAL_LOYALIST", "CHAMPIONS")

    def test_on_segment_changed_hook_handles_runner_exception(self):
        """Test resilience if marketing automation runner throws an exception."""
        with patch("pol_crm.marketing_automation.runner.trigger_segment_change_automations", side_effect=RuntimeError("Runner failed")):
            # Should not raise exception
            on_segment_changed("CUST-100", "POTENTIAL_LOYALIST", "CHAMPIONS")
            frappe.logger().error.assert_called()


class TestSalesInvoiceHooks(unittest.TestCase):
    """Tests for Sales Invoice on_submit and on_cancel lifecycle hooks."""

    @patch("pol_crm.rfm.rfm_calculator.calculate_rfm_for_customer")
    def test_on_sales_invoice_submit_triggers_recalculation(self, mock_calc):
        doc = MagicMock(customer="CUST-HOOK-1")
        on_sales_invoice_submit(doc, "on_submit")
        mock_calc.assert_called_once_with("CUST-HOOK-1")

    @patch("pol_crm.rfm.rfm_calculator.calculate_rfm_for_customer")
    def test_on_sales_invoice_submit_skips_when_no_customer(self, mock_calc):
        doc = MagicMock(customer=None)
        on_sales_invoice_submit(doc, "on_submit")
        mock_calc.assert_not_called()

    @patch("pol_crm.rfm.rfm_calculator.calculate_rfm_for_customer")
    def test_on_sales_invoice_cancel_triggers_recalculation(self, mock_calc):
        doc = MagicMock(customer="CUST-HOOK-2")
        on_sales_invoice_cancel(doc, "on_cancel")
        mock_calc.assert_called_once_with("CUST-HOOK-2")

    @patch("pol_crm.rfm.rfm_calculator.calculate_rfm_for_customer")
    def test_on_sales_invoice_cancel_skips_when_no_customer(self, mock_calc):
        doc = MagicMock(customer="")
        on_sales_invoice_cancel(doc, "on_cancel")
        mock_calc.assert_not_called()


class TestNightlyBatchRecalculation(unittest.TestCase):
    """Tests for nightly scheduled batch recalculation."""

    @patch("pol_crm.rfm.rfm_calculator.calculate_rfm_for_customer")
    def test_nightly_recalculate_all_customers_resilience(self, mock_calc):
        frappe.db.sql.return_value = [
            MagicMock(customer="CUST-1"),
            MagicMock(customer="CUST-2"),
            MagicMock(customer="CUST-3"),
        ]

        # Make CUST-2 raise an exception
        def side_effect(cust):
            if cust == "CUST-2":
                raise ValueError("Database lock error")
            return {}

        mock_calc.side_effect = side_effect

        # Should continue processing CUST-3 despite CUST-2 failure
        nightly_recalculate_all_customers_rfm()

        self.assertEqual(mock_calc.call_count, 3)
        frappe.logger().error.assert_called()

    @patch("pol_crm.rfm.rfm_calculator.recalculate_all_customers_rfm", return_value={"status": "success", "scored_customers": 50})
    def test_nightly_recalculate_bulk_sql_dispatch(self, mock_bulk):
        """When use_bulk_sql=True, nightly recalculate invokes high-speed bulk SQL instead of Python loop."""
        res = nightly_recalculate_all_customers_rfm(use_bulk_sql=True)
        self.assertEqual(res, {"status": "success", "scored_customers": 50})
        mock_bulk.assert_called_once()


class TestContactAndDealSync(unittest.TestCase):
    """Tests for propagating customer RFM segments to Contacts and Deals."""

    def setUp(self):
        reset_mock_frappe()


    def test_sync_customer_rfm_to_contacts(self):
        frappe.get_all.return_value = ["CON-001", "CON-002"]

        sync_customer_rfm_to_contacts("CUST-10", "CHAMPIONS")

        frappe.get_all.assert_called_once_with(
            "Dynamic Link",
            filters={"link_doctype": "Customer", "link_name": "CUST-10", "parenttype": "Contact"},
            pluck="parent",
        )
        frappe.db.set_value.assert_called_once_with(
            "Contact",
            {"name": ["in", ["CON-001", "CON-002"]]},
            "custom_rfm_segment",
            "CHAMPIONS",
            update_modified=False,
        )

    def test_sync_customer_rfm_to_contacts_empty(self):
        frappe.get_all.return_value = []
        sync_customer_rfm_to_contacts("CUST-10", "CHAMPIONS")
        frappe.db.set_value.assert_not_called()

    def test_sync_contact_rfm_on_save(self):
        mock_link = MagicMock(link_doctype="Customer", link_name="CUST-20")
        doc = MagicMock(links=[mock_link], custom_rfm_segment=None)
        frappe.db.get_value.return_value = "AT_RISK"

        sync_contact_rfm_on_save(doc)

        frappe.db.get_value.assert_called_once_with("Customer", "CUST-20", "custom_rfm_segment")
        self.assertEqual(doc.custom_rfm_segment, "AT_RISK")

    def test_sync_contact_rfm_on_save_no_links(self):
        doc = MagicMock(links=[])
        sync_contact_rfm_on_save(doc)
        frappe.db.get_value.assert_not_called()

    def test_sync_deal_rfm_on_save(self):
        doc = MagicMock(contact="CON-30", organization=None, custom_rfm_segment=None)
        frappe.db.get_value.return_value = "LOYAL"

        sync_deal_rfm_on_save(doc)

        frappe.db.get_value.assert_called_once_with("Contact", "CON-30", "custom_rfm_segment")
        self.assertEqual(doc.custom_rfm_segment, "LOYAL")


if __name__ == "__main__":
    unittest.main()
