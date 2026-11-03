"""
Unit & Integration Tests for Story 3 (Issue #4):
Offer Decision Engine, Dynamic Coupon Generation & Cooldown Throttling Tests.
"""

import re
import unittest
from unittest.mock import MagicMock, patch

from pol_crm.tests.frappe_mock import setup_mock_frappe, reset_mock_frappe

mock_frappe = setup_mock_frappe()

import frappe
from pol_crm.rfm.offer_engine import (
    generate_coupon_code,
    customer_has_recent_offer,
    get_or_create_loyalty_pricing_rule,
    create_erpnext_coupon,
    provision_offer,
    evaluate_customer_for_offers,
    daily_offer_decision_pass,
    DEFAULT_OFFER_RULES,
)


class TestCouponCodeGenerator(unittest.TestCase):
    """Tests for dynamic unambiguous coupon code generation."""

    def test_default_prefix_and_format(self):
        code = generate_coupon_code()
        # Format: POL-XXXXXX (where X is 6 chars)
        self.assertTrue(re.match(r"^POL-[A-Z0-9]{6}$", code), f"Invalid code format: {code}")

    def test_custom_prefix(self):
        code = generate_coupon_code("SECO")
        self.assertTrue(re.match(r"^SECO-[A-Z0-9]{6}$", code), f"Invalid code format: {code}")

    def test_unambiguous_character_set(self):
        """
        Verify that ambiguous characters (0, O, 1, I) are NEVER generated
        to prevent customer confusion when typing promo codes.
        """
        disallowed = set("0O1I")
        for _ in range(100):
            code = generate_coupon_code()
            random_part = code.split("-")[1]
            self.assertEqual(len(random_part), 6)
            for ch in random_part:
                self.assertNotIn(ch, disallowed, f"Ambiguous character '{ch}' found in {code}")

    def test_uniqueness(self):
        codes = {generate_coupon_code() for _ in range(200)}
        self.assertEqual(len(codes), 200, "Collision detected in coupon code generation")


class TestCustomerHasRecentOffer(unittest.TestCase):
    """Tests for offer frequency history and cooldown detection."""

    def setUp(self):
        reset_mock_frappe()

    def test_loyalty_offer_doctype_does_not_exist(self):
        frappe.db.exists.side_effect = None
        frappe.db.exists.return_value = False
        res = customer_has_recent_offer("CUST-1", "SECOND_ORDER", 60)
        self.assertFalse(res)

    def test_once_per_lifetime_check(self):
        frappe.db.exists.side_effect = lambda dt, n=None: True if dt in ("DocType", "Loyalty Offer") else False
        res = customer_has_recent_offer("CUST-1", "SECOND_ORDER", 60, once_per_lifetime=True)
        self.assertTrue(res)

    def test_once_per_lifetime_not_found(self):
        # DocType exists, but Loyalty Offer record does not exist
        frappe.db.exists.side_effect = lambda dt, n=None: True if dt == "DocType" else None
        res = customer_has_recent_offer("CUST-1", "SECOND_ORDER", 60, once_per_lifetime=True)
        self.assertFalse(res)

    def test_cooldown_active(self):
        frappe.db.exists.side_effect = lambda dt, n=None: True if dt == "DocType" else False
        frappe.db.sql.return_value = [{"name": "OFFER-001"}]  # Recent offer found

        res = customer_has_recent_offer("CUST-1", "AT_RISK", 30, once_per_lifetime=False)
        self.assertTrue(res)

    def test_cooldown_expired(self):
        frappe.db.exists.side_effect = lambda dt, n=None: True if dt == "DocType" else False
        frappe.db.sql.return_value = []  # No offer in cooldown window

        res = customer_has_recent_offer("CUST-1", "AT_RISK", 30, once_per_lifetime=False)
        self.assertFalse(res)


