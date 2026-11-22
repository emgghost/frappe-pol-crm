"""
Always-on automations (Iraq): purchase triggers, daily and hourly scans, and the
queue (Mkt Scenario Run) that sends each message when it is due.

A trigger never sends directly. It queues a run with a trigger key, so a customer
gets a given automation once per event, delays are honoured, and a follow-up or a
win-back is cancelled as soon as the customer buys.
"""

import json

import frappe
from frappe.utils import add_days, add_to_date, add_years, cint, date_diff, flt, getdate, now_datetime, nowdate

from pol_crm.marketing_hub.audience import (
	CUSTOMER_FIELDS,
	dispatch_to_customer,
	get_audience,
	messaged_customers,
	points_by_customer,
	purchase_stats,
	segments_for_activity,
)
from pol_crm.marketing_hub.utils import hub_settings, issue_coupon, parse_tier_discounts, render_message, split_csv

RUN = "Mkt Scenario Run"
PURCHASE_TRIGGERS = ("FIRST_PURCHASE", "FIRST_ORDER", "SPEND_THRESHOLD", "PURCHASE_COUNT", "AFTER_PURCHASE")
# A pending run of these is dropped when the customer buys before it is sent.
STOP_ON_PURCHASE = ("FIRST_PURCHASE", "FIRST_ORDER", "CHURN", "INACTIVITY", "AT_RISK_CALL")
CLUB_TRIGGERS = ("BIRTHDAY_BY_TIER", "POINTS_USABLE", "POINTS_EXPIRY", "AT_RISK_CALL")
DAILY_LIMIT = 1000


def active_scenarios(*trigger_types):
	if not frappe.db.exists("DocType", "Mkt Scenario"):
		return []
	rows = frappe.get_all(
		"Mkt Scenario", filters={"enabled": 1, "trigger_type": ["in", list(trigger_types)]}, fields=["*"]
	)
	today = getdate(nowdate())
	return [r for r in rows if not r.get("start_date") or getdate(r.start_date) <= today]


def queue_run(scenario, customer, trigger_key, due_at=None, step="Main", reference_doctype=None, reference_name=None, coupon_code=None, context=None):
	"""Queue one message for one customer, unless this exact event was queued before."""
	key = str(trigger_key)[:140]
	if frappe.db.exists(RUN, {"scenario": scenario, "customer": customer, "trigger_key": key, "step": step}):
		return None
	doc = frappe.get_doc(
		{
			"doctype": RUN,
			"scenario": scenario,
			"customer": customer,
			"trigger_key": key,
			"step": step,
			"status": "Pending",
			"due_at": due_at or now_datetime(),
			"reference_doctype": reference_doctype,
			"reference_name": reference_name,
			"coupon_code": coupon_code,
			"context_json": json.dumps(context) if context else None,
		}
	)
	# The order or invoice that caused the run may be deleted later; that must not block the queue.
	doc.flags.ignore_links = True
	doc.insert(ignore_permissions=True)
	return doc.name


def _finish(run_name, status, result=None, coupon_code=None):
	values = {"status": status, "result": str(result or "")[:140]}
	if status == "Sent":
		values["sent_at"] = now_datetime()
	if coupon_code:
		values["coupon_code"] = coupon_code
	frappe.db.set_value(RUN, run_name, values)


# ---------------------------------------------------------------- purchase triggers
def on_sales_invoice_submit(doc, method=None):
	"""Sales Invoice on_submit: first purchase, spend and count milestones, after-purchase thanks."""
	if doc.get("is_return") or not doc.get("customer"):
		return
	try:
		_handle_purchase(doc)
	except Exception:
		frappe.log_error(title="POL CRM automation: purchase trigger failed")


def cancel_pending_on_purchase(customer):
	"""The customer bought: stop follow-ups and win-backs that have not been sent yet."""
	pending = frappe.get_all(RUN, filters={"customer": customer, "status": "Pending"}, fields=["name", "scenario", "step"])
	if not pending:
		return
	triggers = dict(
		frappe.get_all(
			"Mkt Scenario", filters={"name": ["in", list({p.scenario for p in pending})]}, fields=["name", "trigger_type"], as_list=True
		)
	)
	for run in pending:
		if run.step == "Follow-up" or triggers.get(run.scenario) in STOP_ON_PURCHASE:
			_finish(run.name, "Cancelled", "PURCHASED")


