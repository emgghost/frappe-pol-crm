import frappe
from frappe.utils import cint

from pol_crm.marketing_hub import wafi


class WafiPromoteRequest(wafi.WafiReviewDocument):
	title_fieldname = "request_title"

	def features(self):
		return [f for f in wafi.PROMOTE_PRICES if cint(self.get(f))]

	def validate_rules(self):
		if not self.features():
			frappe.throw(frappe._("Turn on at least one visibility feature."))
		days = wafi.inclusive_days(self.start_date, self.end_date)
		if days < wafi.PROMOTE_MIN_DAYS:
			frappe.throw(frappe._("Minimum booking is 1 week."))
		for feature in self.features():
			if feature in wafi.PROMOTE_CAPACITY:
				self._check_capacity(feature)

	def _check_capacity(self, feature):
		"""Top Search, Category and Map have a few slots per business category."""
		others = frappe.get_all(
			"Wafi Promote Request",
			filters={
				"name": ["!=", self.name or ""],
				"business_category": self.business_category,
				feature: 1,
				"status": ["in", wafi.ACTIVE_STATUSES],
			},
			fields=["start_date", "end_date"],
		)
		taken = sum(
			1 for o in others if wafi.ranges_overlap(self.start_date, self.end_date, o.start_date, o.end_date)
		)
		if taken >= wafi.PROMOTE_CAPACITY[feature]:
			frappe.throw(
				frappe._("{0} is full for {1} in these dates.").format(wafi.PROMOTE_LABELS[feature], self.business_category)
			)

	def compute_price(self):
		days = wafi.inclusive_days(self.start_date, self.end_date)
		self.weeks, self.weekly_rate, total = wafi.promote_price(self.features(), days)
		return total
