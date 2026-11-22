"""
Mkt Campaign: a one-time send to existing customers (All Customers, By Segment,
Retention, Event Invitation) on WhatsApp, Instagram DM, Wafi App, SMS or Telegram.
"""

import frappe
from frappe.model.document import Document
from frappe.utils import add_to_date, cint, flt, format_datetime, get_datetime, get_url, now_datetime

from pol_crm.marketing_hub import wallet
from pol_crm.marketing_hub.audience import (
	bought_since,
	dispatch_to_customer,
	get_audience,
	get_customers,
	messaged_customers,
	purchase_stats,
)
from pol_crm.marketing_hub.utils import (
	ACTIVITY_SEGMENTS,
	CHANNEL_CODES,
	IRAQ_GOVERNORATES,
	hub_settings,
	issue_coupon,
	render_message,
	require_club,
	split_csv,
)

FILTER_TYPES = ("All Customers", "Event Invitation")
REPEAT_GAP_DAYS = 2


class MktCampaign(Document):
	def validate(self):
		if not self.status:
			self.status = "Draft"
		tiers = split_csv(self.club_tiers) if self.campaign_type in ("By Segment", "Retention") else []
		activities = split_csv(self.activity_segments) if self.campaign_type == "By Segment" else []

		if self.campaign_type == "Retention":
			require_club(frappe._("Retention campaigns"))
			if not tiers:
				frappe.throw(frappe._("Pick at least one club tier for a Retention campaign."))
		elif tiers:
			require_club(frappe._("Club tiers"))
		if self.campaign_type == "By Segment" and not (tiers or activities):
			frappe.throw(frappe._("Pick at least one activity or club tier."))

		unknown = [a for a in activities if a not in ACTIVITY_SEGMENTS]
		if unknown:
			frappe.throw(frappe._("Unknown activity: {0}. Use: {1}").format(", ".join(unknown), ", ".join(ACTIVITY_SEGMENTS)))
		unknown = [g for g in split_csv(self.governorates) if g not in IRAQ_GOVERNORATES]
		if unknown:
			frappe.throw(frappe._("Unknown governorate: {0}").format(", ".join(unknown)))

		if self.campaign_type == "Event Invitation" and not (self.event_name and self.event_datetime):
			frappe.throw(frappe._("An event invitation needs the event name and its date and time."))
		if self.offer == "Discount" and flt(self.discount_percent) <= 0:
			frappe.throw(frappe._("Enter the discount percentage."))
		if self.content_type != "Message" and not self.media:
			frappe.throw(frappe._("Attach the photo or video."))

		try:
			self.estimated_recipients = len(self.get_recipients())
		except Exception:
			frappe.log_error(title="Mkt Campaign audience estimate failed")

	# ------------------------------------------------------------------ audience
	def audience_filters(self):
		f = {
			"governorates": split_csv(self.governorates),
			"skip_recent_days": hub_settings().skip_recent_days if cint(self.skip_recently_messaged) else 0,
		}
		if self.campaign_type in FILTER_TYPES:
			f.update(
				last_purchase=self.last_purchase,
				purchase_count=self.purchase_count,
				new_customers_only=self.new_customers_only,
				min_spend=self.min_spend,
			)
		elif self.campaign_type == "By Segment":
			f.update(activity_segments=split_csv(self.activity_segments), club_tiers=split_csv(self.club_tiers))
		elif self.campaign_type == "Retention":
			f.update(club_tiers=split_csv(self.club_tiers))
		return f

	def get_recipients(self):
		return get_audience(self.audience_filters())

	def message_context(self, cust):
		ctx = {
			"name": cust.get("customer_name"),
			"customer_name": cust.get("customer_name"),
			"discount": f"{flt(self.discount_percent):g}%" if self.offer == "Discount" else "",
			"code": "",
		}
		if self.campaign_type == "Event Invitation":
			ctx.update(
				event=self.event_name,
				place=self.event_place or "",
				date=format_datetime(self.event_datetime, "d MMM yyyy") if self.event_datetime else "",
				time=format_datetime(self.event_datetime, "HH:mm") if self.event_datetime else "",
			)
		return ctx

	def unit_price(self):
		return flt(hub_settings().whatsapp_message_price) if CHANNEL_CODES.get(self.channel) == "WHATSAPP" else 0

	def ensure_wallet_covers(self, count):
		cost = self.unit_price() * count
		if cost and not wallet.can_pay(cost):
			frappe.throw(
				frappe._("Sending {0} WhatsApp messages costs {1} IQD but the Marketing Wallet has {2} IQD.").format(
					count, f"{cost:,.0f}", f"{wallet.get_balance()['total']:,.0f}"
				),
				title=frappe._("Not enough wallet balance"),
			)

	# ------------------------------------------------------------------ actions
	@frappe.whitelist()
	def preview_audience(self):
		self.check_permission("read")
		recipients = self.get_recipients()
		return {
			"count": len(recipients),
			"sample": [r.customer_name for r in recipients[:10]],
			"cost": self.unit_price() * len(recipients),
			"wallet": wallet.get_balance()["total"],
			"limit": cint(hub_settings().max_recipients_per_send),
		}

	@frappe.whitelist()
	def send_now(self):
		self.check_permission("write")
		if self.status not in ("Draft", "Scheduled", "Failed"):
			frappe.throw(frappe._("This campaign is already {0}.").format(self.status))
		recipients = self.get_recipients()
		if not recipients:
			frappe.throw(frappe._("No customers match this audience."))
		self.ensure_wallet_covers(len(recipients))
		self.db_set({"status": "Sending", "failure_reason": None})
		frappe.enqueue(
			"pol_crm.marketing_hub.doctype.mkt_campaign.mkt_campaign.run_campaign",
			queue="long",
			timeout=3600,
			campaign=self.name,
			enqueue_after_commit=True,
		)
		return {"recipients": len(recipients)}

	@frappe.whitelist()
	def schedule(self):
		self.check_permission("write")
		if self.status not in ("Draft", "Failed", "Cancelled"):
			frappe.throw(frappe._("This campaign is already {0}.").format(self.status))
		if not self.scheduled_at or get_datetime(self.scheduled_at) <= now_datetime():
			frappe.throw(frappe._("Set a schedule time in the future first."))
		self.ensure_wallet_covers(len(self.get_recipients()))
		self.db_set({"status": "Scheduled", "failure_reason": None})

	@frappe.whitelist()
	def cancel_schedule(self):
		self.check_permission("write")
		if self.status != "Scheduled":
			frappe.throw(frappe._("Only a scheduled campaign can be cancelled."))
		self.db_set("status", "Cancelled")

	@frappe.whitelist()
	def refresh_results(self):
		self.check_permission("read")
		if not self.sent_at:
			return {}
		customers = messaged_customers("campaign", self.name)
		bought, revenue = purchase_stats(customers, self.sent_at)
		self.db_set({"purchases_after": bought, "revenue_after": revenue}, update_modified=False)
		return {"recipients": len(customers), "purchases_after": bought, "revenue_after": revenue, "cost": flt(self.cost)}


