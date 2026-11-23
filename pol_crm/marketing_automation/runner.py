"""
Automations: messages that go out by themselves, each time something happens to a customer.

An automation says who and when through its trigger, and what through its message:
	RFM_SEGMENT_CHANGE  the customer moves into an RFM group            (right away)
	INACTIVITY          N days have passed since their last purchase    (daily, at the set hour)
	FIRST_ORDER         N days after their first purchase               (daily, or right away if 0)
	AFTER_PURCHASE      N days after any purchase                       (daily, or right away if 0)
	PURCHASE_COUNT      their Nth purchase is submitted                 (right away)
	SPEND_THRESHOLD     their total purchases pass an amount            (right away)
	BIRTHDAY            today is their birthday                         (daily, at the set hour)

Every message still goes through the messaging rules: quiet hours, the daily and weekly cap
per customer, opt-outs and test mode.
"""

from datetime import datetime

import jinja2
import frappe
from frappe.utils import add_days, cint, flt, getdate, nowdate

DAILY_TRIGGERS = ("INACTIVITY", "FIRST_ORDER", "AFTER_PURCHASE", "BIRTHDAY")
CUSTOMER_FIELDS = ["name", "customer_name", "mobile_no", "custom_telegram_chat_id"]


def render_template_string(template_str, context):
	"""Render a template string with Jinja2 syntax (e.g. {{ customer_name }})."""
	if not template_str:
		return ""
	if "{{" not in template_str and "{%" not in template_str:
		return template_str
	try:
		return jinja2.Template(template_str).render(**context)
	except Exception as e:
		frappe.logger("pol_crm").warning(f"Template rendering failed: {str(e)}")
		return template_str


def scenarios_for(trigger, **filters):
	if not frappe.db.exists("DocType", "Mkt Scenario"):
		return []
	return frappe.get_all(
		"Mkt Scenario",
		filters={"enabled": 1, "trigger_type": trigger, **filters},
		fields=["*"],
	)


def already_sent(scenario, customer, since=None):
	"""Whether this automation has already written to this customer (sent or waiting for morning)."""
	filters = {"scenario": scenario, "customer": customer, "status": ("in", ("SENT", "POSTPONED"))}
	if since:
		filters["creation"] = (">=", since)
	return bool(frappe.db.exists("Mkt Message Log", filters))


def send(scenario, customer):
	from pol_crm.marketing_automation.messages import send_to_customer

	if isinstance(customer, str):
		customer = frappe.db.get_value("Customer", customer, CUSTOMER_FIELDS, as_dict=True)
	if not customer:
		return None
	try:
		return send_to_customer(customer, scenario, reason="AUTOMATION", scenario=scenario.name)
	except Exception:
		frappe.log_error(title=f"Automation {scenario.name}", message=frappe.get_traceback())
		return None


# ---- right away


def trigger_segment_change_automations(customer_name, old_segment, new_segment):
	"""Called by the RFM calculation when a customer moves into another group."""
	for scenario in scenarios_for("RFM_SEGMENT_CHANGE", target_rfm_segment=new_segment):
		# Once per move: someone who bounces in and out of a group is not messaged every night.
		if not already_sent(scenario.name, customer_name, since=add_days(nowdate(), -30)):
			send(scenario, customer_name)


def purchase_totals(customer):
	row = frappe.db.sql(
		"""
		select count(*), coalesce(sum(base_grand_total), 0)
		from `tabSales Invoice`
		where customer = %s and docstatus = 1 and is_return = 0
		""",
		customer,
	)
	return cint(row[0][0]), flt(row[0][1])


def on_sales_invoice_submit(doc, method=None):
	"""Purchase-time automations. Runs after the invoice is saved, so it never blocks the sale."""
	if not doc.customer or doc.get("is_return"):
		return
	frappe.enqueue(
		"pol_crm.marketing_automation.runner.run_purchase_automations",
		queue="short",
		customer=doc.customer,
		invoice_total=flt(doc.base_grand_total),
		enqueue_after_commit=True,
		now=frappe.flags.in_test,
	)


