"""
Kavenegar SMS Gateway Integration for POL CRM
Supports standard SMS sending and Verify/Pattern-based (خدماتی / پترن) sending.
"""

import requests
import frappe


def get_kavenegar_config():
    """Retrieve API key and sender number from settings or environment."""
    api_key = None
    sender = None

    if frappe.db.exists("DocType", "Messaging Settings"):
        settings = frappe.get_single("Messaging Settings")
        api_key = settings.kavenegar_api_key
        sender = settings.kavenegar_sender_line

    if not api_key:
        api_key = frappe.conf.get("kavenegar_api_key")

    return api_key, sender


def send_kavenegar_sms(receptor, message_text, sender=None):
    """Send standard text SMS via Kavenegar API."""
    api_key, default_sender = get_kavenegar_config()
    if not api_key:
        frappe.logger("pol_crm").warning("Kavenegar API key not configured.")
        return {"success": False, "error": "MISSING_API_KEY"}

    url = f"https://api.kavenegar.com/v1/{api_key}/sms/send.json"
    payload = {
        "receptor": receptor,
        "message": message_text,
        "sender": sender or default_sender,
    }

    try:
        response = requests.post(url, data=payload, timeout=10)
        data = response.json()
        if response.status_code == 200 and data.get("return", {}).get("status") == 200:
            entries = data.get("entries", [])
            message_id = entries[0].get("messageid") if entries else None
            return {"success": True, "message_id": message_id}
        else:
            return {"success": False, "error": data.get("return", {}).get("message")}
    except Exception as e:
        return {"success": False, "error": str(e)}


def send_kavenegar_pattern(receptor, template, tokens):
    """
    Send OTP or Service/Pattern-based SMS via Kavenegar Verify API.
    Bypasses Iranian telco advertising blocks.
    tokens: dict like {'token': 'val1', 'token2': 'val2', 'token3': 'val3'}
    """
    api_key, _ = get_kavenegar_config()
    if not api_key:
        frappe.logger("pol_crm").warning("Kavenegar API key not configured.")
        return {"success": False, "error": "MISSING_API_KEY"}

    url = f"https://api.kavenegar.com/v1/{api_key}/verify/lookup.json"
    payload = {
        "receptor": receptor,
        "template": template,
    }
    # Map tokens to token, token2, token3, token10, token20
    for k, v in tokens.items():
        payload[k] = str(v)

    try:
        response = requests.post(url, data=payload, timeout=10)
        data = response.json()
        if response.status_code == 200 and data.get("return", {}).get("status") == 200:
            entries = data.get("entries", [])
            message_id = entries[0].get("messageid") if entries else None
            return {"success": True, "message_id": message_id}
        else:
            return {"success": False, "error": data.get("return", {}).get("message")}
    except Exception as e:
        return {"success": False, "error": str(e)}
