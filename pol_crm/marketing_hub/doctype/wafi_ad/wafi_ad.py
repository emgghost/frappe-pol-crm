import frappe

from pol_crm.marketing_hub import wafi


class WafiAd(wafi.WafiReviewDocument):
	title_fieldname = "ad_title"

	def date_range(self):
		starts = [row.start_date for row in self.placements if row.start_date]
		ends = [row.end_date for row in self.placements if row.end_date]
		return (min(starts) if starts else None, max(ends) if ends else None)

	def validate_rules(self):
		if not self.placements:
			frappe.throw(frappe._("Pick at least one ad placement."))
		seen = set()
		for row in self.placements:
			if row.placement in seen:
				frappe.throw(frappe._("{0} is listed twice.").format(row.placement))
			seen.add(row.placement)
			row.days = wafi.inclusive_days(row.start_date, row.end_date)
			if row.days < wafi.AD_MIN_DAYS:
				frappe.throw(frappe._("{0}: minimum booking is {1} days.").format(row.placement, wafi.AD_MIN_DAYS))
			row.price = wafi.ad_placement_price(row.placement, row.days)
			self._check_availability(row)

	def _check_availability(self, row):
		"""A banner slot holds one ad at a time."""
		taken = frappe.db.sql(
			"""select p.parent, p.start_date, p.end_date
			from `tabWafi Ad Placement` p join `tabWafi Ad` a on a.name = p.parent
			where p.placement = %s and a.name != %s and a.status in %s
			and p.start_date <= %s and p.end_date >= %s limit 1""",
			(row.placement, self.name or "", wafi.ACTIVE_STATUSES, row.end_date, row.start_date),
			as_dict=True,
		)
		if taken:
			frappe.throw(
				frappe._("{0} is already booked from {1} to {2} ({3}).").format(
					row.placement, taken[0].start_date, taken[0].end_date, taken[0].parent
				)
			)

	def compute_price(self):
		gross, discount, total = wafi.ad_totals([(row.placement, row.days) for row in self.placements])
		self.gross_price = gross
		self.discount = discount
		return total
