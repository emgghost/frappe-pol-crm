"""
Unit & Integration Tests for Story 5 (Issue #6):
Who gets an automation and when is tested against a real site in
marketing_hub/doctype/mkt_campaign/test_mkt_campaign.py.
Marketing Automation Scenarios & Jinja2 Template Runner Tests.
"""

import unittest
from unittest.mock import MagicMock, patch

from pol_crm.tests.frappe_mock import setup_mock_frappe, reset_mock_frappe

mock_frappe = setup_mock_frappe()

import frappe
from pol_crm.marketing_hub.runner import (
    render_template_string,
    trigger_segment_change_automations,
    run_inactivity_scan,
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


class TestInactivityScan(unittest.TestCase):
    """Tests for scheduled customer inactivity scan and messaging."""

    def setUp(self):
        reset_mock_frappe()

    def test_inactivity_doctype_missing_early_return(self):
        frappe.db.exists.side_effect = None
        frappe.db.exists.return_value = False

        run_inactivity_scan()
        frappe.get_all.assert_not_called()


if __name__ == "__main__":
    unittest.main()
