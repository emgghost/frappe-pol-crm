frappe.listview_settings["Mkt Scenario"] = {
	add_fields: ["enabled", "trigger_type", "channel", "target_rfm_segment", "scenario_name"],
	get_indicator: function (doc) {
		if (doc.enabled) {
			return [__("فعال"), "green", "enabled,=,1"];
		} else {
			return [__("غیرفعال"), "gray", "enabled,=,0"];
		}
	},
	onload: function (listview) {
		listview.page.add_action_item(__("فعال‌سازی"), function () {
			listview.call_for_selected_items("frappe.client.set_value", {
				fieldname: "enabled",
				value: 1,
			});
		});

		listview.page.add_action_item(__("غیرفعال‌سازی"), function () {
			listview.call_for_selected_items("frappe.client.set_value", {
				fieldname: "enabled",
				value: 0,
			});
		});
	},
};
