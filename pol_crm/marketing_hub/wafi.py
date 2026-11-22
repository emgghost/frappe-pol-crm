"""
Wafi Business Promotion: prices and the shared review flow for Wafi Ad, Wafi Offer,
Wafi Promote Request and Wafi Notification.

Flow: Draft -> (pay from the Marketing Wallet) -> In Review -> Approved -> Live -> Completed,
or Rejected / Cancelled with the payment returned to the wallet.
"""

import math

import frappe
from frappe.model.document import Document
from frappe.utils import cint, date_diff, flt, getdate, now_datetime, nowdate

from pol_crm.marketing_hub import wallet

# Banner ads: price per 5 days, minimum 5 days, 20% off when all four are booked together.
AD_PLACEMENT_PRICES = {
	"Search Results Banner": 15000,
	"Homepage Banner": 35000,
	"Offers Center Banner": 25000,
	"Club Banner": 15000,
}
AD_MIN_DAYS = 5
AD_ALL_DISCOUNT = 0.20

# Offers: three free active offers (one per size); a second one of a size is charged per week.
# First Page tiles are booked for exactly 3 days.
OFFER_FREE = "Regular Pages (Free)"
OFFER_TOP = "First Page (Paid)"
OFFER_TOP_DAYS = 3
OFFER_TOP_PRICES = {"Square": 5000, "Banner": 10000, "Large Tile": 15000}
OFFER_EXTRA_PRICES = {"Square": 2000, "Banner": 3000, "Large Tile": 4000}
TILE_SIZE = {
	"Square 1": "Square",
	"Square 2": "Square",
	"Banner": "Banner",
	"Square 3": "Square",
	"Large Tile": "Large Tile",
	"Square 4": "Square",
}

# Promote: weekly price per feature; three of them have 3 slots per business category.
PROMOTE_PRICES = {
	"top_search": 30000,
	"middle_search": 15000,
	"category_highlight": 20000,
	"map_pin": 25000,
	"wider_radius": 10000,
}
PROMOTE_LABELS = {
	"top_search": "Top Search",
	"middle_search": "Middle Search",
	"category_highlight": "Category",
	"map_pin": "Map",
	"wider_radius": "Wider Radius",
}
PROMOTE_CAPACITY = {"top_search": 3, "category_highlight": 3, "map_pin": 3}
PROMOTE_MIN_DAYS = 7

# Requests that hold a slot.
ACTIVE_STATUSES = ("In Review", "Approved", "Live")
REVIEW_DOCTYPES = ("Wafi Ad", "Wafi Offer", "Wafi Promote Request", "Wafi Notification")


def inclusive_days(start_date, end_date):
	"""Both the start and the end day count."""
	if not start_date or not end_date:
		return 0
	return max(date_diff(end_date, start_date) + 1, 0)


def ad_placement_price(placement, days):
	return round(cint(days) * AD_PLACEMENT_PRICES.get(placement, 0) / 5)


def ad_totals(rows):
	"""rows: [(placement, days)] -> (gross, discount, total)"""
	gross = sum(ad_placement_price(placement, days) for placement, days in rows)
	all_booked = {placement for placement, _days in rows} >= set(AD_PLACEMENT_PRICES)
	discount = round(gross * AD_ALL_DISCOUNT) if all_booked else 0
	return gross, discount, gross - discount


def offer_price(tier, size=None, tile=None, days=0, is_extra=False):
	if tier == OFFER_TOP:
		return OFFER_TOP_PRICES.get(TILE_SIZE.get(tile), 0)
	if is_extra:
		return max(1, math.ceil(cint(days) / 7)) * OFFER_EXTRA_PRICES.get(size, 0)
	return 0


def promote_price(features, days):
	"""features: fieldnames that are switched on -> (weeks, weekly_rate, total)"""
	weeks = math.ceil(cint(days) / 7) if cint(days) > 0 else 0
	rate = sum(PROMOTE_PRICES.get(f, 0) for f in features)
	return weeks, rate, weeks * rate


def ranges_overlap(start_a, end_a, start_b, end_b):
	return getdate(start_a) <= getdate(end_b) and getdate(start_b) <= getdate(end_a)


