frappe.listview_settings["Loyalty Offer"] = {
	add_fields: ["status", "customer", "discount_code", "percentage_value", "valid_until", "reason"],
	get_indicator: function (doc) {
		const status_colors = {
			ACTIVE: "green",
			USED: "blue",
			EXPIRED: "red",
		};
		const status_labels = {
			ACTIVE: __("فعال"),
			USED: __("مصرف‌شده"),
			EXPIRED: __("منقضی"),
		};
		const color = status_colors[doc.status] || "gray";
		const label = status_labels[doc.status] || doc.status;
		return [label, color, "status,=," + doc.status];
	},
	formatters: {
		percentage_value: function (val) {
			if (!val) return "";
			return `<span class="badge badge-success font-weight-bold" style="background:#e3f9e5; color:#1f7a37; padding:2px 8px; border-radius:12px;">${val}٪</span>`;
		},
		discount_code: function (val) {
			if (!val) return "";
			return `<code style="font-weight:600; color:#4f46e5;">${val}</code>`;
		},
	},
	onload: function (listview) {
		listview.page.add_action_item(__("علامت‌گذاری به عنوان منقضی"), function () {
			listview.call_for_selected_items("frappe.client.set_value", {
				fieldname: "status",
				value: "EXPIRED",
			});
		});
	},
};