class TestERPNextCouponIntegration(unittest.TestCase):
    """Tests for integration with native ERPNext Coupon Code and Pricing Rule."""

    def setUp(self):
        reset_mock_frappe()

    def test_get_or_create_pricing_rule_existing(self):
        """When an existing Pricing Rule exists in DB, it should be reused."""
        frappe.db.exists.side_effect = lambda dt, n=None: True if dt in ["DocType", "Pricing Rule"] else False
        frappe.db.get_value.return_value = "PR-EXISTING-15"

        rule_name = get_or_create_loyalty_pricing_rule(15)
        self.assertEqual(rule_name, "PR-EXISTING-15")

    def test_get_or_create_pricing_rule_creates_new(self):
        """When no rule exists, it auto-creates a new transaction-level Pricing Rule."""
        frappe.db.exists.side_effect = lambda dt, n=None: True if dt == "DocType" else False
        frappe.db.get_value.return_value = None
        mock_rule = MagicMock()
        mock_rule.name = "POL Loyalty 20% Discount"
        frappe.get_doc.return_value = mock_rule

        rule_name = get_or_create_loyalty_pricing_rule(20)
        self.assertEqual(rule_name, "POL Loyalty 20% Discount")
        frappe.get_doc.assert_called_once()
        args = frappe.get_doc.call_args[0][0]
        self.assertEqual(args["doctype"], "Pricing Rule")
        self.assertEqual(args["discount_percentage"], 20.0)
        self.assertEqual(args["coupon_code_based"], 1)
        mock_rule.insert.assert_called_once_with(ignore_permissions=True)

    def test_create_erpnext_coupon_attaches_pricing_rule(self):
        """create_erpnext_coupon automatically attaches resolved Pricing Rule to Coupon Code."""
        frappe.db.exists.side_effect = lambda dt, n=None: True if dt in ["DocType", "Coupon Code", "Pricing Rule"] else False
        frappe.db.get_value.return_value = "POL Loyalty 15% Discount"

        mock_coupon = MagicMock()
        created_docs = []

        def mock_get_doc_capture(d):
            created_docs.append(d)
            return mock_coupon

        frappe.get_doc.side_effect = mock_get_doc_capture

        res = create_erpnext_coupon("POL-XYZ123", "CUST-1", 15, "2026-10-25")
        self.assertTrue(res)
        mock_coupon.insert.assert_called_once_with(ignore_permissions=True)
        self.assertEqual(len(created_docs), 1)
        self.assertEqual(created_docs[0]["pricing_rule"], "POL Loyalty 15% Discount")
        self.assertEqual(created_docs[0]["coupon_code"], "POL-XYZ123")

    def test_create_erpnext_coupon_with_explicit_pricing_rule(self):
        """create_erpnext_coupon accepts an explicit pricing_rule argument."""
        frappe.db.exists.side_effect = lambda dt, n=None: True if dt in ["DocType", "Coupon Code"] else False
        mock_coupon = MagicMock()
        created_docs = []

        def mock_get_doc_capture(d):
            created_docs.append(d)
            return mock_coupon

        frappe.get_doc.side_effect = mock_get_doc_capture

        res = create_erpnext_coupon("POL-EXPLICIT", "CUST-1", 10, "2026-10-25", pricing_rule="PR-CUSTOM-RULE")
        self.assertTrue(res)
        self.assertEqual(created_docs[0]["pricing_rule"], "PR-CUSTOM-RULE")

    def test_create_erpnext_coupon_missing_doctype(self):
        frappe.db.exists.side_effect = None
        frappe.db.exists.return_value = False

        res = create_erpnext_coupon("POL-XYZ123", "CUST-1", 15, "2026-10-25")
        self.assertFalse(res)

    def test_create_erpnext_coupon_handles_exception(self):
        frappe.db.exists.side_effect = None
        frappe.db.exists.return_value = True
        frappe.get_doc.side_effect = Exception("Validation failed")

        res = create_erpnext_coupon("POL-XYZ123", "CUST-1", 15, "2026-10-25")
        self.assertFalse(res)
        frappe.logger().warning.assert_called()


