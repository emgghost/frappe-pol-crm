"""
Unit & Integration Tests for Story 5 (Issue #6):
Marketing Automation Scenarios & Jinja2 Template Runner Tests.
"""

import unittest
from unittest.mock import MagicMock, patch

from pol_crm.tests.frappe_mock import setup_mock_frappe, reset_mock_frappe

mock_frappe = setup_mock_frappe()

import frappe
from pol_crm.marketing_automation.runner import (
    render_template_string,
    trigger_segment_change_automations,
    run_inactivity_scan,
    daily_automation_scan,
)


class TestJinja2TemplateRendering(unittest.TestCase):
    """Tests for safe Jinja2 template rendering and exception handling."""

    def setUp(self):
        reset_mock_frappe()

    def test_render_empty_or_none(self):
        self.assertEqual(render_template_string("", {}), "")
        self.assertEqual(render_template_string(None, {}), "")

    def test_render_simple_context_variables(self):
        tpl = "سلام {{ customer_name }} عزیز، خوش آمدید!"
        ctx = {"customer_name": "سارا"}
        result = render_template_string(tpl, ctx)
        self.assertEqual(result, "سلام سارا عزیز، خوش آمدید!")

    def test_render_object_attributes(self):
        tpl = "مشتری {{ customer.name }} در سگمنت {{ customer.custom_rfm_segment }} قرار گرفت."
        mock_cust = MagicMock(name="CUST-100", custom_rfm_segment="CHAMPIONS")
        mock_cust.name = "CUST-100"
        ctx = {"customer": mock_cust}
        result = render_template_string(tpl, ctx)
        self.assertEqual(result, "مشتری CUST-100 در سگمنت CHAMPIONS قرار گرفت.")

    def test_render_jinja_control_flow(self):
        tpl = "{% if old_segment %}ارتقا از {{ old_segment }} به {{ new_segment }}{% else %}ورود به {{ new_segment }}{% endif %}"
        # With old segment
        ctx1 = {"old_segment": "POTENTIAL_LOYALIST", "new_segment": "CHAMPIONS"}
        self.assertEqual(render_template_string(tpl, ctx1), "ارتقا از POTENTIAL_LOYALIST به CHAMPIONS")

        # Without old segment
        ctx2 = {"old_segment": None, "new_segment": "NEW_CUSTOMERS"}
        self.assertEqual(render_template_string(tpl, ctx2), "ورود به NEW_CUSTOMERS")

    def test_render_syntax_error_graceful_fallback(self):
        """
        Malformed Jinja2 syntax must NOT crash the CRM workflow.
        It should catch the TemplateSyntaxError, log a warning, and return the raw string.
        """
        malformed_tpl = "سلام {{ customer_name unclosed expression"
        ctx = {"customer_name": "علی"}
        result = render_template_string(malformed_tpl, ctx)
        # Returns fallback raw template string
        self.assertEqual(result, malformed_tpl)
        frappe.logger().warning.assert_called()


class TestSegmentChangeAutomations(unittest.TestCase):
    """Tests for event-driven segment transition automations."""

    def setUp(self):
        reset_mock_frappe()

    def test_scenario_doctype_missing_early_return(self):
        frappe.db.exists.side_effect = None
        frappe.db.exists.return_value = False

        trigger_segment_change_automations("CUST-1", "LOST", "CHAMPIONS")
        frappe.get_all.assert_not_called()

    def test_no_matching_active_scenarios(self):
        frappe.db.exists.side_effect = None
        frappe.db.exists.return_value = True
        frappe.get_all.return_value = []  # No scenario found

        trigger_segment_change_automations("CUST-1", "NEW_CUSTOMERS", "POTENTIAL_LOYALIST")
        frappe.get_doc.assert_not_called()

    @patch("pol_crm.marketing_automation.runner.send_marketing_message")
    def test_trigger_segment_change_scenario_success(self, mock_send_mkt):
        frappe.db.exists.side_effect = None
        frappe.db.exists.return_value = True

        mock_scenario = MagicMock(
            scenario_name="تبریک پیوستن به مشتریان برتر",
            channel="SMS",
            message_template="سلام {{ customer_name }} عزیز، شما اکنون یک {{ new_segment }} هستید!",
            template_code="CHAMP_WELCOME",
        )
        mock_scenario.name = "SCN-001"
        frappe.get_all.return_value = [mock_scenario]

        mock_customer = MagicMock(
            customer_name="امید نوری",
            mobile_no="09123334455",
            phone=None,
        )
        mock_customer.name = "CUST-CHAMP"
        frappe.get_doc.return_value = mock_customer

        trigger_segment_change_automations("CUST-CHAMP", "POTENTIAL_LOYALIST", "CHAMPIONS")

        frappe.get_all.assert_called_once_with(
            "Mkt Scenario",
            filters={
                "enabled": 1,
                "trigger_type": "RFM_SEGMENT_CHANGE",
                "target_rfm_segment": "CHAMPIONS",
            },
            fields=["name", "scenario_name", "channel", "message_template", "template_code"],
        )
        frappe.get_doc.assert_called_once_with("Customer", "CUST-CHAMP")
        mock_send_mkt.assert_called_once_with(
            customer="CUST-CHAMP",
            phone="09123334455",
            text="سلام امید نوری عزیز، شما اکنون یک CHAMPIONS هستید!",
            channel="SMS",
            template_code="CHAMP_WELCOME",
            category="marketing",
        )

    @patch("pol_crm.marketing_automation.runner.send_marketing_message")
    def test_customer_phone_fallback_when_mobile_is_empty(self, mock_send_mkt):
        frappe.db.exists.side_effect = None
        frappe.db.exists.return_value = True

        mock_scenario = MagicMock(
            channel="SMS",
            message_template="سلام {{ customer_name }}",
            template_code=None,
        )
        frappe.get_all.return_value = [mock_scenario]

        # mobile_no is None, phone has mobile number
        mock_customer = MagicMock(customer_name="محسن", mobile_no=None, phone="09127778899")
        frappe.get_doc.return_value = mock_customer

        trigger_segment_change_automations("CUST-PHONE", "LOST", "NEW_CUSTOMERS")
        mock_send_mkt.assert_called_once_with(
            customer="CUST-PHONE",
            phone="09127778899",
            text="سلام محسن",
            channel="SMS",
            template_code=None,
            category="marketing",
        )


