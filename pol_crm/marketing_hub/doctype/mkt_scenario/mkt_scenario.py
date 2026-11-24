import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt

# The field each trigger needs before the automation can be turned on.
REQUIRED = {
	"RFM_SEGMENT_CHANGE": ("target_rfm_segment", "گروه RFM"),
	"INACTIVITY": ("inactivity_days", "روز بدون خرید"),
	"PURCHASE_COUNT": ("purchase_count_target", "خرید چندم"),
	"SPEND_THRESHOLD": ("spend_threshold", "مبلغ سقف خرید"),
}


class MktScenario(Document):
	def validate(self):
		if flt(self.discount_percent) < 0 or flt(self.discount_percent) > 100:
			frappe.throw(_("درصد تخفیف باید بین ۰ و ۱۰۰ باشد."))
		if "{code}" in (self.message_template or "") and not flt(self.discount_percent):
			frappe.throw(_("متن پیام {code} دارد، ولی درصد کد تخفیف صفر است."))
		if self.send_hour is not None and not 0 <= cint(self.send_hour) <= 23:
			frappe.throw(_("ساعت ارسال باید بین ۰ و ۲۳ باشد."))
		if self.enabled and self.trigger_type in REQUIRED:
			field, label = REQUIRED[self.trigger_type]
			if not flt(self.get(field)) and not self.get(field):
				frappe.throw(_("برای روشن کردن این اتوماسیون «{0}» را پر کنید.").format(label))

	@frappe.whitelist()
	def preview(self):
		from pol_crm.marketing_hub.messages import preview_text

		return {"text": preview_text(self)}

	@frappe.whitelist()
	def send_test(self, mobile=None, chat_id=None):
		frappe.only_for(("System Manager", "Marketing Manager"))
		from pol_crm.marketing_hub.doctype.mkt_campaign.mkt_campaign import send_test_message

		return send_test_message(self, mobile, chat_id)