class WafiReviewDocument(Document):
	"""Base for the four Wafi request doctypes."""

	title_fieldname = "name"

	def compute_price(self):
		return 0

	def validate_rules(self):
		pass

	def date_range(self):
		return self.get("start_date"), self.get("end_date")

	def payload(self):
		skip = {"owner", "modified_by", "docstatus", "idx", "wallet_transaction"}
		return {k: v for k, v in self.as_dict(convert_dates_to_str=True).items() if k not in skip and v not in (None, "")}

	def validate(self):
		if not self.status:
			self.status = "Draft"
		if not self.is_new() and not self.flags.review_action:
			current = frappe.db.get_value(self.doctype, self.name, "status")
			if current not in ("Draft", "Rejected"):
				frappe.throw(frappe._("This request is {0} and can no longer be changed.").format(current))
		self.validate_rules()
		self.total_price = self.compute_price()

	def on_trash(self):
		if self.status in ACTIVE_STATUSES:
			frappe.throw(frappe._("Cancel this request before deleting it."))

	def _save_review(self):
		self.flags.review_action = True
		try:
			self.save(ignore_permissions=True)
		finally:
			# Only this one save may change a request that is past Draft.
			self.flags.review_action = False

	def _refund(self):
		if cint(self.paid) and self.wallet_transaction:
			wallet.refund_transaction(self.wallet_transaction, f"Refund: {self.doctype} {self.get(self.title_fieldname)}")
			self.paid = 0
			self.wallet_transaction = None

	@frappe.whitelist()
	def submit_for_review(self):
		"""Pay from the wallet when there is a price, then put the request in the review queue."""
		self.check_permission("write")
		if self.status not in ("Draft", "Rejected"):
			frappe.throw(frappe._("This request is already {0}.").format(self.status))
		self.validate_rules()
		price = self.compute_price()
		if price > 0 and not cint(self.paid):
			self.wallet_transaction = wallet.charge(
				price, f"{self.doctype}: {self.get(self.title_fieldname)}", self.doctype, self.name
			)
			self.paid = 1
		self.total_price = price
		self.status = "In Review"
		self.submitted_on = now_datetime()
		self.review_note = None

		from pol_crm.messaging.channels import wafi_request

		data, error = wafi_request("wafi_promotions_path", {"kind": self.doctype, "reference": self.name, "data": self.payload()})
		if data and data.get("id"):
			self.wafi_reference = data.get("id")
		self._save_review()
		return {"status": self.status, "price": price, "pushed_to_wafi": not error, "wafi_error": error}

	@frappe.whitelist()
	def approve(self, note=None):
		frappe.only_for("System Manager")
		if self.status != "In Review":
			frappe.throw(frappe._("Only a request in review can be approved."))
		self.status = "Approved"
		self.review_note = note
		self._save_review()

	@frappe.whitelist()
	def reject(self, reason=None):
		frappe.only_for("System Manager")
		if self.status not in ("In Review", "Approved"):
			frappe.throw(frappe._("Only a request in review or approved can be rejected."))
		self._refund()
		self.status = "Rejected"
		self.review_note = reason
		self._save_review()

	@frappe.whitelist()
	def cancel_request(self):
		"""The merchant withdraws a request that is not live yet; the payment goes back to the wallet."""
		self.check_permission("write")
		if self.status not in ("Draft", "In Review", "Approved"):
			frappe.throw(frappe._("A request that is {0} cannot be cancelled.").format(self.status))
		self._refund()
		self.status = "Cancelled"
		self._save_review()


def sync_reviews():
	"""Ask Wafi what its reviewers decided for every request still in review.

	Expects {"status": "approved" | "rejected" | ..., "note": "..."} from the status
	endpoint; anything else leaves the request in review."""
	from pol_crm.messaging.channels import wafi_get

	for doctype in REVIEW_DOCTYPES:
		if not frappe.db.exists("DocType", doctype):
			continue
		pending = frappe.get_all(doctype, filters={"status": "In Review", "wafi_reference": ["is", "set"]}, fields=["name", "wafi_reference"])
		for row in pending:
			data, error = wafi_get("wafi_status_path", row.wafi_reference)
			if error or not isinstance(data, dict):
				continue
			decision = str(data.get("status") or "").lower()
			if decision not in ("approved", "rejected"):
				continue
			doc = frappe.get_doc(doctype, row.name)
			if decision == "rejected":
				doc._refund()
			doc.status = "Approved" if decision == "approved" else "Rejected"
			doc.review_note = data.get("note") or data.get("reason")
			doc._save_review()


def advance_statuses():
	"""Every 10 minutes: read Wafi's review decisions, then approved requests go live on
	their start day and complete after their end day."""
	try:
		sync_reviews()
		frappe.db.commit()
	except Exception:
		frappe.db.rollback()
		frappe.log_error(title="Wafi review sync failed")
	today = getdate(nowdate())
	for doctype in ("Wafi Ad", "Wafi Offer", "Wafi Promote Request"):
		if not frappe.db.exists("DocType", doctype):
			continue
		for name in frappe.get_all(doctype, filters={"status": ["in", ["Approved", "Live"]]}, pluck="name"):
			doc = frappe.get_doc(doctype, name)
			start, end = doc.date_range()
			if not start or not end:
				continue
			if getdate(end) < today:
				doc.db_set("status", "Completed")
			elif doc.status == "Approved" and getdate(start) <= today:
				doc.db_set("status", "Live")

	if frappe.db.exists("DocType", "Wafi Notification"):
		for name in frappe.get_all("Wafi Notification", filters={"status": "Approved"}, pluck="name"):
			frappe.get_doc("Wafi Notification", name).send_if_due()