def run_purchase_automations(customer, invoice_total=0):
	count, total = purchase_totals(customer)

	for scenario in scenarios_for("PURCHASE_COUNT", purchase_count_target=count):
		if not already_sent(scenario.name, customer):
			send(scenario, customer)

	before = total - flt(invoice_total)
	for scenario in scenarios_for("SPEND_THRESHOLD"):
		threshold = flt(scenario.spend_threshold)
		if threshold and before < threshold <= total and not already_sent(scenario.name, customer):
			send(scenario, customer)

	for scenario in scenarios_for("FIRST_ORDER", delay_days=0):
		if count == 1 and not already_sent(scenario.name, customer):
			send(scenario, customer)

	for scenario in scenarios_for("AFTER_PURCHASE", delay_days=0):
		send(scenario, customer)


# ---- once a day, at each automation's hour


def customers_with_invoice_on(day, which):
	"""Customers whose first / last / any submitted invoice falls on this day."""
	having = {
		"first": "min(posting_date) = %(day)s",
		"last": "max(posting_date) = %(day)s",
		"any": "sum(posting_date = %(day)s) > 0",
	}[which]
	return frappe.db.sql_list(
		f"""
		select customer from `tabSales Invoice`
		where docstatus = 1 and is_return = 0 and customer is not null
		group by customer having {having}
		""",
		{"day": day},
	)


def customers_born_on(day):
	if not frappe.db.has_column("Customer", "custom_birth_date"):
		return []
	day = getdate(day)
	return frappe.db.sql_list(
		"""
		select name from `tabCustomer`
		where disabled = 0 and custom_birth_date is not null
			and month(custom_birth_date) = %s and day(custom_birth_date) = %s
		""",
		(day.month, day.day),
	)


def due_customers(scenario, today):
	trigger = scenario.trigger_type
	if trigger == "INACTIVITY":
		return customers_with_invoice_on(add_days(today, -(cint(scenario.inactivity_days) or 60)), "last")
	if trigger == "FIRST_ORDER":
		return customers_with_invoice_on(add_days(today, -cint(scenario.delay_days)), "first")
	if trigger == "AFTER_PURCHASE":
		return customers_with_invoice_on(add_days(today, -cint(scenario.delay_days)), "any")
	if trigger == "BIRTHDAY":
		return customers_born_on(today)
	return []


def run_scenario_for_day(scenario, today):
	sent = 0
	once_since = add_days(today, -300) if scenario.trigger_type == "BIRTHDAY" else None
	for customer in due_customers(scenario, today):
		if scenario.trigger_type == "FIRST_ORDER" and already_sent(scenario.name, customer):
			continue
		if once_since and already_sent(scenario.name, customer, since=once_since):
			continue
		if send(scenario, customer):
			sent += 1
	frappe.db.set_value("Mkt Scenario", scenario.name, "last_run_on", today)
	frappe.db.commit()
	return sent


def local_now():
	from pol_crm.messaging.policy import get_messaging_settings

	import pytz

	return datetime.now(pytz.timezone(get_messaging_settings().get("timezone") or "Asia/Tehran"))


def run_daily_automations():
	"""Hourly: run each daily automation once a day, at or after its hour (Tehran time)."""
	now = local_now()
	today = now.date()
	for trigger in DAILY_TRIGGERS:
		for scenario in scenarios_for(trigger):
			if trigger in ("FIRST_ORDER", "AFTER_PURCHASE") and not cint(scenario.delay_days):
				continue  # these go out at the moment of purchase
			if scenario.last_run_on and getdate(scenario.last_run_on) >= today:
				continue
			if now.hour < cint(scenario.send_hour if scenario.send_hour is not None else 10):
				continue
			run_scenario_for_day(scenario, today)


# Kept for callers from before the daily run moved to the hourly job.
def run_inactivity_scan():
	today = local_now().date()
	for scenario in scenarios_for("INACTIVITY"):
		run_scenario_for_day(scenario, today)


def daily_automation_scan():
	run_daily_automations()