def _handle_purchase(doc):
	customer = doc.customer
	cancel_pending_on_purchase(customer)
	scenarios = active_scenarios(*PURCHASE_TRIGGERS)
	if not scenarios:
		return

	row = frappe.db.sql(
		"""select count(*), coalesce(sum(base_grand_total), 0) from `tabSales Invoice`
		where customer = %s and docstatus = 1 and is_return = 0""",
		customer,
	)
	count, total = cint(row[0][0]), flt(row[0][1])
	this_amount = flt(doc.get("base_grand_total"))
	now = now_datetime()

	for sc in scenarios:
		trigger = sc.trigger_type
		due = add_to_date(now, days=cint(sc.get("delay_days")))
		ref = {"reference_doctype": "Sales Invoice", "reference_name": doc.name}
		if trigger in ("FIRST_PURCHASE", "FIRST_ORDER") and count == 1:
			queue_run(sc.name, customer, "first", due, **ref)
		elif trigger == "SPEND_THRESHOLD":
			threshold = flt(sc.get("spend_threshold"))
			if threshold > 0 and total >= threshold > total - this_amount:
				queue_run(sc.name, customer, f"spend:{threshold:g}", due, **ref)
		elif trigger == "PURCHASE_COUNT":
			if cint(sc.get("purchase_count_target")) > 0 and count == cint(sc.purchase_count_target):
				queue_run(sc.name, customer, f"count:{count}", due, **ref)
		elif trigger == "AFTER_PURCHASE":
			if not cint(sc.get("first_purchase_only")) or count == 1:
				queue_run(sc.name, customer, f"inv:{doc.name}", due, **ref)


# ---------------------------------------------------------------- daily scans
def daily_scan():
	"""Daily: churn, at-risk, birthdays, occasions and club points."""
	for job in (roll_occasions, scan_inactive, scan_birthdays, scan_occasions, scan_points):
		try:
			job()
			frappe.db.commit()
		except Exception:
			frappe.db.rollback()
			frappe.log_error(title=f"POL CRM automation: {job.__name__} failed")
	process_due_runs()


def roll_occasions():
	"""Occasions on a fixed Gregorian date move to next year once they have passed."""
	if not frappe.db.exists("DocType", "Mkt Occasion"):
		return
	today = getdate(nowdate())
	rows = frappe.get_all(
		"Mkt Occasion", filters={"repeats_yearly": 1, "occasion_date": ["<", today]}, fields=["name", "occasion_date"]
	)
	for row in rows:
		next_date = getdate(row.occasion_date)
		while next_date < today:
			next_date = getdate(add_years(next_date, 1))
		frappe.db.set_value("Mkt Occasion", row.name, "occasion_date", next_date)


