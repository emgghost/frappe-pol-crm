"""
What a customer receives: the text with their name filled in and, when the campaign or
automation offers one, a discount code that is theirs alone.

Placeholders a merchant can write in a message:
	{name}      the customer's name
	{code}      their discount code
	{discount}  the discount, for example ۱۰٪
	{expiry}    the last day the code works, as a Jalali date
	{occasion}  the occasion being greeted (occasion automations)
	{item}      the item back in stock (back-in-stock automations)
	{event} {date} {time} {place}   the event of an invitation campaign
The older {{ customer_name }} style still works in automations written before.
"""

import frappe
from frappe.utils import add_days, cint, flt, nowdate

from pol_crm.marketing_hub.runner import render_template_string
from pol_crm.messaging.policy import send_marketing_message
from pol_crm.rfm.offer_engine import create_erpnext_coupon, generate_coupon_code

PLACEHOLDERS = ("name", "code", "discount", "expiry", "occasion", "item", "event", "date", "time", "place")


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


def issue_code(customer, percent, valid_days, reason, campaign=None, scenario=None):
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
			"campaign": campaign,
			"scenario": scenario,
		}
	).insert(ignore_permissions=True)
	return code, valid_until


def event_context(source):
	"""{event}, {date}, {time} and {place} of an invitation campaign."""
	if not source.get("event_datetime"):
		return {}
	from frappe.utils import get_datetime

	when = get_datetime(source.get("event_datetime"))
	return {
		"event": source.get("event_title") or "",
		"date": jalali_date(when.date()),
		"time": persian_digits(when.strftime("%H:%M")),
		"place": source.get("event_place") or "",
	}


def build_context(customer, source, reason, sample=False, extra=None, with_code=True):
	"""Everything a message can mention. A sample context shows the merchant how it will read."""
	context = {
		"name": customer.get("customer_name") or customer.get("name"),
		"customer_name": customer.get("customer_name") or customer.get("name"),
		"customer": customer,
		**event_context(source),
		**(extra or {}),
	}
	percent = flt(source.get("discount_percent")) if with_code else 0
	if percent:
		days = cint(source.get("code_valid_days")) or 7
		if sample:
			code, valid_until = "POL-TEST12", add_days(nowdate(), days)
		else:
			code, valid_until = issue_code(
				customer.get("name"),
				percent,
				days,
				reason,
				campaign=source.name if source.get("doctype") == "Mkt Campaign" else None,
				scenario=source.name if source.get("doctype") == "Mkt Scenario" else None,
			)
		context.update(
			{
				"code": code,
				"discount": persian_digits(f"{percent:g}") + "٪",
				"expiry": jalali_date(valid_until),
			}
		)
	return context


def send_to_customer(customer, source, reason, scenario=None, campaign=None, extra=None, template=None):
	"""Send a campaign's or automation's message to one customer, through the messaging rules.

	`template` sends another text of the same campaign (an event reminder or thank-you),
	without a new discount code."""
	text = render_message(
		template or source.get("message") or source.get("message_template"),
		build_context(customer, source, reason, extra=extra, with_code=not template),
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


SAMPLE_EXTRA = {"occasion": "نوروز", "item": "کالای نمونه"}


def preview_text(source, customer_name="مشتری نمونه"):
	customer = {"name": customer_name, "customer_name": customer_name}
	return render_message(
		source.get("message") or source.get("message_template"),
		build_context(customer, source, reason=None, sample=True, extra=SAMPLE_EXTRA),
	)
