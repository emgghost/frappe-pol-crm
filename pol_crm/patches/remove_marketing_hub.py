"""
Take out the marketing hub that was built for the Iraqi market (Meta Ads, Wafi,
WhatsApp, Instagram, a wallet in dinars). It never held any records on our sites
apart from the occasions it seeded itself, so nothing of the merchant's is lost.
"""

import frappe

MODULE = "Marketing Hub"

# Customer fields that only the Iraqi channels and address format used.
CUSTOM_FIELDS = (
	"Customer-custom_governorate",
	"Customer-custom_wafi_user_id",
	"Customer-custom_instagram_user_id",
	"Customer-custom_instagram_last_inbound",
)


def execute():
	for page in frappe.get_all("Page", filters={"module": MODULE}, pluck="name"):
		frappe.delete_doc("Page", page, force=True, ignore_missing=True)

	for report in frappe.get_all("Report", filters={"module": MODULE}, pluck="name"):
		frappe.delete_doc("Report", report, force=True, ignore_missing=True)

	# Child tables first, so their parents can go without dangling links.
	doctypes = frappe.get_all("DocType", filters={"module": MODULE}, fields=["name", "istable"])
	for doctype in sorted(doctypes, key=lambda d: not d.istable):
		frappe.delete_doc("DocType", doctype.name, force=True, ignore_missing=True)
		# Deleting the DocType leaves its table behind. These held nothing of the merchant's.
		frappe.db.sql_ddl(f"drop table if exists `tab{doctype.name}`")

	# The hub's sidebar linked to the doctypes above. The app no longer ships one.
	if frappe.db.exists("DocType", "Sidebar"):
		frappe.delete_doc("Sidebar", "RFM", force=True, ignore_missing=True)

	for field in CUSTOM_FIELDS:
		frappe.delete_doc("Custom Field", field, force=True, ignore_missing=True)

	frappe.delete_doc("Module Def", MODULE, force=True, ignore_missing=True)
	frappe.clear_cache()
