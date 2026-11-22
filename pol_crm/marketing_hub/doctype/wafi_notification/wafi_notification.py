import frappe
from frappe.utils import cint, get_datetime, now_datetime

from pol_crm.marketing_hub import wafi


class WafiNotification(wafi.WafiReviewDocument):
	title_fieldname = "notification_title"

	def date_range(self):
		return None, None

	def validate_rules(self):
		if not (cint(self.city_wide) or cint(self.specific_town) or cint(self.by_radius)):
			frappe.throw(frappe._("Pick who should get this: city-wide, a town or a radius."))
		if cint(self.specific_town) and not self.governorate:
			frappe.throw(frappe._("Pick the governorate for the town."))
		if cint(self.by_radius) and not (self.latitude and self.longitude):
			frappe.throw(frappe._("Set the latitude and longitude of the point on the map."))
		if cint(self.age_to) < cint(self.age_from):
			frappe.throw(frappe._("The age range is reversed."))
		if self.send_mode == "Schedule":
			if not self.scheduled_at:
				frappe.throw(frappe._("Set when the notification should be sent."))
			if self.status in ("Draft", "Rejected") and get_datetime(self.scheduled_at) <= now_datetime():
				frappe.throw(frappe._("The send time must be in the future."))

	def send_if_due(self):
		"""Approved notifications are handed to Wafi now, or at their scheduled time."""
		if self.status != "Approved":
			return
		if self.send_mode == "Schedule" and get_datetime(self.scheduled_at) > now_datetime():
			return
		from pol_crm.messaging.channels import wafi_request

		_data, error = wafi_request("wafi_notifications_path",{"reference": self.name, "data": self.payload()})
		if error:
			self.db_set("review_note", f"Could not send to Wafi: {error}"[:140], update_modified=False)
			return
		self.db_set({"status": "Completed", "sent_on": now_datetime(), "review_note": None})
