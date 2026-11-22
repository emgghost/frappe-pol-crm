"""
Marketing Performance: every campaign, automation, Meta ad and Wafi promotion in one
table, with spend, purchases, revenue and ROAS for the chosen dates.
"""

import frappe
from frappe.utils import add_days, cint, flt, getdate, nowdate

from pol_crm.marketing_hub.audience import messaged_customers, purchase_stats
from pol_crm.marketing_hub.utils import hub_settings

CHANNEL_PLATFORM = {
	"WhatsApp": "WhatsApp",
	"WHATSAPP": "WhatsApp",
	"Instagram DM": "Instagram",
	"INSTAGRAM": "Instagram",
	"Wafi App": "Wafi App",
	"WAFI": "Wafi App",
	"SMS": "SMS",
	"Telegram": "Telegram",
	"TELEGRAM": "Telegram",
}


def execute(filters=None):
	filters = frappe._dict(filters or {})
	filters.from_date = getdate(filters.from_date or add_days(nowdate(), -30))
	filters.to_date = getdate(filters.to_date or nowdate())

	rows = []
	kinds = {
		"Campaign": campaign_rows,
		"Automation": automation_rows,
		"Meta Ad": meta_rows,
		"Wafi": wafi_rows,
	}
	for kind, loader in kinds.items():
		if filters.type and filters.type != kind:
			continue
		rows.extend(loader(filters))

	if filters.platform:
		rows = [r for r in rows if r["platform"] == filters.platform]
	if filters.status:
		rows = [r for r in rows if r["status"] == filters.status]
	for row in rows:
		row["roas"] = round(flt(row["revenue"]) / flt(row["spend"]), 2) if flt(row["spend"]) else 0
	rows.sort(key=lambda r: flt(r["revenue"]), reverse=True)

	spend = sum(flt(r["spend"]) for r in rows)
	revenue = sum(flt(r["revenue"]) for r in rows)
	purchases = sum(cint(r["purchases"]) for r in rows)
	summary = [
		{"label": "Spend (IQD)", "value": spend, "datatype": "Int", "indicator": "Orange"},
		{"label": "Purchases", "value": purchases, "datatype": "Int", "indicator": "Blue"},
		{"label": "Revenue (IQD)", "value": revenue, "datatype": "Int", "indicator": "Green"},
		{"label": "ROAS", "value": round(revenue / spend, 2) if spend else 0, "datatype": "Float", "indicator": "Green"},
	]
	top = [r for r in rows if flt(r["revenue"]) > 0][:8]
	chart = None
	if top:
		chart = {
			"data": {"labels": [r["title"] for r in top], "datasets": [{"name": "Revenue (IQD)", "values": [flt(r["revenue"]) for r in top]}]},
			"type": "bar",
			"colors": ["#FF8C00"],
		}
	return columns(), rows, None, chart, summary


def columns():
	return [
		{"fieldname": "title", "label": "Name", "fieldtype": "Data", "width": 220},
		{"fieldname": "type", "label": "Type", "fieldtype": "Data", "width": 100},
		{"fieldname": "platform", "label": "Platform", "fieldtype": "Data", "width": 110},
		{"fieldname": "status", "label": "Status", "fieldtype": "Data", "width": 100},
		{"fieldname": "reached", "label": "Reached", "fieldtype": "Int", "width": 100},
		{"fieldname": "spend", "label": "Spend (IQD)", "fieldtype": "Int", "width": 120},
		{"fieldname": "purchases", "label": "Purchases", "fieldtype": "Int", "width": 100},
		{"fieldname": "revenue", "label": "Revenue (IQD)", "fieldtype": "Int", "width": 130},
		{"fieldname": "roas", "label": "ROAS", "fieldtype": "Float", "width": 80},
		{"fieldname": "reference_doctype", "label": "Document Type", "fieldtype": "Data", "hidden": 1},
		{"fieldname": "reference", "label": "Document", "fieldtype": "Dynamic Link", "options": "reference_doctype", "width": 130},
	]


