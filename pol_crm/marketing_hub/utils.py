"""
Shared helpers for the Marketing Hub (Iraq): constants, settings, plan locks,
message placeholders and single-use coupons.
"""

import re

import frappe
from frappe.utils import add_days, cint, flt, nowdate

IRAQ_GOVERNORATES = [
	"Baghdad", "Basra", "Nineveh", "Erbil", "Najaf", "Karbala", "Sulaymaniyah", "Dhi Qar", "Anbar",
	"Diyala", "Kirkuk", "Babil", "Wasit", "Maysan", "Salah al-Din", "Al-Qadisiyyah", "Al-Muthanna", "Dohuk",
]

# What the merchant picks ("Very Active") -> the RFM segments it stands for.
ACTIVITY_SEGMENTS = {
	"Very Active": ["CHAMPIONS", "LOYAL"],
	"Active": ["POTENTIAL_LOYALIST", "PROMISING", "NEED_ATTENTION"],
	"New Lead": ["NEW_CUSTOMERS"],
	"Re-engage": ["ABOUT_TO_SLEEP", "AT_RISK", "CANT_LOSE"],
	"No Activity": ["HIBERNATING", "LOST"],
}

CHANNEL_CODES = {
	"WhatsApp": "WHATSAPP",
	"Instagram DM": "INSTAGRAM",
	"Wafi App": "WAFI",
	"SMS": "SMS",
	"Telegram": "TELEGRAM",
}

SETTINGS_DEFAULTS = {
	"plan": "Free",
	"club_enabled": 0,
	"points_redeem_level": 100,
	"max_recipients_per_send": 1000,
	"skip_recent_days": 7,
	"conversion_window_days": 14,
	"whatsapp_message_price": 30,
	"gift_schedule": "50000,25000,25000",
	"gift_months_granted": 0,
	"last_gift_month": "",
}

_TOKEN = re.compile(r"(?<!\{)\{(\w+)\}(?!\})")


def split_csv(value):
	"""'Gold, Platinum' -> ['Gold', 'Platinum']"""
	if not value:
		return []
	if isinstance(value, (list, tuple, set)):
		return [str(v).strip() for v in value if str(v).strip()]
	return [part.strip() for part in re.split(r"[,\n]", str(value)) if part.strip()]


def hub_settings():
	"""Marketing Hub Settings with defaults filled in, also before the first save."""
	values = dict(SETTINGS_DEFAULTS)
	try:
		doc = frappe.get_cached_doc("Marketing Hub Settings")
	except Exception:
		doc = None
	if doc:
		for key, default in SETTINGS_DEFAULTS.items():
			value = doc.get(key)
			if value in (None, ""):
				continue
			if isinstance(default, str):
				values[key] = value
			elif key == "whatsapp_message_price":
				values[key] = flt(value)
			else:
				values[key] = cint(value)
	return frappe._dict(values)


def require_pro(feature="Meta Ads"):
	if hub_settings().plan != "Pro":
		frappe.throw(frappe._("{0} is a Pro feature. Switch the plan to Pro in Marketing Hub Settings.").format(feature))


def require_club(feature):
	if not hub_settings().club_enabled:
		frappe.throw(frappe._("{0} needs the Club subscription. Turn it on in Marketing Hub Settings.").format(feature))


def render_message(template, context):
	"""
	Fill a message. Supports the short placeholders merchants type ({name}, {code},
	{points}) and Jinja ({{ customer_name }}) used by older scenarios.
	"""
	if not template:
		return ""
	context = context or {}

	def swap(match):
		key = match.group(1)
		if key not in context:
			return match.group(0)
		value = context.get(key)
		return str(value) if value not in (None, "") else ""

	text = _TOKEN.sub(swap, template)
	if "{{" in text or "{%" in text:
		from pol_crm.marketing_automation.runner import render_template_string

		text = render_template_string(text, context)
	return text


