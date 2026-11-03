"""
Telegram Bot Adapter for POL CRM
Supports proxy and relay base URLs for servers located in Iran.
"""

import requests
import frappe


def get_telegram_config():
    """Retrieve Telegram Bot credentials and proxy settings."""
    bot_token = None
    proxy_url = None
    relay_url = None

    if frappe.db.exists("DocType", "Messaging Settings"):
        settings = frappe.get_single("Messaging Settings")
        bot_token = settings.telegram_bot_token
        proxy_url = settings.telegram_proxy_url
        relay_url = settings.telegram_relay_url

    if not bot_token:
        bot_token = frappe.conf.get("telegram_bot_token")

    return bot_token, proxy_url, relay_url


def send_telegram_message(chat_id, text, parse_mode="HTML"):
    """Send message via Telegram Bot API."""
    bot_token, proxy_url, relay_url = get_telegram_config()
    if not bot_token:
        frappe.logger("pol_crm").warning("Telegram Bot token not configured.")
        return {"success": False, "error": "MISSING_BOT_TOKEN"}

    # Use custom relay base URL if provided (e.g., https://my-relay.example.com/bot<token>/sendMessage)
    base_api = relay_url.rstrip("/") if relay_url else "https://api.telegram.org"
    url = f"{base_api}/bot{bot_token}/sendMessage"

    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
    }

    proxies = {"https": proxy_url, "http": proxy_url} if proxy_url else None

    try:
        response = requests.post(url, json=payload, proxies=proxies, timeout=12)
        data = response.json()
        if response.status_code == 200 and data.get("ok"):
            message_id = data.get("result", {}).get("message_id")
            return {"success": True, "message_id": message_id}
        else:
            return {"success": False, "error": data.get("description")}
    except Exception as e:
        return {"success": False, "error": str(e)}