class TestProvisionOffer(unittest.TestCase):
    """Tests for offer provisioning, document creation, and notification trigger."""

    def setUp(self):
        reset_mock_frappe()

    @patch("pol_crm.rfm.offer_engine.create_erpnext_coupon")
    @patch("pol_crm.messaging.policy.send_marketing_message")
    def test_provision_offer_flow(self, mock_send_mkt, mock_erp_coupon):
        frappe.db.exists.side_effect = None
        frappe.db.exists.return_value = True

        mock_offer_doc = MagicMock()
        mock_customer_doc = MagicMock(customer_name="احمد رضایی", mobile_no="09121234567", phone=None)

        def mock_get_doc_dispatch(doctype_or_data, name=None):
            if isinstance(doctype_or_data, dict):
                return mock_offer_doc
            if doctype_or_data == "Customer":
                return mock_customer_doc
            return MagicMock()

        frappe.get_doc.side_effect = mock_get_doc_dispatch

        rule = {
            "reason": "SECOND_ORDER",
            "offer_type": "DISCOUNT_CODE",
            "percentage_value": 15,
            "validity_days": 7,
        }

        code = provision_offer("CUST-1", rule)

        self.assertTrue(code.startswith("SECO-"))
        mock_erp_coupon.assert_called_once()
        mock_offer_doc.insert.assert_called_once_with(ignore_permissions=True)
        frappe.db.commit.assert_called_once()
        mock_send_mkt.assert_called_once()


class TestEvaluateCustomerForOffers(unittest.TestCase):
    """
    Tests evaluation of customers against all business rules:
    SECOND_ORDER, AT_RISK, POTENTIAL_LOYALIST, CANT_LOSE,
    cooldown enforcement, lifetime limits, and opt-outs.
    """

    def setUp(self):
        reset_mock_frappe()

    def test_opted_out_customer_is_skipped(self):
        cust = MagicMock()
        cust.get.side_effect = lambda k: 1 if k == "custom_mkt_opted_out_all" else None

        res = evaluate_customer_for_offers(cust)
        self.assertIsNone(res)

    @patch("pol_crm.rfm.offer_engine.provision_offer", return_value="SECO-ABCDEF")
    @patch("pol_crm.rfm.offer_engine.customer_has_recent_offer", return_value=False)
    def test_second_order_rule_match(self, mock_has_offer, mock_provision):
        """Customer with exactly 1 invoice purchased 25 days ago matches SECOND_ORDER."""
        cust = MagicMock(name="CUST-1")
        cust.name = "CUST-1"
        data = {
            "custom_paid_invoices_count": 1,
            "custom_days_since_last_purchase": 25,
            "custom_rfm_segment": "NEW_CUSTOMERS",
        }
        cust.get.side_effect = lambda k: data.get(k)

        res = evaluate_customer_for_offers(cust)
        self.assertEqual(res, "SECO-ABCDEF")
        mock_provision.assert_called_once()
        # Verify passed rule reason is SECOND_ORDER
        rule_arg = mock_provision.call_args[0][1]
        self.assertEqual(rule_arg["reason"], "SECOND_ORDER")

    @patch("pol_crm.rfm.offer_engine.provision_offer")
    @patch("pol_crm.rfm.offer_engine.customer_has_recent_offer", return_value=False)
    def test_second_order_rule_mismatch_invoice_count(self, mock_has_offer, mock_provision):
        """Customer with 2 invoices should NOT match SECOND_ORDER rule."""
        cust = MagicMock()
        data = {
            "custom_paid_invoices_count": 2,  # > 1
            "custom_days_since_last_purchase": 25,
            "custom_rfm_segment": "NEW_CUSTOMERS",
        }
        cust.get.side_effect = lambda k: data.get(k)

        res = evaluate_customer_for_offers(cust)
        self.assertIsNone(res)
        mock_provision.assert_not_called()

    @patch("pol_crm.rfm.offer_engine.provision_offer")
    @patch("pol_crm.rfm.offer_engine.customer_has_recent_offer", return_value=False)
    def test_second_order_rule_mismatch_days_outside_range(self, mock_has_offer, mock_provision):
        """Customer with 1 invoice but only 10 days since purchase (min is 15)."""
        cust = MagicMock()
        data = {
            "custom_paid_invoices_count": 1,
            "custom_days_since_last_purchase": 10,  # < 15
            "custom_rfm_segment": "NEW_CUSTOMERS",
        }
        cust.get.side_effect = lambda k: data.get(k)

        res = evaluate_customer_for_offers(cust)
        self.assertIsNone(res)

    @patch("pol_crm.rfm.offer_engine.provision_offer", return_value="AT_R-XYZ999")
    @patch("pol_crm.rfm.offer_engine.customer_has_recent_offer", return_value=False)
    def test_at_risk_segment_rule_match(self, mock_has_offer, mock_provision):
        """Customer in AT_RISK segment with 60 days since purchase."""
        cust = MagicMock(name="CUST-RISK")
        cust.name = "CUST-RISK"
        data = {
            "custom_paid_invoices_count": 5,
            "custom_days_since_last_purchase": 60,
            "custom_rfm_segment": "AT_RISK",
        }
        cust.get.side_effect = lambda k: data.get(k)

        res = evaluate_customer_for_offers(cust)
        self.assertEqual(res, "AT_R-XYZ999")
        rule_arg = mock_provision.call_args[0][1]
        self.assertEqual(rule_arg["reason"], "AT_RISK")

    @patch("pol_crm.rfm.offer_engine.provision_offer", return_value="CANT-123456")
    @patch("pol_crm.rfm.offer_engine.customer_has_recent_offer", return_value=False)
    def test_cant_lose_segment_rule_match(self, mock_has_offer, mock_provision):
        """Customer in CANT_LOSE segment with 90 days since purchase."""
        cust = MagicMock(name="CUST-CANT")
        cust.name = "CUST-CANT"
        data = {
            "custom_paid_invoices_count": 10,
            "custom_days_since_last_purchase": 90,
            "custom_rfm_segment": "CANT_LOSE",
        }
        cust.get.side_effect = lambda k: data.get(k)

        res = evaluate_customer_for_offers(cust)
        self.assertEqual(res, "CANT-123456")
        rule_arg = mock_provision.call_args[0][1]
        self.assertEqual(rule_arg["reason"], "CANT_LOSE")

    @patch("pol_crm.rfm.offer_engine.provision_offer")
    @patch("pol_crm.rfm.offer_engine.customer_has_recent_offer", return_value=True)
    def test_cooldown_prevents_duplicate_offer(self, mock_has_offer, mock_provision):
        """Customer matches AT_RISK rule but has received offer within cooldown window."""
        cust = MagicMock()
        data = {
            "custom_paid_invoices_count": 5,
            "custom_days_since_last_purchase": 60,
            "custom_rfm_segment": "AT_RISK",
        }
        cust.get.side_effect = lambda k: data.get(k)

        res = evaluate_customer_for_offers(cust)
        self.assertIsNone(res)
        mock_provision.assert_not_called()


