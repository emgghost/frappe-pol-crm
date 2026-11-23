"""
A campaign is sent once: to whom (the audience filters), what (the message and an optional
discount code) and when (now, or at the time set). Pressing Send schedules it; a job every
five minutes starts the campaigns that are due and sends them in the background.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt, get_datetime, now_datetime

from pol_crm.marketing_automation.audience import count_audience, get_audience
from pol_crm.marketing_automation.messages import preview_text, send_to_customer

EDITABLE = ("Draft",)


class MktCampaign(Document):
	def validate(self):
		if flt(self.discount_percent) < 0 or flt(self.discount_percent) > 100:
			frappe.throw(_("درصد تخفیف باید بین ۰ و ۱۰۰ باشد."))
		if "{code}" in (self.message or "") and not flt(self.discount_percent):
			frappe.throw(_("متن پیام {code} دارد، ولی درصد کد تخفیف صفر است."))
		if self.status in EDITABLE:
			self.audience_count = count_audience(self)

	@frappe.whitelist()
	def preview(self):
		"""How many customers it reaches, a few of them, and the text as one of them reads it."""
		frappe.only_for(("System Manager", "Marketing Manager"))
		sample = get_audience(self, limit=5)
		return {
			"count": count_audience(self),
			"sample": [c.customer_name or c.name for c in sample],
			"text": preview_text(self, sample[0].customer_name if sample else "مشتری نمونه"),
		}

	@frappe.whitelist()
	def send_test(self, mobile=None, chat_id=None):
		"""Send the message once to the merchant's own number or chat, outside every rule."""
		frappe.only_for(("System Manager", "Marketing Manager"))
		return send_test_message(self, mobile, chat_id)

	@frappe.whitelist()
	def schedule(self):
		frappe.only_for(("System Manager", "Marketing Manager"))
		if self.status not in EDITABLE:
			frappe.throw(_("این کمپین قبلاً ارسال یا زمان‌بندی شده است."))
		if not count_audience(self):
			frappe.throw(_("هیچ مشتری‌ای با این شرایط پیدا نشد."))
		if not self.send_at or get_datetime(self.send_at) < now_datetime():
			self.send_at = now_datetime()
		self.status = "Scheduled"
		self.save()
		if get_datetime(self.send_at) <= now_datetime():
			start_campaign(self.name)
		return self.status

	@frappe.whitelist()
	def cancel_campaign(self):
		frappe.only_for(("System Manager", "Marketing Manager"))
		if self.status != "Scheduled":
			frappe.throw(_("فقط کمپین زمان‌بندی‌شده را می‌شود لغو کرد."))
		self.status = "Cancelled"
		self.save()

	@frappe.whitelist()
	def back_to_draft(self):
		frappe.only_for(("System Manager", "Marketing Manager"))
		if self.status not in ("Scheduled", "Cancelled"):
			frappe.throw(_("کمپینی که ارسال شده را نمی‌شود دوباره ویرایش کرد."))
		self.status = "Draft"
		self.save()


def send_test_message(source, mobile=None, chat_id=None):
	from pol_crm.messaging.policy import send_plain_sms
	from pol_crm.messaging.telegram import send_telegram_message

	text = preview_text(source)
	if (source.get("channel") or "SMS") == "TELEGRAM":
		if not chat_id:
			frappe.throw(_("شناسه‌ی چت تلگرام را وارد کنید."))
		result = send_telegram_message(chat_id, text)
	else:
		from pol_crm.messaging.phone_utils import normalize_iranian_mobile

		_e164, local, valid = normalize_iranian_mobile(mobile)
		if not valid:
			frappe.throw(_("شماره‌ی موبایل معتبر نیست."))
		result = send_plain_sms(local, text)
	if not result.get("success"):
		frappe.throw(_("ارسال نشد: {0}").format(result.get("error") or ""))
	return text


def start_campaign(name):
	"""Mark the campaign as sending and hand it to a background worker."""
	frappe.db.set_value("Mkt Campaign", name, "status", "Sending")
	frappe.enqueue(
		"pol_crm.marketing_automation.doctype.mkt_campaign.mkt_campaign.send_campaign",
		queue="long",
		timeout=3600,
		name=name,
		enqueue_after_commit=True,
		now=frappe.flags.in_test,
	)


def process_due_campaigns():
	"""Every few minutes: start the scheduled campaigns whose time has come."""
	for name in frappe.get_all(
		"Mkt Campaign",
		filters={"status": "Scheduled", "send_at": ("<=", now_datetime())},
		pluck="name",
	):
		start_campaign(name)


def send_campaign(name):
	campaign = frappe.get_doc("Mkt Campaign", name)
	if campaign.status != "Sending":
		return

	counts = {"SENT": 0, "POSTPONED": 0, "SKIPPED": 0, "FAILED": 0}
	for customer in get_audience(campaign):
		try:
			result = send_to_customer(customer, campaign, reason="CAMPAIGN", campaign=campaign.name)
			status = (result or {}).get("status") or "FAILED"
		except Exception:
			frappe.log_error(title=f"Campaign {name}", message=frappe.get_traceback())
			status = "FAILED"
		counts[status if status in counts else "FAILED"] += 1
		frappe.db.commit()

	frappe.db.set_value(
		"Mkt Campaign",
		name,
		{
			"status": "Sent",
			"sent_count": counts["SENT"],
			"postponed_count": counts["POSTPONED"],
			"skipped_count": counts["SKIPPED"],
			"failed_count": counts["FAILED"],
			"sent_on": now_datetime(),
		},
	)
	frappe.db.commit()