def scan_inactive():
	"""CHURN: win-back messages. AT_RISK_CALL: a reminder to call a valuable customer who stopped buying."""
	today = getdate(nowdate())
	for sc in active_scenarios("CHURN", "AT_RISK_CALL"):
		days = cint(sc.get("inactivity_days")) or (30 if sc.trigger_type == "AT_RISK_CALL" else 60)
		filters = [
			["disabled", "=", 0],
			["custom_mkt_opted_out_all", "=", 0],
			["custom_last_purchase_date", "<=", add_days(today, -days)],
		]
		tiers = split_csv(sc.get("club_tiers"))
		if tiers:
			filters.append(["loyalty_program_tier", "in", tiers])
		segments = segments_for_activity(sc.get("activity_segments"))
		if segments:
			filters.append(["custom_rfm_segment", "in", segments])

		customers = frappe.get_all(
			"Customer",
			filters=filters,
			fields=["name", "custom_last_purchase_date"],
			order_by="custom_last_purchase_date desc",
			limit_page_length=DAILY_LIMIT,
		)
		repeat = cint(sc.get("repeat_every_days"))
		max_sends = max(cint(sc.get("max_sends")), 1)
		for cust in customers:
			since = date_diff(today, cust.custom_last_purchase_date)
			cycle = min((since - days) // repeat, max_sends - 1) if repeat > 0 else 0
			queue_run(sc.name, cust.name, f"inactive:{cust.custom_last_purchase_date}:{cycle}")


def scan_birthdays():
	today = getdate(nowdate())
	for sc in active_scenarios("BIRTHDAY", "BIRTHDAY_BY_TIER"):
		target = getdate(add_days(today, cint(sc.get("delay_days"))))
		rows = frappe.db.sql(
			"""select name, loyalty_program_tier from `tabCustomer`
			where disabled = 0 and custom_birth_date is not null
			and month(custom_birth_date) = %s and day(custom_birth_date) = %s""",
			(target.month, target.day),
			as_dict=True,
		)
		tiers = set(parse_tier_discounts(sc.get("tier_discounts"))) | set(split_csv(sc.get("club_tiers")))
		for cust in rows:
			if sc.trigger_type == "BIRTHDAY_BY_TIER" and tiers and cust.loyalty_program_tier not in tiers:
				continue
			queue_run(sc.name, cust.name, f"bday:{target.year}")


def scan_occasions():
	if not frappe.db.exists("DocType", "Mkt Occasion"):
		return
	today = getdate(nowdate())
	for sc in active_scenarios("OCCASION"):
		target = add_days(today, cint(sc.get("delay_days")))
		wanted = split_csv(sc.get("occasions"))
		occasions = frappe.get_all("Mkt Occasion", filters={"enabled": 1, "occasion_date": target}, pluck="name")
		occasions = [o for o in occasions if not wanted or o in wanted]
		if not occasions:
			continue
		audience = get_audience({"last_purchase": "In the last 90 days"})
		for occasion in occasions:
			for cust in audience:
				queue_run(sc.name, cust.name, f"occasion:{occasion}:{target}", context={"occasion": occasion})


def scan_points():
	"""POINTS_USABLE: points reached the redeem level. POINTS_EXPIRY: points expire in N days."""
	today = getdate(nowdate())
	usable = active_scenarios("POINTS_USABLE")
	if usable:
		level = cint(hub_settings().points_redeem_level) or 1
		balances = {c: p for c, p in points_by_customer().items() if p >= level}
		for sc in usable:
			every = cint(sc.get("repeat_every_days")) or 14
			max_sends = cint(sc.get("max_sends"))
			for customer, points in balances.items():
				previous = frappe.get_all(
					RUN, filters={"scenario": sc.name, "customer": customer}, fields=["creation"], order_by="creation desc"
				)
				if max_sends and len(previous) >= max_sends:
					continue
				if previous and date_diff(today, previous[0].creation) < every:
					continue
				queue_run(sc.name, customer, f"points:{today}", context={"points": points})

	for sc in active_scenarios("POINTS_EXPIRY"):
		if not frappe.db.exists("DocType", "Loyalty Point Entry"):
			break
		for before in split_csv(sc.get("points_before_days")) or ["7"]:
			target = add_days(today, cint(before))
			rows = frappe.db.sql(
				"""select customer, sum(loyalty_points) from `tabLoyalty Point Entry`
				where expiry_date = %s group by customer having sum(loyalty_points) > 0""",
				target,
			)
			for customer, points in rows:
				queue_run(
					sc.name, customer, f"expiry:{target}:{before}", context={"points": cint(points), "date": str(target)}
				)


# ---------------------------------------------------------------- hourly scans
def hourly_scan():
	"""Hourly: incomplete orders, back-in-stock alerts, then everything that is due."""
	for job in (scan_incomplete_orders, scan_restock):
		try:
			job()
			frappe.db.commit()
		except Exception:
			frappe.db.rollback()
			frappe.log_error(title=f"POL CRM automation: {job.__name__} failed")
	process_due_runs()


def scan_incomplete_orders():
	"""A draft Sales Order that was started but never confirmed."""
	now = now_datetime()
	for sc in active_scenarios("INCOMPLETE_ORDER"):
		hours = cint(sc.get("delay_hours")) or 1
		drafts = frappe.get_all(
			"Sales Order",
			filters={
				"docstatus": 0,
				"customer": ["is", "set"],
				"modified": ["between", [add_to_date(now, days=-3), add_to_date(now, hours=-hours)]],
			},
			fields=["name", "customer"],
		)
		for order in drafts:
			queue_run(sc.name, order.customer, f"order:{order.name}", reference_doctype="Sales Order", reference_name=order.name)


def scan_restock():
	"""Customers on the waitlist are told when their item has stock again."""
	if not frappe.db.exists("DocType", "Mkt Stock Waitlist"):
		return
	scenarios = active_scenarios("BACK_IN_STOCK")
	waiting = frappe.get_all("Mkt Stock Waitlist", filters={"status": "Waiting"}, fields=["name", "customer", "item"])
	if not scenarios or not waiting:
		return
	stock = dict(
		frappe.db.sql(
			"select item_code, sum(actual_qty) from `tabBin` where item_code in %s group by item_code",
			(tuple({w.item for w in waiting}),),
		)
	)
	for entry in waiting:
		if flt(stock.get(entry.item)) <= 0:
			continue
		item_name = frappe.db.get_value("Item", entry.item, "item_name") or entry.item
		for sc in scenarios:
			queue_run(sc.name, entry.customer, f"stock:{entry.name}", context={"item": item_name})
		frappe.db.set_value("Mkt Stock Waitlist", entry.name, {"status": "Notified", "notified_on": now_datetime()})


# ---------------------------------------------------------------- sending
def process_due_runs(limit=300):
	if not frappe.db.exists("DocType", RUN):
		return
	due = frappe.get_all(
		RUN, filters={"status": "Pending", "due_at": ["<=", now_datetime()]}, pluck="name", order_by="due_at", limit_page_length=limit
	)
	for name in due:
		try:
			execute_run(name)
			frappe.db.commit()
		except Exception:
			frappe.db.rollback()
			frappe.log_error(title=f"POL CRM automation: run {name} failed")
			_finish(name, "Skipped", "ERROR")
			frappe.db.commit()


def execute_run(run_name):
	run = frappe.get_doc(RUN, run_name)
	sc = frappe.db.get_value("Mkt Scenario", run.scenario, "*", as_dict=True)
	if not sc or not cint(sc.enabled):
		return _finish(run.name, "Cancelled", "AUTOMATION_OFF")
	cust = frappe.db.get_value("Customer", run.customer, CUSTOMER_FIELDS, as_dict=True)
	if not cust or cint(cust.disabled):
		return _finish(run.name, "Cancelled", "NO_CUSTOMER")

	trigger = sc.trigger_type
	if trigger == "INCOMPLETE_ORDER" and frappe.db.get_value("Sales Order", run.reference_name, "docstatus") != 0:
		return _finish(run.name, "Cancelled", "ORDER_CONFIRMED")

	follow_up = run.step == "Follow-up"
	template = sc.get("followup_message") if follow_up else sc.message_template
	if trigger == "AT_RISK_CALL" and not follow_up:
		if cint(sc.get("call_reminder")):
			_create_call_reminder(sc, cust)
		if not cint(sc.get("send_message")) or not template:
			return _finish(run.name, "Sent", "CALL_REMINDER")

	ctx = json.loads(run.context_json) if run.get("context_json") else {}
	percent = parse_tier_discounts(sc.get("tier_discounts")).get(cust.loyalty_program_tier) or flt(sc.get("discount_percent"))
	code = run.coupon_code
	if percent and not code:
		code = issue_coupon(cust.name, percent, cint(sc.get("coupon_validity_days")) or 7)
	if "{points}" in (template or "") and "points" not in ctx:
		ctx["points"] = points_by_customer().get(cust.name, 0)
	ctx.update(
		name=cust.customer_name,
		customer_name=cust.customer_name,
		customer=cust,
		code=code or "",
		discount=f"{percent:g}%" if percent else "",
		days=cint(sc.get("inactivity_days")),
	)

	text = render_message(template, ctx)
	if code and code not in text:
		text = f"{text}\n{code}"

	result = dispatch_to_customer(
		cust, sc.channel or "WHATSAPP", text, scenario=sc.name, urgent=trigger == "INCOMPLETE_ORDER"
	)
	sent = result.get("status") in ("SENT", "POSTPONED")
	_finish(run.name, "Sent" if sent else "Skipped", result.get("reason") or result.get("error") or result.get("status"), code)

	if sent and not follow_up and cint(sc.get("followup_enabled")) and sc.get("followup_message"):
		queue_run(
			sc.name,
			cust.name,
			run.trigger_key,
			add_to_date(now_datetime(), days=cint(sc.get("followup_wait_days")) or 2),
			step="Follow-up",
			reference_doctype=run.reference_doctype,
			reference_name=run.reference_name,
			coupon_code=code,
			context={k: v for k, v in ctx.items() if k in ("points", "date", "item", "occasion")},
		)


def _create_call_reminder(sc, cust):
	days = cint(sc.get("inactivity_days")) or 30
	frappe.get_doc(
		{
			"doctype": "ToDo",
			"description": f"Call {cust.customer_name} ({cust.mobile_no or 'no phone'}): no purchase for {days}+ days. Automation: {sc.scenario_name}",
			"reference_type": "Customer",
			"reference_name": cust.name,
			"allocated_to": sc.owner if sc.owner not in ("Administrator", "Guest") else None,
			"date": nowdate(),
			"priority": "High",
		}
	).insert(ignore_permissions=True)


# ---------------------------------------------------------------- report
@frappe.whitelist()
def scenario_stats(scenario, days=30):
	"""Results of one automation over the last `days` days."""
	frappe.has_permission("Mkt Scenario", "read", scenario, throw=True)
	since = add_days(now_datetime(), -cint(days))
	customers = messaged_customers("scenario", scenario, since)
	converted, revenue = purchase_stats(customers, since, cint(days) + cint(hub_settings().conversion_window_days))
	return {
		"entered": len(customers),
		"converted": converted,
		"revenue": revenue,
		"pending": frappe.db.count(RUN, {"scenario": scenario, "status": "Pending"}),
		"cost": flt(
			frappe.db.sql(
				"select coalesce(sum(cost), 0) from `tabMkt Message Log` where scenario = %s and creation >= %s",
				(scenario, since),
			)[0][0]
		),
	}
