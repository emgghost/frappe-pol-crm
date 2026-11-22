import frappe
from frappe.model.document import Document
from frappe.utils import flt

from pol_crm.marketing_hub import meta


class MetaAdSet(Document):
	def validate(self):
		meta.assert_editable(self, self.campaign)
		if not self.status:
			self.status = "Draft"
		objective = frappe.db.get_value("Meta Ad Campaign", self.campaign, "objective")
		rules = meta.OBJECTIVES.get(objective) or {}
		if not self.optimization_goal and rules.get("goals"):
			self.optimization_goal = rules["goals"][0]
		self.days = meta.ad_set_days(self.start_date, self.end_date)
		self.total_budget = flt(self.daily_budget) * self.days
		self.est_impressions, self.est_clicks = meta.estimate_results(self.total_budget)

	def on_update(self):
		meta.recompute_campaign_totals(self.campaign)

	def on_trash(self):
		meta.assert_editable(self, self.campaign)
		for name in frappe.get_all("Meta Ad", filters={"ad_set": self.name}, pluck="name"):
			frappe.delete_doc("Meta Ad", name, ignore_permissions=True, flags={"ignore_lock": True})

	def after_delete(self):
		meta.recompute_campaign_totals(self.campaign)

	@frappe.whitelist()
	def duplicate(self):
		self.check_permission("read")
		meta.assert_editable(self, self.campaign)
		return meta.duplicate_ad_set(self.name)

	@frappe.whitelist()
	def add_ad(self, ad_name=None):
		self.check_permission("write")
		meta.assert_editable(self, self.campaign)
		count = frappe.db.count("Meta Ad", {"ad_set": self.name})
		ctas = meta.CTAS.get(self.destination) or ["Learn More"]
		doc = frappe.get_doc(
			{
				"doctype": "Meta Ad",
				"ad_set": self.name,
				"campaign": self.campaign,
				"ad_name": ad_name or f"Ad {count + 1}",
				"cta": ctas[0],
			}
		).insert()
		return doc.name
