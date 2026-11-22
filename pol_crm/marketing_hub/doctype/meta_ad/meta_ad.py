import frappe
from frappe.model.document import Document

from pol_crm.marketing_hub import meta


class MetaAd(Document):
	def validate(self):
		self.campaign = frappe.db.get_value("Meta Ad Set", self.ad_set, "campaign")
		meta.assert_editable(self, self.campaign)
		if not self.status:
			self.status = "Draft"
		if len(self.get("cards") or []) > 10:
			frappe.throw(frappe._("A carousel can have at most 10 cards."))

	def on_trash(self):
		meta.assert_editable(self, self.campaign)

	@frappe.whitelist()
	def get_issues(self):
		self.check_permission("read")
		return meta.ad_issues(self, frappe.get_doc("Meta Ad Set", self.ad_set))

	@frappe.whitelist()
	def duplicate(self):
		self.check_permission("read")
		meta.assert_editable(self, self.campaign)
		return meta.duplicate_ad(self.name)
