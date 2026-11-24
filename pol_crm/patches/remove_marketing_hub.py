"""
Take out what the Iraqi version of the marketing hub added: Meta ads, Wafi, the wallet in
dinars and the customer fields only Iraqi channels used. They never held records on our
sites, so nothing of the merchant's is lost.

The Iran Marketing Hub ships under the same module name, with its own campaign, occasion,
waitlist, templates page and report, so this names exactly what goes and leaves the module,
its page, report and sidebar to the normal sync.
"""

import frappe

IRAQ_DOCTYPES = (
	# child tables first, so their parents can go without dangling links
	"Meta Ad Card",
	"Wafi Ad Placement",
	"Meta Ad",
	"Meta Ad Set",
	"Meta Ad Campaign",
	"Wafi Ad",
	"Wafi Offer",
	"Wafi Notification",
	"Wafi Promote Request",
	"Mkt Wallet Transaction",
	"Mkt Scenario Run",
	"Marketing Hub Settings",
)

CUSTOM_FIELDS = (
	"Customer-custom_governorate",
	"Customer-custom_wafi_user_id",
	"Customer-custom_instagram_user_id",
	"Customer-custom_instagram_last_inbound",
)


def execute():
	for doctype in IRAQ_DOCTYPES:
		frappe.delete_doc("DocType", doctype, force=True, ignore_missing=True)
		# Deleting the DocType leaves its table behind. These held nothing of the merchant's.
		frappe.db.sql_ddl(f"drop table if exists `tab{doctype}`")

	for field in CUSTOM_FIELDS:
		frappe.delete_doc("Custom Field", field, force=True, ignore_missing=True)

	frappe.clear_cache()
