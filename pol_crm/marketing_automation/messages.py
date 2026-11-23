"""
What a customer receives: the text with their name filled in and, when the campaign or
automation offers one, a discount code that is theirs alone.

Placeholders a merchant can write in a message:
	{name}      the customer's name
	{code}      their discount code
	{discount}  the discount, for example ۱۰٪
	{expiry}    the last day the code works, as a Jalali date
The older {{ customer_name }} style still works in automations written before.
"""

import frappe
from frappe.utils import add_days, cint, flt, nowdate

from pol_crm.marketing_automation.runner import render_template_string
from pol_crm.messaging.policy import send_marketing_message
from pol_crm.rfm.offer_engine import create_erpnext_coupon, generate_coupon_code

PLACEHOLDERS = ("name", "code", "discount", "expiry")


def persian_digits(value):
	try:
		from iran_base.utils.numbers import to_persian_digits

		return to_persian_digits(value)
	except ImportError:
		return str(value)


def jalali_date(date):
	try:
		from iran_base.utils.jalali import format_jalali

		return format_jalali(date, persian_digits=True)
	except ImportError:
		return str(date)


def render_message(template, context):
	text = render_template_string(template or "", context)
	for key in PLACEHOLDERS:
		text = text.replace("{" + key + "}", str(context.get(key) or ""))
	return text.strip()


def issue_code(customer, percent, valid_days, reason):
	"""A single-use code for one customer, made an ERPNext coupon when ERPNext can take it."""
	valid_until = add_days(nowdate(), cint(valid_days) or 7)
	code = generate_coupon_code("POL")
	create_erpnext_coupon(code, customer, flt(percent), valid_until)
	frappe.get_doc(
		{
			"doctype": "Loyalty Offer",
			"customer": customer,
			"reason": reason,
			"offer_type": "DISCOUNT_CODE",
			"discount_code": code,
			"percentage_value": flt(percent),
			"valid_from": nowdate(),
			"valid_until": valid_until,
			"status": "ACTIVE",
		}
	).insert(ignore_permissions=True)
	return code, valid_until


def build_context(customer, source, reason, sample=False):
	"""Everything a message can mention. A sample context shows the merchant how it will read."""
	context = {
		"name": customer.get("customer_name") or customer.get("name"),
		"customer_name": customer.get("customer_name") or customer.get("name"),
		"customer": customer,
	}
	percent = flt(source.get("discount_percent"))
	if percent:
		days = cint(source.get("code_valid_days")) or 7
		if sample:
			code, valid_until = "POL-TEST12", add_days(nowdate(), days)
		else:
			code, valid_until = issue_code(customer.get("name"), percent, days, reason)
		context.update(
			{
				"code": code,
				"discount": persian_digits(f"{percent:g}") + "٪",
				"expiry": jalali_date(valid_until),
			}
		)
	return context


def send_to_customer(customer, source, reason, scenario=None, campaign=None):
	"""Send a campaign's or automation's message to one customer, through the messaging rules."""
	text = render_message(
		source.get("message") or source.get("message_template"),
		build_context(customer, source, reason),
	)
	return send_marketing_message(
		customer=customer.get("name"),
		phone=customer.get("mobile_no"),
		telegram_chat_id=customer.get("custom_telegram_chat_id"),
		text=text,
		channel=source.get("channel") or "SMS",
		category="marketing",
		scenario=scenario,
		campaign=campaign,
	)


def preview_text(source, customer_name="مشتری نمونه"):
	customer = {"name": customer_name, "customer_name": customer_name}
	return render_message(
		source.get("message") or source.get("message_template"),
		build_context(customer, source, reason=None, sample=True),
	)