def run_campaign(campaign, step="main"):
	"""Send one step of a campaign: main, repeat, reminder or thanks."""
	doc = frappe.get_doc("Mkt Campaign", campaign)
	try:
		_send_step(doc, step)
	except Exception:
		frappe.db.rollback()
		frappe.log_error(title=f"Mkt Campaign {campaign} failed ({step})")
		if step == "main":
			doc.db_set({"status": "Failed", "failure_reason": frappe.get_traceback()[-900:]})
	frappe.db.commit()


def _send_step(doc, step):
	template = {"reminder": doc.reminder_message, "thanks": doc.thanks_message}.get(step, doc.message)
	if step == "main":
		recipients = doc.get_recipients()
	else:
		names = set(messaged_customers("campaign", doc.name))
		if step == "repeat":
			names -= bought_since(names, doc.sent_at)
		recipients = get_customers(names)

	price = doc.unit_price()
	if price and not wallet.can_pay(price * len(recipients)):
		if step == "main":
			doc.db_set({"status": "Failed", "failure_reason": "Not enough Marketing Wallet balance for this send."})
		return

	media_url = get_url(doc.media) if doc.media and doc.content_type != "Message" and step in ("main", "repeat") else None
	wants_code = doc.offer == "Discount" and "{code}" in (template or "")
	sent = skipped = 0
	for cust in recipients:
		ctx = doc.message_context(cust)
		if wants_code:
			ctx["code"] = issue_coupon(cust.name, doc.discount_percent) or ""
		result = dispatch_to_customer(
			cust,
			doc.channel,
			render_message(template, ctx),
			media_url=media_url,
			campaign=doc.name,
			charge=False,
			skip_cap=step != "main",
		)
		if result.get("status") == "SENT":
			sent += 1
		elif result.get("status") != "POSTPONED":
			skipped += 1

	cost = price * sent
	if cost:
		wallet.charge(cost, f"WhatsApp - {doc.campaign_name} ({sent} messages)", "Mkt Campaign", doc.name)

	now = now_datetime()
	if step == "main":
		values = {
			"status": "Sent",
			"sent_at": now,
			"last_send_at": now,
			"recipients_count": len(recipients),
			"sent_count": sent,
			"skipped_count": skipped,
			"cost": cost,
		}
	else:
		values = {"sent_count": cint(doc.sent_count) + sent, "cost": flt(doc.cost) + cost, "last_send_at": now}
		if step == "repeat":
			values["repeats_done"] = cint(doc.repeats_done) + 1
		else:
			values[f"{step}_sent"] = 1
	doc.db_set(values)

	if step == "main" and cint(doc.also_create_meta_ad) and not doc.meta_ad_campaign and hub_settings().plan == "Pro":
		from pol_crm.marketing_hub.meta import create_draft_from_message

		doc.db_set("meta_ad_campaign", create_draft_from_message(doc.campaign_name, doc.message, doc.media))


