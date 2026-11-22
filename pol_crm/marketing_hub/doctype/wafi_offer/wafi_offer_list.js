frappe.listview_settings["Wafi Offer"] = {
	add_fields: ["status", "total_price"],
	get_indicator: (doc) => pol_crm.marketing.review_indicator(doc),
};
