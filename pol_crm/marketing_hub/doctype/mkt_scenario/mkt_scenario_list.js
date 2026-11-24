frappe.listview_settings["Mkt Scenario"] = {
	add_fields: ["enabled", "trigger_type", "channel", "scenario_name"],
	get_indicator(doc) {
		return doc.enabled ? [__("روشن"), "green", "enabled,=,1"] : [__("خاموش"), "gray", "enabled,=,0"];
	},
	formatters: {
		trigger_type: (value) => pol_crm.marketing.labels.trigger_type[value] || value,
		channel: (value) => pol_crm.marketing.labels.channel[value] || value,
	},
	onload(listview) {
		listview.page.add_inner_button(__("قالب‌های آماده"), () => pol_crm.marketing.show_templates("automation"));
		listview.page.add_action_item(__("روشن کردن"), () =>
			listview.call_for_selected_items("frappe.client.set_value", { fieldname: "enabled", value: 1 })
		);
		listview.page.add_action_item(__("خاموش کردن"), () =>
			listview.call_for_selected_items("frappe.client.set_value", { fieldname: "enabled", value: 0 })
		);
	},
};
