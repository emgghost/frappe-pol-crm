frappe.listview_settings["Mkt Campaign"] = {
	add_fields: ["status"],
	get_indicator(doc) {
		const [label, color] = pol_crm.marketing.labels.status[doc.status] || [doc.status, "gray"];
		return [label, color, "status,=," + doc.status];
	},
	onload(listview) {
		listview.page.add_inner_button(__("قالب‌های آماده"), () => pol_crm.marketing.show_templates("campaign"));
	},
};