class TestInactivityScan(unittest.TestCase):
    """Tests for scheduled customer inactivity scan and messaging."""

    def setUp(self):
        reset_mock_frappe()

    def test_inactivity_doctype_missing_early_return(self):
        frappe.db.exists.side_effect = None
        frappe.db.exists.return_value = False

        run_inactivity_scan()
        frappe.get_all.assert_not_called()

    @patch("pol_crm.marketing_automation.runner.send_marketing_message")
    def test_inactivity_scan_matches_and_dispatches(self, mock_send_mkt):
        frappe.db.exists.side_effect = None
        frappe.db.exists.return_value = True

        mock_scenario = MagicMock(
            inactivity_days=45,
            channel="SMS",
            message_template="سلام {{ customer_name }} عزیز، {{ days }} روزه از آخرین خریدتون میگذره!",
        )
        mock_scenario.name = "SCN-INACTIVE-45"

        mock_candidate1 = MagicMock(customer_name="مریم", mobile_no="09121112222", phone=None)
        mock_candidate1.name = "CUST-M1"

        mock_candidate2 = MagicMock(customer_name="داود", mobile_no="09123334444", phone=None)
        mock_candidate2.name = "CUST-D2"

        # First get_all call for Mkt Scenario, second for Customers matching 45 days
        frappe.get_all.side_effect = [
            [mock_scenario],
            [mock_candidate1, mock_candidate2],
        ]

        run_inactivity_scan()

        self.assertEqual(mock_send_mkt.call_count, 2)
        mock_send_mkt.assert_any_call(
            customer="CUST-M1",
            phone="09121112222",
            text="سلام مریم عزیز، 45 روزه از آخرین خریدتون میگذره!",
            channel="SMS",
            category="marketing",
        )
        mock_send_mkt.assert_any_call(
            customer="CUST-D2",
            phone="09123334444",
            text="سلام داود عزیز، 45 روزه از آخرین خریدتون میگذره!",
            channel="SMS",
            category="marketing",
        )

    @patch("pol_crm.marketing_automation.runner.send_marketing_message")
    def test_inactivity_scan_no_matching_customers(self, mock_send_mkt):
        frappe.db.exists.side_effect = None
        frappe.db.exists.return_value = True

        mock_scenario = MagicMock(inactivity_days=60, channel="SMS", message_template="Hello")
        frappe.get_all.side_effect = [
            [mock_scenario],
            [],  # No customers matching 60 days
        ]

        run_inactivity_scan()
        mock_send_mkt.assert_not_called()


class TestDailyAutomationScan(unittest.TestCase):
    """Tests for nightly scheduled automation scan task."""

    def setUp(self):
        reset_mock_frappe()

    @patch("pol_crm.marketing_automation.runner.run_inactivity_scan")
    def test_daily_automation_scan(self, mock_run):
        daily_automation_scan()
        mock_run.assert_called_once()
        frappe.logger().info.assert_called()


if __name__ == "__main__":
    unittest.main()
