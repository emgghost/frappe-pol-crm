"""
Who a campaign goes to. The filters read the RFM fields the nightly calculation keeps on
each Customer, so picking an audience is one query and never walks the invoices.
"""

import frappe
from frappe.utils import add_days, cint, flt, nowdate

# How a campaign narrows customers by their last purchase.
ANY_TIME = "ANY_TIME"
BOUGHT_WITHIN = "BOUGHT_WITHIN"
NOT_BOUGHT_WITHIN = "NOT_BOUGHT_WITHIN"


def channel_filter(channel):
	"""A customer can only be reached on a channel they have an address for."""
	if channel == "TELEGRAM":
		return ["custom_telegram_chat_id", "is", "set"]
	return ["mobile_no", "is", "set"]


def audience_filters(doc):
	"""Customer filters for a campaign (or anything with the same audience fields)."""
	channel = doc.get("channel") or "SMS"
	filters = [
		["disabled", "=", 0],
		["custom_mkt_opted_out_all", "!=", 1],
		channel_filter(channel),
	]
	if channel == "SMS":
		filters.append(["custom_mkt_sms_opted_out", "!=", 1])

	segments = [row.get("segment") for row in (doc.get("segments") or []) if row.get("segment")]
	if segments:
		filters.append(["custom_rfm_segment", "in", segments])

	if doc.get("customer_group"):
		filters.append(["customer_group", "=", doc.get("customer_group")])

	days = cint(doc.get("last_purchase_days"))
	if doc.get("last_purchase") == BOUGHT_WITHIN and days:
		filters.append(["custom_last_purchase_date", ">=", add_days(nowdate(), -days)])
	elif doc.get("last_purchase") == NOT_BOUGHT_WITHIN and days:
		filters.append(["custom_last_purchase_date", "<", add_days(nowdate(), -days)])

	if cint(doc.get("min_purchase_count")):
		filters.append(["custom_paid_invoices_count", ">=", cint(doc.get("min_purchase_count"))])

	if flt(doc.get("min_total_spent")):
		filters.append(["custom_total_spent", ">=", flt(doc.get("min_total_spent"))])

	return filters


def get_audience(doc, limit=None):
	return frappe.get_all(
		"Customer",
		filters=audience_filters(doc),
		fields=["name", "customer_name", "mobile_no", "custom_telegram_chat_id"],
		order_by="name asc",
		limit=limit,
	)


def count_audience(doc):
	return frappe.db.count("Customer", filters=audience_filters(doc))
