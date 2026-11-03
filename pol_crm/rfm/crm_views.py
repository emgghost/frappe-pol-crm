import json
import frappe


def setup_standard_crm_views():
	"""Create or update standard CRM views in Frappe CRM (/crm) including RFM segment columns & grouping."""
	if not frappe.db.exists("DocType", "CRM View Settings"):
		return 0

	views = [
		{
			"name": "Standard Contacts",
			"label": "All Contacts",
			"type": "list",
			"dt": "Contact",
			"route_name": "Contacts",
			"is_standard": 1,
			"is_default": 1,
			"public": 1,
			"user": "",
			"columns": json.dumps([
				{"label": "Name", "type": "Data", "key": "full_name", "width": "16rem"},
				{"label": "RFM Segment", "type": "Select", "key": "custom_rfm_segment", "width": "11rem"},
				{"label": "Email", "type": "Data", "key": "email_id", "width": "12rem"},
				{"label": "Phone", "type": "Data", "key": "mobile_no", "width": "11rem"},
				{"label": "Organization", "type": "Data", "key": "company_name", "width": "11rem"},
				{"label": "Last Modified", "type": "Datetime", "key": "modified", "width": "8rem"},
			]),
			"rows": json.dumps([
				"name",
				"full_name",
				"company_name",
				"email_id",
				"mobile_no",
				"custom_rfm_segment",
				"modified",
				"image",
			]),
			"order_by": "modified desc",
			"filters": json.dumps({}),
		},
		{
			"name": "Contacts by RFM",
			"label": "Contacts by RFM",
			"type": "group_by",
			"dt": "Contact",
			"route_name": "Contacts",
			"is_standard": 1,
			"is_default": 0,
			"public": 1,
			"user": "",
			"group_by_field": "custom_rfm_segment",
			"columns": json.dumps([
				{"label": "Name", "type": "Data", "key": "full_name", "width": "16rem"},
				{"label": "RFM Segment", "type": "Select", "key": "custom_rfm_segment", "width": "11rem"},
				{"label": "Email", "type": "Data", "key": "email_id", "width": "12rem"},
				{"label": "Phone", "type": "Data", "key": "mobile_no", "width": "11rem"},
				{"label": "Organization", "type": "Data", "key": "company_name", "width": "11rem"},
			]),
			"rows": json.dumps([
				"name",
				"full_name",
				"company_name",
				"email_id",
				"mobile_no",
				"custom_rfm_segment",
				"modified",
				"image",
			]),
			"order_by": "modified desc",
			"filters": json.dumps({}),
		},
		{
			"name": "VIP & Champions",
			"label": "VIP & Champions",
			"type": "list",
			"dt": "Contact",
			"route_name": "Contacts",
			"is_standard": 1,
			"is_default": 0,
			"public": 1,
			"user": "",
			"columns": json.dumps([
				{"label": "Name", "type": "Data", "key": "full_name", "width": "16rem"},
				{"label": "RFM Segment", "type": "Select", "key": "custom_rfm_segment", "width": "11rem"},
				{"label": "Phone", "type": "Data", "key": "mobile_no", "width": "11rem"},
				{"label": "Organization", "type": "Data", "key": "company_name", "width": "11rem"},
			]),
			"rows": json.dumps([
				"name",
				"full_name",
				"company_name",
				"email_id",
				"mobile_no",
				"custom_rfm_segment",
				"modified",
				"image",
			]),
			"order_by": "modified desc",
			"filters": json.dumps({"custom_rfm_segment": ["in", ["CHAMPIONS", "LOYAL"]]}),
		},
		{
			"name": "At Risk Contacts",
			"label": "At Risk Customers",
			"type": "list",
			"dt": "Contact",
			"route_name": "Contacts",
			"is_standard": 1,
			"is_default": 0,
			"public": 1,
			"user": "",
			"columns": json.dumps([
				{"label": "Name", "type": "Data", "key": "full_name", "width": "16rem"},
				{"label": "RFM Segment", "type": "Select", "key": "custom_rfm_segment", "width": "11rem"},
				{"label": "Phone", "type": "Data", "key": "mobile_no", "width": "11rem"},
				{"label": "Organization", "type": "Data", "key": "company_name", "width": "11rem"},
			]),
			"rows": json.dumps([
				"name",
				"full_name",
				"company_name",
				"email_id",
				"mobile_no",
				"custom_rfm_segment",
				"modified",
				"image",
			]),
			"order_by": "modified desc",
			"filters": json.dumps({"custom_rfm_segment": ["in", ["AT_RISK", "CANT_LOSE"]]}),
		},
		{
			"name": "Deals by RFM",
			"label": "Deals by Customer Segment",
			"type": "group_by",
			"dt": "CRM Deal",
			"route_name": "Deals",
			"is_standard": 1,
			"is_default": 0,
			"public": 1,
			"user": "",
			"group_by_field": "custom_rfm_segment",
			"columns": json.dumps([
				{"label": "Organization", "type": "Link", "key": "organization", "options": "CRM Organization", "width": "11rem"},
				{"label": "Customer Segment", "type": "Data", "key": "custom_rfm_segment", "width": "11rem"},
				{"label": "Annual Revenue", "type": "Currency", "key": "annual_revenue", "align": "right", "width": "9rem"},
				{"label": "Status", "type": "Link", "options": "CRM Deal Status", "key": "status", "width": "10rem"},
				{"label": "Email", "type": "Data", "key": "email", "width": "12rem"},
			]),
			"rows": json.dumps([
				"name",
				"organization",
				"custom_rfm_segment",
				"annual_revenue",
				"status",
				"email",
				"currency",
				"deal_owner",
			]),
			"order_by": "modified desc",
			"filters": json.dumps({}),
		},
	]

	# Ensure Contact full_name is visible in CRM views
	try:
		from frappe.custom.doctype.property_setter.property_setter import make_property_setter
		make_property_setter("Contact", "full_name", "hidden", 0, "Check")
	except Exception:
		pass

	for v in views:
		existing = frappe.db.get_value(
			"CRM View Settings",
			{"label": v["label"], "dt": v["dt"], "type": v["type"]},
			"name",
		)
		v_copy = dict(v)
		v_copy.pop("name", None)
		if existing:
			doc = frappe.get_doc("CRM View Settings", existing)
			doc.update(v_copy)
			doc.save(ignore_permissions=True)
		else:
			doc = frappe.get_doc({"doctype": "CRM View Settings", **v_copy})
			doc.insert(ignore_permissions=True)

	frappe.db.commit()
	return len(views)
