frappe.listview_settings["Mkt Stock Waitlist"] = {
	add_fields: ["status"],
	get_indicator(doc) {
		const [label, color] = pol_crm.marketing.labels.waitlist_status[doc.status] || [doc.status, "gray"];
		return [label, color, "status,=," + doc.status];
	},
};
