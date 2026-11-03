"""
Automation Runner for POL CRM
Executes event-driven and scheduled marketing scenarios based on
RFM segment transitions, purchase milestones, and customer inactivity.
"""

import jinja2
import frappe
from frappe.utils import nowdate, date_diff, cint
from pol_crm.messaging.policy import send_marketing_message


def dispatch_marketing_message(**kwargs):
    """Dispatch marketing message asynchronously via Redis Queue, or synchronously in test mode."""
    if frappe and hasattr(frappe, "enqueue") and not getattr(getattr(frappe, "flags", None), "in_test", False):
        return frappe.enqueue(
            "pol_crm.messaging.policy.send_marketing_message",
            queue="short",
            **kwargs,
        )
    return send_marketing_message(**kwargs)


def render_template_string(template_str, context):
    """Render a template string with Jinja2 syntax (e.g. {{ customer_name }})."""
    if not template_str:
        return ""
    try:
        template = jinja2.Template(template_str)
        return template.render(**context)
    except Exception as e:
        frappe.logger("pol_crm").warning(f"Template rendering failed: {str(e)}")
        return template_str


def trigger_segment_change_automations(customer_name, old_segment, new_segment):
    """
    Triggered when an RFM segment change occurs on a Customer record.
    Finds active scenarios listening for this transition.
    """
    if not frappe.db.exists("DocType", "Mkt Scenario"):
        return

    scenarios = frappe.get_all(
        "Mkt Scenario",
        filters={
            "enabled": 1,
            "trigger_type": "RFM_SEGMENT_CHANGE",
            "target_rfm_segment": new_segment,
        },
        fields=["name", "scenario_name", "channel", "message_template", "template_code"],
    )

    if not scenarios:
        return

    customer_doc = frappe.get_doc("Customer", customer_name)
    context = {
        "customer": customer_doc,
        "customer_name": customer_doc.customer_name,
        "old_segment": old_segment,
        "new_segment": new_segment,
    }

    for sc in scenarios:
        body = render_template_string(sc.message_template, context)
        phone = customer_doc.mobile_no or customer_doc.phone
        if sc.channel == "TELEGRAM":
            telegram_chat_id = customer_doc.get("custom_telegram_chat_id") if hasattr(customer_doc, "get") else None
            dispatch_marketing_message(
                customer=customer_name,
                telegram_chat_id=telegram_chat_id,
                text=body,
                channel=sc.channel or "SMS",
                template_code=sc.template_code,
                category="marketing",
            )
        else:
            dispatch_marketing_message(
                customer=customer_name,
                phone=phone,
                text=body,
                channel=sc.channel or "SMS",
                template_code=sc.template_code,
                category="marketing",
            )


def run_inactivity_scan():
    """Scan for customers with no purchase in X days matching active inactivity scenarios."""
    if not frappe.db.exists("DocType", "Mkt Scenario"):
        return

    inactivity_scenarios = frappe.get_all(
        "Mkt Scenario",
        filters={"enabled": 1, "trigger_type": "INACTIVITY"},
        fields=["name", "scenario_name", "inactivity_days", "channel", "message_template"],
    )

    for sc in inactivity_scenarios:
        target_days = cint(sc.inactivity_days) or 60
        # Find customers whose last purchase was target_days ago
        candidates = frappe.get_all(
            "Customer",
            filters={
                "disabled": 0,
                "custom_days_since_last_purchase": target_days,
            },
            fields=["name", "customer_name", "mobile_no", "phone"],
        )

        for cust in candidates:
            context = {"customer_name": cust.customer_name, "days": target_days}
            body = render_template_string(sc.message_template, context)
            phone = cust.mobile_no or cust.phone
            msg_kwargs = {
                "customer": cust.name,
                "text": body,
                "channel": sc.channel or "SMS",
                "category": "marketing",
            }
            if sc.channel == "TELEGRAM":
                msg_kwargs["telegram_chat_id"] = cust.get("custom_telegram_chat_id") or cust.get("telegram_chat_id")
            else:
                msg_kwargs["phone"] = phone
            dispatch_marketing_message(**msg_kwargs)


def daily_automation_scan():
    """Daily scheduler event to execute date-based marketing scans."""
    frappe.logger("pol_crm").info("Running daily marketing automation scan...")
    run_inactivity_scan()