def row(title, kind, platform, status, reached, spend, purchases, revenue, doctype, name):
	return {
		"title": title,
		"type": kind,
		"platform": platform,
		"status": status,
		"reached": cint(reached),
		"spend": flt(spend),
		"purchases": cint(purchases),
		"revenue": flt(revenue),
		"reference_doctype": doctype,
		"reference": name,
	}


def campaign_rows(filters):
	"""Campaigns sent or scheduled inside the dates, plus drafts."""
	out = []
	campaigns = frappe.get_all(
		"Mkt Campaign",
		fields=["name", "campaign_name", "channel", "status", "sent_at", "scheduled_at", "sent_count", "cost", "creation"],
	)
	for c in campaigns:
		when = getdate(c.sent_at or c.scheduled_at or c.creation)
		if not (filters.from_date <= when <= filters.to_date):
			continue
		bought, revenue = (0, 0)
		if c.sent_at:
			bought, revenue = purchase_stats(messaged_customers("campaign", c.name), c.sent_at)
		out.append(
			row(c.campaign_name, "Campaign", CHANNEL_PLATFORM.get(c.channel, c.channel), c.status, c.sent_count, c.cost, bought, revenue, "Mkt Campaign", c.name)
		)
	return out


def automation_rows(filters):
	"""Automations by the messages they sent inside the dates."""
	out = []
	window = cint(hub_settings().conversion_window_days) or 14
	span = (filters.to_date - filters.from_date).days + window
	for sc in frappe.get_all("Mkt Scenario", fields=["name", "scenario_name", "channel", "enabled"]):
		logs = frappe.db.sql(
			"""select count(distinct customer), coalesce(sum(cost), 0) from `tabMkt Message Log`
			where scenario = %s and status = 'SENT' and date(creation) between %s and %s""",
			(sc.name, filters.from_date, filters.to_date),
		)
		reached, cost = cint(logs[0][0]), flt(logs[0][1])
		bought, revenue = (0, 0)
		if reached:
			bought, revenue = purchase_stats(messaged_customers("scenario", sc.name, filters.from_date), filters.from_date, span)
		out.append(
			row(sc.scenario_name, "Automation", CHANNEL_PLATFORM.get(sc.channel, sc.channel), "Running" if sc.enabled else "Stopped", reached, cost, bought, revenue, "Mkt Scenario", sc.name)
		)
	return out


def meta_rows(filters):
	"""Meta ad campaigns whose ad sets run inside the dates (Pro plan)."""
	if hub_settings().plan != "Pro":
		return []
	out = []
	for c in frappe.get_all(
		"Meta Ad Campaign", fields=["name", "campaign_name", "status", "spend", "impressions", "purchases", "revenue", "creation"]
	):
		sets = frappe.get_all(
			"Meta Ad Set", filters={"campaign": c.name}, fields=["start_date", "end_date", "placement_facebook", "placement_instagram"]
		)
		starts = [getdate(s.start_date) for s in sets if s.start_date] or [getdate(c.creation)]
		ends = [getdate(s.end_date) for s in sets if s.end_date] or starts
		if min(starts) > filters.to_date or max(ends) < filters.from_date:
			continue
		platform = "Instagram" if sets and not any(cint(s.placement_facebook) for s in sets) else "Facebook"
		out.append(row(c.campaign_name, "Meta Ad", platform, c.status, c.impressions, c.spend, c.purchases, c.revenue, "Meta Ad Campaign", c.name))
	return out


def wafi_rows(filters):
	"""Paid Wafi promotions requested inside the dates."""
	out = []
	for doctype, title_field, reach_field in (
		("Wafi Ad", "ad_title", "views"),
		("Wafi Offer", "offer_title", "views"),
		("Wafi Promote Request", "request_title", None),
		("Wafi Notification", "notification_title", None),
	):
		fields = ["name", title_field, "status", "total_price", "paid", "creation"] + ([reach_field] if reach_field else [])
		for d in frappe.get_all(doctype, fields=fields):
			if not (filters.from_date <= getdate(d.creation) <= filters.to_date):
				continue
			out.append(
				row(d.get(title_field), "Wafi", "Wafi App", d.status, d.get(reach_field) if reach_field else 0, d.total_price if cint(d.paid) else 0, 0, 0, doctype, d.name)
			)
	return out
