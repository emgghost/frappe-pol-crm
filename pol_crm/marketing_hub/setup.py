"""
First-run content for the Marketing Hub: the occasions every Iranian shop greets on.

Only occasions fixed in the Jalali calendar are seeded. Lunar ones (Mother's Day, Eid) move
every year, so the merchant adds them with this year's date.
"""

import datetime

import frappe
from frappe.utils import getdate, nowdate

# name: (Jalali month, day)
FIXED_OCCASIONS = {
	"نوروز": (1, 1),
	"شب یلدا": (9, 30),
}


def next_on_jalali(month, day, today):
	from iran_base.utils.jalali import gregorian_to_jalali, jalali_to_gregorian

	year = gregorian_to_jalali(today.year, today.month, today.day)[0]
	for y in (year, year + 1):
		date = datetime.date(*jalali_to_gregorian(y, month, day))
		if date >= today:
			return date
	return date


def seed_occasions():
	if "iran_base" not in frappe.get_installed_apps() or frappe.db.count("Mkt Occasion"):
		return
	today = getdate(nowdate())
	for name, (month, day) in FIXED_OCCASIONS.items():
		frappe.get_doc(
			{
				"doctype": "Mkt Occasion",
				"occasion_name": name,
				"occasion_date": next_on_jalali(month, day, today),
				"repeats_yearly": 1,
				"enabled": 1,
			}
		).insert(ignore_permissions=True)
