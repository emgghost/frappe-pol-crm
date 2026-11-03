"""
Policy Layer for POL CRM Messaging
Enforces quiet hours, frequency capping, consent/opt-out rules, test-mode redirection,
and audit logging in Mkt Message Log.
"""

from datetime import datetime, time
import pytz
import frappe
from frappe.utils import now_datetime, nowdate, add_days, getdate, cint
from pol_crm.messaging.phone_utils import normalize_iranian_mobile
from pol_crm.messaging.kavenegar import send_kavenegar_sms, send_kavenegar_pattern
from pol_crm.messaging.telegram import send_telegram_message


def get_messaging_settings():
    """Load messaging policy settings or sensible defaults."""
    if frappe.db.exists("DocType", "Messaging Settings"):
        settings = frappe.get_single("Messaging Settings")
        return {
            "quiet_hours_enabled": getattr(settings, "quiet_hours_enabled", 1),
            "quiet_start_hour": cint(getattr(settings, "quiet_start_hour", 21)),
            "quiet_end_hour": cint(getattr(settings, "quiet_end_hour", 9)),
            "timezone": getattr(settings, "timezone", "Asia/Tehran") or "Asia/Tehran",
            "cap_per_day": cint(getattr(settings, "cap_per_day", 1)),
            "cap_per_week": cint(getattr(settings, "cap_per_week", 2)),
            "test_mode": getattr(settings, "test_mode", 0),
            "test_phone": getattr(settings, "test_phone", None),
        }
    return {
        "quiet_hours_enabled": 1,
        "quiet_start_hour": 21,
        "quiet_end_hour": 9,
        "timezone": "Asia/Tehran",
        "cap_per_day": 1,
        "cap_per_week": 2,
        "test_mode": 0,
        "test_phone": None,
    }


def is_in_quiet_hours(settings):
    """Check if current time in specified timezone falls into quiet hours."""
    if not settings.get("quiet_hours_enabled"):
        return False

    tz = pytz.timezone(settings.get("timezone", "Asia/Tehran"))
    local_now = datetime.now(tz)
    current_hour = local_now.hour

    start = settings.get("quiet_start_hour", 21)
    end = settings.get("quiet_end_hour", 9)

    # e.g. 21:00 to 09:00 spans midnight
    if start > end:
        return current_hour >= start or current_hour < end
    else:
        return start <= current_hour < end


def check_frequency_cap(customer, settings):
    """
    Check if the customer has exceeded the daily or weekly marketing message cap.
    Returns (exceeded: bool, reason: str)
    """
    if not frappe.db.exists("DocType", "Mkt Message Log"):
        return False, None

    now = now_datetime()
    one_day_ago = add_days(now, -1)
    seven_days_ago = add_days(now, -7)

    # Count messages sent in last 24h
    day_count = frappe.db.count(
        "Mkt Message Log",
        filters={
            "customer": customer,
            "status": "SENT",
            "category": "marketing",
            "creation": [">=", one_day_ago],
        },
    )
    if day_count >= settings.get("cap_per_day", 1):
        return True, "DAILY_CAP_REACHED"

    # Count messages sent in last 7 days
    week_count = frappe.db.count(
        "Mkt Message Log",
        filters={
            "customer": customer,
            "status": "SENT",
            "category": "marketing",
            "creation": [">=", seven_days_ago],
        },
    )
    if week_count >= settings.get("cap_per_week", 2):
        return True, "WEEKLY_CAP_REACHED"

    return False, None


def is_customer_opted_out(customer, channel="SMS"):
    """Check customer consent and opt-out flags."""
    cust = frappe.db.get_value(
        "Customer",
        customer,
        ["custom_mkt_opted_out_all", "custom_mkt_sms_opted_out"],
        as_dict=True,
    )
    if cust:
        if cust.get("custom_mkt_opted_out_all"):
            return True
        if channel == "SMS" and cust.get("custom_mkt_sms_opted_out"):
            return True

    # Also check Mkt Subscription if exists
    if frappe.db.exists("DocType", "Mkt Subscription"):
        sub = frappe.db.get_value(
            "Mkt Subscription",
            {"customer": customer, "channel": channel},
            "status",
        )
        if sub == "OPTED_OUT":
            return True

    return False


def log_message(customer, channel, to_address, text, status, reason=None, message_id=None, category="marketing", existing_log_name=None):
    """Persist message record into Mkt Message Log, or update existing postponed log to preserve audit trail."""
    if frappe.db.exists("DocType", "Mkt Message Log"):
        try:
            if existing_log_name and frappe.db.exists("Mkt Message Log", existing_log_name):
                frappe.db.set_value(
                    "Mkt Message Log",
                    existing_log_name,
                    {
                        "status": status,
                        "skip_reason": reason,
                        "external_id": str(message_id) if message_id else None,
                    },
                    update_modified=True,
                )
                frappe.db.commit()
                return existing_log_name

            doc = frappe.get_doc({
                "doctype": "Mkt Message Log",
                "customer": customer,
                "channel": channel,
                "recipient": to_address,
                "message_body": text,
                "status": status,
                "skip_reason": reason,
                "external_id": str(message_id) if message_id else None,
                "category": category,
            })
            doc.insert(ignore_permissions=True)
            frappe.db.commit()
            return doc.name
        except Exception as e:
            frappe.logger("pol_crm").error(f"Failed to log message: {str(e)}")
    return None


