frappe.listview_settings["Wafi Notification"] = {
	add_fields: ["status", "total_price"],
	get_indicator: (doc) => pol_crm.marketing.review_indicator(doc),
};