class TestDailyOfferDecisionPass(unittest.TestCase):
    """Tests for nightly scheduled offer decision scan."""

    def setUp(self):
        reset_mock_frappe()

    @patch("pol_crm.rfm.offer_engine.evaluate_customer_for_offers")
    def test_daily_pass_executes_for_all_active_customers(self, mock_evaluate):
        cust1 = MagicMock(name="CUST-1")
        cust2 = MagicMock(name="CUST-2")
        frappe.get_all.return_value = [cust1, cust2]

        mock_evaluate.side_effect = ["CODE-1", None]

        daily_offer_decision_pass()

        frappe.get_all.assert_called_once_with(
            "Customer",
            fields=[
                "name",
                "customer_name",
                "mobile_no",
                "phone",
                "custom_rfm_segment",
                "custom_days_since_last_purchase",
                "custom_paid_invoices_count",
                "custom_mkt_opted_out_all",
                "custom_mkt_sms_opted_out",
            ],
            filters={"disabled": 0},
            order_by="name asc",
            limit_start=0,
            limit_page_length=1000,
        )
        self.assertEqual(mock_evaluate.call_count, 2)
        frappe.logger().info.assert_called()

    @patch("pol_crm.rfm.offer_engine.evaluate_customer_for_offers", return_value=None)
    def test_daily_pass_batch_chunking_pagination(self, mock_evaluate):
        """Tests that chunking iterates across multiple pages until records exhaust."""
        # 2 batches of size 2, then empty list
        batch1 = [MagicMock(name="C1"), MagicMock(name="C2")]
        batch2 = [MagicMock(name="C3"), MagicMock(name="C4")]
        frappe.get_all.side_effect = [batch1, batch2, []]

        daily_offer_decision_pass(batch_size=2)

        self.assertEqual(frappe.get_all.call_count, 3)
        self.assertEqual(mock_evaluate.call_count, 4)


if __name__ == "__main__":
    unittest.main()