def send_marketing_message(
    customer,
    phone=None,
    telegram_chat_id=None,
    text="",
    channel="SMS",
    template_code=None,
    template_tokens=None,
    category="marketing",
    urgent=False,
    existing_log_name=None,
):
    """
    Main entry point for all outbound communications.
    Enforces quiet hours, capping, opt-outs, test-mode, and logging.
    """
    settings = get_messaging_settings()

    # 1. Opt-out Check
    if is_customer_opted_out(customer, channel):
        log_message(customer, channel, phone or telegram_chat_id, text, "SKIPPED", reason="OPTED_OUT", category=category, existing_log_name=existing_log_name)
        return {"status": "SKIPPED", "reason": "OPTED_OUT"}

    # 2. Quiet Hours Check (for non-urgent marketing)
    if category == "marketing" and not urgent and is_in_quiet_hours(settings):
        log_message(customer, channel, phone or telegram_chat_id, text, "POSTPONED", reason="QUIET_HOURS", category=category, existing_log_name=existing_log_name)
        return {"status": "POSTPONED", "reason": "QUIET_HOURS"}

    # 3. Frequency Capping Check (for marketing)
    if category == "marketing" and not urgent:
        capped, cap_reason = check_frequency_cap(customer, settings)
        if capped:
            log_message(customer, channel, phone or telegram_chat_id, text, "SKIPPED", reason=cap_reason, category=category, existing_log_name=existing_log_name)
            return {"status": "SKIPPED", "reason": cap_reason}

    # 4. Target Address & Test Mode Redirection
    final_recipient = phone
    final_chat_id = telegram_chat_id
    if settings.get("test_mode") and settings.get("test_phone"):
        final_recipient = settings.get("test_phone")
        final_chat_id = settings.get("test_phone")
        frappe.logger("pol_crm").info(f"Test mode active: redirected message for {customer} to {final_recipient}")

    # 5. Channel Dispatch
    if channel == "SMS":
        e164, local_phone, is_valid = normalize_iranian_mobile(final_recipient)
        if not is_valid:
            log_message(customer, channel, final_recipient, text, "SKIPPED", reason="INVALID_PHONE", category=category, existing_log_name=existing_log_name)
            return {"status": "SKIPPED", "reason": "INVALID_PHONE"}

        # Pattern-based sending if template provided
        if template_code and template_tokens:
            res = send_kavenegar_pattern(local_phone, template_code, template_tokens)
        else:
            res = send_kavenegar_sms(local_phone, text)

        if res.get("success"):
            log_message(customer, channel, local_phone, text, "SENT", message_id=res.get("message_id"), category=category, existing_log_name=existing_log_name)
            return {"status": "SENT", "message_id": res.get("message_id")}
        else:
            log_message(customer, channel, local_phone, text, "FAILED", reason=res.get("error"), category=category, existing_log_name=existing_log_name)
            return {"status": "FAILED", "error": res.get("error")}

    elif channel == "TELEGRAM":
        target_chat = final_chat_id
        if not target_chat:
            log_message(customer, channel, target_chat, text, "SKIPPED", reason="NO_CHAT_ID", category=category, existing_log_name=existing_log_name)
            return {"status": "SKIPPED", "reason": "NO_CHAT_ID"}

        res = send_telegram_message(target_chat, text)
        if res.get("success"):
            log_message(customer, channel, target_chat, text, "SENT", message_id=res.get("message_id"), category=category, existing_log_name=existing_log_name)
            return {"status": "SENT", "message_id": res.get("message_id")}
        else:
            log_message(customer, channel, target_chat, text, "FAILED", reason=res.get("error"), category=category, existing_log_name=existing_log_name)
            return {"status": "FAILED", "error": res.get("error")}

    return {"status": "SKIPPED", "reason": "UNSUPPORTED_CHANNEL"}


def enqueue_marketing_message(
    customer,
    phone=None,
    telegram_chat_id=None,
    text="",
    channel="SMS",
    template_code=None,
    template_tokens=None,
    category="marketing",
    urgent=False,
    now=False,
):
    """
    Enqueue marketing message to be processed asynchronously via Redis Queue.
    In testing (frappe.flags.in_test) or if now=True, dispatches synchronously.
    """
    if now or not frappe or not hasattr(frappe, "enqueue") or getattr(getattr(frappe, "flags", None), "in_test", False):
        return send_marketing_message(
            customer=customer,
            phone=phone,
            telegram_chat_id=telegram_chat_id,
            text=text,
            channel=channel,
            template_code=template_code,
            template_tokens=template_tokens,
            category=category,
            urgent=urgent,
        )

    return frappe.enqueue(
        "pol_crm.messaging.policy.send_marketing_message",
        queue="short",
        customer=customer,
        phone=phone,
        telegram_chat_id=telegram_chat_id,
        text=text,
        channel=channel,
        template_code=template_code,
        template_tokens=template_tokens,
        category=category,
        urgent=urgent,
    )


def process_postponed_messages():
    """Hourly background job to retry messages that were postponed during quiet hours."""
    settings = get_messaging_settings()
    if is_in_quiet_hours(settings):
        return  # Still in quiet hours

    if not frappe.db.exists("DocType", "Mkt Message Log"):
        return

    postponed = frappe.get_all(
        "Mkt Message Log",
        filters={"status": "POSTPONED"},
        fields=["name", "customer", "recipient", "channel", "message_body", "category"],
        limit=50,
    )

    for item in postponed:
        if item.channel == "TELEGRAM":
            send_marketing_message(
                customer=item.customer,
                telegram_chat_id=item.recipient,
                text=item.message_body,
                channel=item.channel,
                category=item.category,
                existing_log_name=item.name,
            )
        else:
            send_marketing_message(
                customer=item.customer,
                phone=item.recipient,
                text=item.message_body,
                channel=item.channel,
                category=item.category,
                existing_log_name=item.name,
            )
