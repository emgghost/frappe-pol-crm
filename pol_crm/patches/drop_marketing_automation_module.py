"""
Campaigns and automations moved from the Marketing Automation module into Marketing Hub.
Sync has already moved each DocType; this removes the module record left behind.
"""

import frappe


def execute():
	if frappe.db.exists("Module Def", "Marketing Automation") and not frappe.db.exists(
		"DocType", {"module": "Marketing Automation"}
	):
		frappe.delete_doc("Module Def", "Marketing Automation", force=True, ignore_missing=True)
