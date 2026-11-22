"""
Who gets a message: turns the merchant's audience choices into a list of customers,
sends to one customer on any channel, and measures purchases afterwards.
"""

import frappe
from frappe.utils import add_days, cint, flt, getdate, now_datetime, nowdate

from pol_crm.marketing_hub.utils import ACTIVITY_SEGMENTS, CHANNEL_CODES, hub_settings, split_csv

# label -> (kind, days): "within" = bought in the last N days, "not" = no purchase for N+ days
LAST_PURCHASE = {
	"In the last 7 days": ("within", 7),
	"In the last 30 days": ("within", 30),
	"In the last 90 days": ("within", 90),
	"Not in 30+ days": ("not", 30),
	"Not in 45+ days": ("not", 45),
	"Not in 60+ days": ("not", 60),
}

PURCHASE_COUNT = {
	"Bought once": ("=", 1),
	"More than once": (">=", 2),
	"5+ times": (">=", 5),
}

CUSTOMER_FIELDS = [
	"name",
	"customer_name",
	"mobile_no",
	"disabled",
	"loyalty_program_tier",
	"custom_rfm_segment",
	"custom_last_purchase_date",
	"custom_governorate",
	"custom_telegram_chat_id",
	"custom_instagram_user_id",
	"custom_instagram_last_inbound",
	"custom_wafi_user_id",
]


def segments_for_activity(labels):
	"""['Very Active', 'New Lead'] -> RFM segment codes."""
	out = []
	for label in split_csv(labels):
		out.extend(ACTIVITY_SEGMENTS.get(label, []))
	return out


def build_customer_filters(f, today=None):
	"""Audience choices -> Frappe filters on Customer. Pure, so it can be tested without a site."""
	today = today or nowdate()
	filters = [["disabled", "=", 0], ["custom_mkt_opted_out_all", "=", 0]]

	rule = LAST_PURCHASE.get(f.get("last_purchase"))
	if rule:
		kind, days = rule
		filters.append(["custom_last_purchase_date", ">=" if kind == "within" else "<=", add_days(today, -days)])

	count_rule = PURCHASE_COUNT.get(f.get("purchase_count"))
	if count_rule:
		filters.append(["custom_paid_invoices_count", count_rule[0], count_rule[1]])

	if flt(f.get("min_spend")) > 0:
		filters.append(["custom_total_spent", ">=", flt(f.get("min_spend"))])

	governorates = split_csv(f.get("governorates"))
	if governorates:
		filters.append(["custom_governorate", "in", governorates])

	segments = segments_for_activity(f.get("activity_segments"))
	if segments:
		filters.append(["custom_rfm_segment", "in", segments])

	tiers = split_csv(f.get("club_tiers"))
	if tiers:
		filters.append(["loyalty_program_tier", "in", tiers])

	return filters


def recently_messaged(days):
	"""Customers who already got a marketing message in the last `days` days."""
	if cint(days) <= 0:
		return set()
	return set(
		frappe.get_all(
			"Mkt Message Log",
			filters={"status": "SENT", "category": "marketing", "creation": [">=", add_days(now_datetime(), -cint(days))]},
			pluck="customer",
			distinct=True,
		)
	)


def first_time_buyers(days=30):
	"""Customers whose first invoice is at most `days` days old."""
	rows = frappe.db.sql(
		"""select customer from `tabSales Invoice`
		where docstatus = 1 and is_return = 0
		group by customer having min(posting_date) >= %s""",
		add_days(nowdate(), -cint(days)),
	)
	return {row[0] for row in rows}


