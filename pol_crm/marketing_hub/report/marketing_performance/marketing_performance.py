"""
Marketing Performance: what each campaign and automation did in the chosen dates.

Reached      customers a message was sent to
Codes        discount codes it handed out, and how many were used on an invoice
Buyers       reached customers who bought within N days of their message
Sales        what those buyers spent in that window
"""

import frappe
from frappe.utils import add_days, cint, flt, getdate, nowdate

KIND_LABEL = {"Campaign": "کمپین", "Automation": "اتوماسیون"}
CHANNEL_LABEL = {"SMS": "پیامک", "TELEGRAM": "تلگرام"}


def execute(filters=None):
	filters = frappe._dict(filters or {})
	filters.from_date = getdate(filters.from_date or add_days(nowdate(), -30))
	filters.to_date = getdate(filters.to_date or nowdate())
	filters.window_days = cint(filters.window_days) or 14

	rows = []
	if filters.kind in (None, "", "Campaign"):
		rows += [stats(filters, "campaign", c) for c in frappe.get_all("Mkt Campaign", fields=["name", "campaign_name as title", "channel"])]
	if filters.kind in (None, "", "Automation"):
		rows += [stats(filters, "scenario", s) for s in frappe.get_all("Mkt Scenario", fields=["name", "scenario_name as title", "channel"])]
	rows = [r for r in rows if r["reached"] or r["codes"]]
	rows.sort(key=lambda r: (flt(r["sales"]), r["reached"]), reverse=True)

	summary = [
		{"label": "مشتری که پیام گرفت", "value": sum(r["reached"] for r in rows), "datatype": "Int", "indicator": "Blue"},
		{"label": "کد استفاده‌شده", "value": sum(r["codes_used"] for r in rows), "datatype": "Int", "indicator": "Orange"},
		{"label": "خریدار", "value": sum(r["buyers"] for r in rows), "datatype": "Int", "indicator": "Green"},
		{"label": "فروش", "value": sum(flt(r["sales"]) for r in rows), "datatype": "Currency", "indicator": "Green"},
	]
	top = [r for r in rows if flt(r["sales"])][:8]
	chart = (
		{
			"data": {"labels": [r["title"] for r in top], "datasets": [{"name": "فروش", "values": [flt(r["sales"]) for r in top]}]},
			"type": "bar",
		}
		if top
		else None
	)
	return columns(), rows, None, chart, summary


def columns():
	return [
		{"fieldname": "title", "label": "نام", "fieldtype": "Data", "width": 220},
		{"fieldname": "kind", "label": "نوع", "fieldtype": "Data", "width": 90},
		{"fieldname": "channel", "label": "کانال", "fieldtype": "Data", "width": 80},
		{"fieldname": "reached", "label": "پیام رسید", "fieldtype": "Int", "width": 100},
		{"fieldname": "not_sent", "label": "نرسید", "fieldtype": "Int", "width": 80},
		{"fieldname": "codes", "label": "کد داده‌شده", "fieldtype": "Int", "width": 100},
		{"fieldname": "codes_used", "label": "کد استفاده‌شده", "fieldtype": "Int", "width": 110},
		{"fieldname": "buyers", "label": "خریدار", "fieldtype": "Int", "width": 90},
		{"fieldname": "sales", "label": "فروش", "fieldtype": "Currency", "width": 130},
		{"fieldname": "reference_doctype", "label": "نوع سند", "fieldtype": "Data", "hidden": 1},
		{"fieldname": "reference", "label": "سند", "fieldtype": "Dynamic Link", "options": "reference_doctype", "width": 110},
	]


def stats(filters, field, doc):
	logs = frappe.db.sql(
		f"""
		select customer, status, min(date(creation)) as first_sent
		from `tabMkt Message Log`
		where `{field}` = %(name)s and date(creation) between %(from)s and %(to)s
		group by customer, status
		""",
		{"name": doc.name, "from": filters.from_date, "to": filters.to_date},
		as_dict=True,
	)
	reached = {}
	not_sent = set()
	for log in logs:
		if log.status == "SENT":
			reached[log.customer] = min(log.first_sent, reached.get(log.customer, log.first_sent))
		elif log.status in ("FAILED", "SKIPPED"):
			not_sent.add(log.customer)

	codes = frappe.get_all(
		"Loyalty Offer",
		filters={field: doc.name, "creation": ("between", (filters.from_date, add_days(filters.to_date, 1)))},
		pluck="discount_code",
	)
	codes_used = 0
	if codes and frappe.db.has_column("Sales Invoice", "coupon_code"):
		codes_used = frappe.db.count("Sales Invoice", {"docstatus": 1, "coupon_code": ("in", codes)})

	buyers, sales = purchases_after(reached, filters.window_days)
	return {
		"title": doc.title,
		"kind": KIND_LABEL["Campaign" if field == "campaign" else "Automation"],
		"channel": CHANNEL_LABEL.get(doc.channel, doc.channel),
		"reached": len(reached),
		"not_sent": len(not_sent - set(reached)),
		"codes": len(codes),
		"codes_used": codes_used,
		"buyers": buyers,
		"sales": sales,
		"reference_doctype": "Mkt Campaign" if field == "campaign" else "Mkt Scenario",
		"reference": doc.name,
	}


def purchases_after(reached, window_days):
	"""Customers who bought within the window after their first message, and what they spent."""
	if not reached:
		return 0, 0
	rows = frappe.db.sql(
		"""
		select customer, posting_date, base_grand_total
		from `tabSales Invoice`
		where docstatus = 1 and is_return = 0 and customer in %(customers)s
			and posting_date >= %(start)s
		""",
		{"customers": list(reached), "start": min(reached.values())},
		as_dict=True,
	)
	buyers, sales = set(), 0.0
	for row in rows:
		sent = reached[row.customer]
		if sent <= getdate(row.posting_date) <= add_days(sent, window_days):
			buyers.add(row.customer)
			sales += flt(row.base_grand_total)
	return len(buyers), sales
