import frappe
from frappe.utils import add_days, flt, getdate

from pol_crm.marketing_hub import wafi

VALUE_FIELDS = {
	"% Discount": ("discount_percent", "Discount %"),
	"Fixed Discount": ("discount_amount", "Discount Amount"),
	"Buy X Get Y": ("deal_text", "The Deal"),
	"Free Item": ("free_item", "Free Item"),
	"Special Price": ("special_price", "Special Price"),
}


class WafiOffer(wafi.WafiReviewDocument):
	title_fieldname = "offer_title"

	def validate_rules(self):
		fieldname, label = VALUE_FIELDS[self.offer_type]
		if not self.get(fieldname):
			frappe.throw(frappe._("{0} is required for a {1} offer.").format(label, self.offer_type))
		if self.offer_type == "% Discount" and not 0 < flt(self.discount_percent) <= 100:
			frappe.throw(frappe._("Discount % must be between 1 and 100."))

		if self.tier == wafi.OFFER_TOP:
			if not (self.area and self.tile):
				frappe.throw(frappe._("Pick the area and the tile for a First Page offer."))
			self.end_date = add_days(self.start_date, wafi.OFFER_TOP_DAYS - 1)
			self.size = wafi.TILE_SIZE.get(self.tile)
			self._check_tile()
		else:
			if not self.end_date or getdate(self.end_date) < getdate(self.start_date):
				frappe.throw(frappe._("The end date must be on or after the start date."))
			self.area = None
			self.tile = None

	def _check_tile(self):
		"""One merchant per First Page tile, per area, at a time."""
		others = frappe.get_all(
			"Wafi Offer",
			filters={
				"name": ["!=", self.name or ""],
				"tier": wafi.OFFER_TOP,
				"area": self.area,
				"tile": self.tile,
				"status": ["in", wafi.ACTIVE_STATUSES],
			},
			fields=["name", "start_date", "end_date"],
		)
		for other in others:
			if wafi.ranges_overlap(self.start_date, self.end_date, other.start_date, other.end_date):
				frappe.throw(
					frappe._("{0} in {1} is already booked from {2} to {3}.").format(
						self.tile, self.area, other.start_date, other.end_date
					)
				)

	def is_extra(self):
		"""True when another free offer of this size is already active: this one is charged per week."""
		if self.tier != wafi.OFFER_FREE:
			return False
		return bool(
			frappe.db.exists(
				"Wafi Offer",
				{
					"name": ["!=", self.name or ""],
					"tier": wafi.OFFER_FREE,
					"size": self.size,
					"status": ["in", wafi.ACTIVE_STATUSES],
				},
			)
		)

	def compute_price(self):
		days = wafi.inclusive_days(self.start_date, self.end_date)
		return wafi.offer_price(self.tier, self.size, self.tile, days, self.is_extra())
