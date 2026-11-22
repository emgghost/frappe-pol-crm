import frappe
from frappe.model.document import Document

from pol_crm.marketing_hub import meta, meta_api
from pol_crm.marketing_hub.utils import require_pro


class MetaAdCampaign(Document):
	def validate(self):
		require_pro()
		if not self.status:
			self.status = "Draft"

	def on_trash(self):
		for name in frappe.get_all("Meta Ad Set", filters={"campaign": self.name}, pluck="name"):
			frappe.delete_doc("Meta Ad Set", name, ignore_permissions=True, flags={"ignore_lock": True})

	def _set_status(self, status, reason=None):
		self.db_set({"status": status, "rejection_reason": reason})
		meta.set_tree_status(self.name, status)

	@frappe.whitelist()
	def get_tree(self):
		"""Campaign -> ad sets -> ads, plus what still blocks publishing."""
		self.check_permission("read")
		ad_sets = frappe.get_all(
			"Meta Ad Set",
			filters={"campaign": self.name},
			fields=["name", "ad_set_name", "daily_budget", "days", "start_date", "end_date", "status"],
			order_by="creation",
		)
		for row in ad_sets:
			row["ads"] = frappe.get_all(
				"Meta Ad", filters={"ad_set": row.name}, fields=["name", "ad_name", "format", "source", "status"], order_by="creation"
			)
		return {"ad_sets": ad_sets, "issues": meta.campaign_issues(self.name)}

	@frappe.whitelist()
	def publish(self):
		self.check_permission("write")
		require_pro()
		if self.status not in ("Draft", "Rejected"):
			frappe.throw(frappe._("This campaign is already {0}.").format(self.status))
		issues = meta.campaign_issues(self.name)
		if issues:
			frappe.throw("<br>".join(issues), title=frappe._("Fix these before publishing"))
		meta.recompute_campaign_totals(self.name)
		sent = meta_api.is_configured()
		if sent:
			try:
				meta_api.push_campaign(self.name)
			except meta_api.MetaError as e:
				frappe.throw(str(e), title=frappe._("Meta did not accept the campaign"))
		self._set_status("In Review")
		return {"sent_to_meta": sent}

	def _deliver(self, active):
		try:
			meta_api.set_delivery(self.name, active)
		except meta_api.MetaError as e:
			frappe.throw(str(e), title=frappe._("Meta"))

	@frappe.whitelist()
	def pause(self):
		self.check_permission("write")
		if self.status != "Active":
			frappe.throw(frappe._("Only an active campaign can be paused."))
		self._deliver(False)
		self._set_status("Paused")

	@frappe.whitelist()
	def resume(self):
		self.check_permission("write")
		if self.status != "Paused":
			frappe.throw(frappe._("Only a paused campaign can be resumed."))
		issues = meta.campaign_issues(self.name)
		if issues:
			frappe.throw("<br>".join(issues), title=frappe._("Fix these before resuming"))
		self._deliver(True)
		self._set_status("Active")

	@frappe.whitelist()
	def mark_active(self):
		"""Meta approved the campaign. Recorded by an administrator until the Meta sync exists."""
		frappe.only_for("System Manager")
		if self.status != "In Review":
			frappe.throw(frappe._("Only a campaign in review can be approved."))
		self._set_status("Active")

	@frappe.whitelist()
	def reject(self, reason=None):
		frappe.only_for("System Manager")
		if self.status not in ("In Review", "Active"):
			frappe.throw(frappe._("Only a campaign in review or active can be rejected."))
		self._set_status("Rejected", reason)

	@frappe.whitelist()
	def duplicate(self):
		self.check_permission("read")
		return meta.duplicate_campaign(self.name)

	@frappe.whitelist()
	def add_ad_set(self, ad_set_name=None):
		self.check_permission("write")
		rules = meta.OBJECTIVES.get(self.objective) or meta.OBJECTIVES["Engagement"]
		count = frappe.db.count("Meta Ad Set", {"campaign": self.name})
		doc = frappe.get_doc(
			{
				"doctype": "Meta Ad Set",
				"campaign": self.name,
				"ad_set_name": ad_set_name or f"Ad set {count + 1}",
				"destination": rules["destinations"][0],
				"start_date": frappe.utils.nowdate(),
				"end_date": frappe.utils.add_days(frappe.utils.nowdate(), 7),
			}
		).insert()
		return doc.name
