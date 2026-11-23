"""
Create the app's custom fields on every site, whatever else it has installed.

Frappe syncs a fixture file all or nothing: custom_field.json also holds fields for Frappe
CRM's CRM Deal, so on a site without CRM the whole file was skipped and Customer got none of
the RFM and marketing fields. This creates each field whose DocType exists.
"""

import json
import os

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_field

KEYS = ("dt", "name", "doctype", "modified", "creation", "owner", "modified_by", "idx", "docstatus")


def ensure_custom_fields():
	path = frappe.get_app_path("pol_crm", "fixtures", "custom_field.json")
	if not os.path.exists(path):
		return
	with open(path) as f:
		fields = json.load(f)

	for field in fields:
		dt = field.get("dt")
		if not dt or not frappe.db.exists("DocType", dt) or frappe.db.exists("Custom Field", field["name"]):
			continue
		create_custom_field(dt, {k: v for k, v in field.items() if k not in KEYS}, ignore_validate=True)