def get_audience(f, limit=None):
	"""Customers matching the audience choices, most recent buyers first, capped at the send limit."""
	limit = cint(limit) or cint(hub_settings().max_recipients_per_send) or 1000
	skip = recently_messaged(f.get("skip_recent_days"))
	new_only = first_time_buyers(30) if cint(f.get("new_customers_only")) else None
	post_filtered = bool(skip) or new_only is not None

	rows = frappe.get_all(
		"Customer",
		filters=build_customer_filters(f),
		fields=CUSTOMER_FIELDS,
		order_by="custom_last_purchase_date desc",
		limit_page_length=limit * 5 if post_filtered else limit,
	)
	if post_filtered:
		rows = [r for r in rows if r.name not in skip and (new_only is None or r.name in new_only)]
	return rows[:limit]


def get_customers(names):
	if not names:
		return []
	return frappe.get_all("Customer", filters={"name": ["in", list(names)], "disabled": 0}, fields=CUSTOMER_FIELDS)


def dispatch_to_customer(cust, channel, text, media_url=None, scenario=None, campaign=None, charge=True, skip_cap=False, urgent=False):
	"""Send one message to one customer through the policy layer (opt-out, quiet hours, caps, log)."""
	from pol_crm.messaging.policy import send_marketing_message

	code = CHANNEL_CODES.get(channel, channel)
	kwargs = {
		"customer": cust.get("name"),
		"text": text,
		"channel": code,
		"category": "marketing",
		"scenario": scenario,
		"campaign": campaign,
		"media_url": media_url,
		"charge": charge,
		"skip_cap": skip_cap,
		"urgent": urgent,
	}
	if code == "TELEGRAM":
		kwargs["telegram_chat_id"] = cust.get("custom_telegram_chat_id")
	elif code == "INSTAGRAM":
		kwargs["recipient_id"] = cust.get("custom_instagram_user_id")
		kwargs["ig_last_inbound"] = cust.get("custom_instagram_last_inbound") or ""
	elif code == "WAFI":
		kwargs["recipient_id"] = cust.get("custom_wafi_user_id") or cust.get("mobile_no")
	else:
		kwargs["phone"] = cust.get("mobile_no")
	return send_marketing_message(**kwargs)


def messaged_customers(fieldname, value, since=None):
	"""Customers a campaign or automation reached (sent or waiting for quiet hours to end)."""
	filters = {fieldname: value, "status": ["in", ["SENT", "POSTPONED"]]}
	if since:
		filters["creation"] = [">=", since]
	return frappe.get_all("Mkt Message Log", filters=filters, pluck="customer", distinct=True)


def purchase_stats(customers, since, window_days=None):
	"""(customers who bought, revenue) among `customers` from `since`, within the conversion window."""
	customers = [c for c in set(customers or []) if c]
	if not customers or not since:
		return 0, 0.0
	window = cint(window_days) or cint(hub_settings().conversion_window_days) or 14
	start = getdate(since)
	row = frappe.db.sql(
		"""select count(distinct customer), coalesce(sum(base_grand_total), 0)
		from `tabSales Invoice`
		where docstatus = 1 and is_return = 0 and customer in %s
		and posting_date between %s and %s""",
		(tuple(customers), start, add_days(start, window)),
	)
	return cint(row[0][0]), flt(row[0][1])


def bought_since(customers, since):
	"""Subset of `customers` with an invoice on or after `since`."""
	customers = [c for c in set(customers or []) if c]
	if not customers or not since:
		return set()
	rows = frappe.db.sql(
		"""select distinct customer from `tabSales Invoice`
		where docstatus = 1 and is_return = 0 and customer in %s and posting_date >= %s""",
		(tuple(customers), getdate(since)),
	)
	return {row[0] for row in rows}


def points_by_customer():
	"""Usable loyalty points per customer (ERPNext Loyalty Point Entry)."""
	if not frappe.db.exists("DocType", "Loyalty Point Entry"):
		return {}
	rows = frappe.db.sql(
		"""select customer, sum(loyalty_points) from `tabLoyalty Point Entry`
		where expiry_date >= %s group by customer having sum(loyalty_points) > 0""",
		nowdate(),
	)
	return {row[0]: cint(row[1]) for row in rows}