def process_campaigns():
	"""Every 10 minutes: send scheduled campaigns, event reminders and thank-yous, and repeat sends."""
	if not frappe.db.exists("DocType", "Mkt Campaign"):
		return
	now = now_datetime()

	for name in frappe.get_all("Mkt Campaign", filters={"status": "Scheduled", "scheduled_at": ["<=", now]}, pluck="name"):
		frappe.db.set_value("Mkt Campaign", name, "status", "Sending")
		frappe.db.commit()
		run_campaign(name)

	events = frappe.get_all(
		"Mkt Campaign",
		filters={"status": "Sent", "campaign_type": "Event Invitation", "event_datetime": ["is", "set"]},
		fields=["name", "event_datetime", "reminder_enabled", "reminder_sent", "thanks_enabled", "thanks_sent"],
	)
	for ev in events:
		when = get_datetime(ev.event_datetime)
		if ev.reminder_enabled and not ev.reminder_sent and add_to_date(when, days=-1) <= now < when:
			run_campaign(ev.name, "reminder")
		if ev.thanks_enabled and not ev.thanks_sent and add_to_date(when, days=1) <= now < add_to_date(when, days=4):
			run_campaign(ev.name, "thanks")

	repeats = frappe.get_all(
		"Mkt Campaign",
		filters={
			"status": "Sent",
			"campaign_type": ["!=", "Event Invitation"],
			"send_times": ["in", ["2", "3"]],
			"last_send_at": ["<=", add_to_date(now, days=-REPEAT_GAP_DAYS)],
		},
		fields=["name", "send_times", "repeats_done"],
	)
	for row in repeats:
		if cint(row.repeats_done) < cint(row.send_times) - 1:
			run_campaign(row.name, "repeat")