def issue_coupon(customer, percent, validity_days=7, prefix="MKT"):
	"""Create a single-use ERPNext coupon for one customer; returns the code (or None)."""
	percent = flt(percent)
	if percent <= 0:
		return None
	from pol_crm.rfm.offer_engine import create_erpnext_coupon, generate_coupon_code

	code = generate_coupon_code(prefix)
	create_erpnext_coupon(code, customer, percent, add_days(nowdate(), cint(validity_days) or 7))
	return code


@frappe.whitelist()
def get_club_tiers():
	"""Tier names defined on the ERPNext loyalty programs, for the tier pickers."""
	if not frappe.db.exists("DocType", "Loyalty Program Collection"):
		return []
	rows = frappe.db.sql(
		"select distinct tier_name from `tabLoyalty Program Collection` where parenttype = 'Loyalty Program' order by min_spent"
	)
	return [row[0] for row in rows if row[0]]


def ensure_customer_fields():
	"""Create the Customer fields campaigns filter on.

	They are also in fixtures/custom_field.json, but Frappe skips that whole file on a
	site without Frappe CRM (it holds a CRM Deal field), so they are created here too.
	"""
	from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

	after = "custom_telegram_chat_id" if frappe.get_meta("Customer").has_field("custom_telegram_chat_id") else None
	fields = [
		{"fieldname": "custom_governorate", "fieldtype": "Select", "label": "Governorate",
			"options": "\n" + "\n".join(IRAQ_GOVERNORATES), "in_standard_filter": 1},
		{"fieldname": "custom_birth_date", "fieldtype": "Date", "label": "Birthday"},
		{"fieldname": "custom_wafi_user_id", "fieldtype": "Data", "label": "Wafi User ID"},
		{"fieldname": "custom_instagram_user_id", "fieldtype": "Data", "label": "Instagram User ID"},
		{"fieldname": "custom_instagram_last_inbound", "fieldtype": "Datetime", "label": "Last Instagram Message From Customer",
			"description": "Instagram only delivers to customers who messaged you in the last 24 hours."},
	]
	for df in fields:
		if after:
			df["insert_after"] = after
		after = df["fieldname"]
	create_custom_fields({"Customer": fields}, ignore_validate=True, update=False)


def seed_defaults():
	"""after_migrate: the occasions merchants greet on. Fixed dates repeat by themselves;
	Hijri occasions start switched off because their date must be confirmed every year."""
	ensure_customer_fields()
	if not frappe.db.exists("DocType", "Mkt Occasion"):
		return
	year = cint(nowdate()[:4])
	fixed = {"New Year": "01-01", "Teacher's Day": "03-01", "Labor Day": "05-01"}
	hijri = ["Ramadan", "Eid al-Fitr", "Eid al-Adha", "Eid al-Ghadir"]
	for name, month_day in fixed.items():
		if frappe.db.exists("Mkt Occasion", name):
			continue
		date = f"{year}-{month_day}"
		if date < nowdate():
			date = f"{year + 1}-{month_day}"
		frappe.get_doc(
			{"doctype": "Mkt Occasion", "occasion_name": name, "occasion_date": date, "repeats_yearly": 1, "enabled": 1}
		).insert(ignore_permissions=True)
	for name in hijri:
		if not frappe.db.exists("Mkt Occasion", name):
			frappe.get_doc(
				{"doctype": "Mkt Occasion", "occasion_name": name, "occasion_date": nowdate(), "repeats_yearly": 0, "enabled": 0}
			).insert(ignore_permissions=True)


def parse_tier_discounts(value):
	"""'Bronze:5, Silver:10' -> {'Bronze': 5.0, 'Silver': 10.0}"""
	out = {}
	for part in split_csv(value):
		if ":" not in part:
			continue
		tier, pct = part.split(":", 1)
		pct = flt(str(pct).replace("%", "").strip())
		if tier.strip() and pct > 0:
			out[tier.strip()] = pct
	return out
