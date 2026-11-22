"""
Outbound channels used in Iraq: WhatsApp (Meta Cloud API), Instagram DM (Graph API)
and the Wafi app. Every sender returns {"success": bool, "message_id"|"error": ...}
like the Kavenegar and Telegram adapters.
"""

import frappe
import requests

GRAPH_URL = "https://graph.facebook.com/v25.0"
TIMEOUT = 15


def _settings():
	if not frappe.db.exists("DocType", "Marketing Hub Settings"):
		return None
	return frappe.get_single("Marketing Hub Settings")


def _secret(settings, fieldname):
	try:
		return settings.get_password(fieldname, raise_exception=False)
	except Exception:
		return None


def _post(url, payload, token):
	try:
		response = requests.post(url, json=payload, headers={"Authorization": f"Bearer {token}"}, timeout=TIMEOUT)
		data = response.json() if response.content else {}
	except Exception as e:
		frappe.logger("pol_crm").error(f"Channel request failed: {e}")
		return None, str(e)
	if response.status_code >= 400:
		error = data.get("error") if isinstance(data, dict) else None
		message = error.get("message") if isinstance(error, dict) else (error or f"HTTP {response.status_code}")
		return None, str(message)
	return data, None


def send_whatsapp_message(to_e164, text, media_url=None):
	"""Send through the WhatsApp Cloud API. Uses the approved template when one is configured."""
	settings = _settings()
	phone_id = settings and settings.whatsapp_phone_number_id
	token = settings and _secret(settings, "whatsapp_access_token")
	if not phone_id or not token:
		return {"success": False, "error": "WHATSAPP_NOT_CONFIGURED"}

	payload = {"messaging_product": "whatsapp", "to": str(to_e164).lstrip("+")}
	if settings.whatsapp_template_name:
		payload["type"] = "template"
		payload["template"] = {
			"name": settings.whatsapp_template_name,
			"language": {"code": settings.whatsapp_template_language or "ar"},
			"components": [{"type": "body", "parameters": [{"type": "text", "text": text}]}],
		}
	elif media_url:
		kind = "video" if str(media_url).lower().rsplit(".", 1)[-1] in ("mp4", "mov", "3gp") else "image"
		payload["type"] = kind
		payload[kind] = {"link": media_url, "caption": text}
	else:
		payload["type"] = "text"
		payload["text"] = {"body": text}

	data, error = _post(f"{GRAPH_URL}/{phone_id}/messages", payload, token)
	if error:
		return {"success": False, "error": error}
	messages = data.get("messages") or [{}]
	return {"success": True, "message_id": messages[0].get("id")}


def send_instagram_dm(recipient_id, text, media_url=None):
	"""Send an Instagram direct message. Meta only delivers inside the 24-hour window."""
	settings = _settings()
	account_id = settings and settings.instagram_account_id
	token = settings and _secret(settings, "instagram_access_token")
	if not account_id or not token:
		return {"success": False, "error": "INSTAGRAM_NOT_CONFIGURED"}

	url = f"{GRAPH_URL}/{account_id}/messages"
	message_id = None
	if media_url:
		attachment = {"attachment": {"type": "image", "payload": {"url": media_url}}}
		data, error = _post(url, {"recipient": {"id": recipient_id}, "message": attachment}, token)
		if error:
			return {"success": False, "error": error}
		message_id = data.get("message_id")
	if text:
		data, error = _post(url, {"recipient": {"id": recipient_id}, "message": {"text": text}}, token)
		if error:
			return {"success": False, "error": error}
		message_id = data.get("message_id") or message_id
	return {"success": True, "message_id": message_id}


WAFI_DEFAULT_PATHS = {
	"wafi_messages_path": "messages",
	"wafi_promotions_path": "promotions",
	"wafi_notifications_path": "notifications/send",
	"wafi_status_path": "promotions/{reference}",
}


def _wafi_target(path_field, reference=None):
	"""(url, token, settings) for one Wafi API call; the path comes from Marketing Hub Settings."""
	settings = _settings()
	base = settings and (settings.wafi_api_url or "").rstrip("/")
	token = settings and _secret(settings, "wafi_api_key")
	if not base or not token:
		return None, None, None
	path = (settings.get(path_field) or WAFI_DEFAULT_PATHS[path_field]).replace("{reference}", str(reference or ""))
	return f"{base}/{path.lstrip('/')}", token, settings


def wafi_request(path_field, payload):
	"""POST to the Wafi app's API. Returns (data, error)."""
	url, token, settings = _wafi_target(path_field)
	if not url:
		return None, "WAFI_NOT_CONFIGURED"
	body = dict(payload or {})
	body.setdefault("merchant_id", settings.wafi_merchant_id)
	return _post(url, body, token)


def wafi_get(path_field, reference):
	"""GET from the Wafi app's API (the review status of a request). Returns (data, error)."""
	url, token, settings = _wafi_target(path_field, reference)
	if not url:
		return None, "WAFI_NOT_CONFIGURED"
	try:
		response = requests.get(
			url, params={"merchant_id": settings.wafi_merchant_id}, headers={"Authorization": f"Bearer {token}"}, timeout=TIMEOUT
		)
		data = response.json() if response.content else {}
	except Exception as e:
		return None, str(e)
	if response.status_code >= 400:
		return None, f"HTTP {response.status_code}"
	return data, None


def send_wafi_message(recipient, text, media_url=None):
	"""In-app message + notification to one Wafi user (by Wafi user id or phone)."""
	data, error = wafi_request("wafi_messages_path", {"recipient": recipient, "text": text, "media_url": media_url})
	if error:
		return {"success": False, "error": error}
	return {"success": True, "message_id": (data or {}).get("id")}
