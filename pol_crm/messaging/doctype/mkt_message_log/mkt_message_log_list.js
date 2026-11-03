frappe.listview_settings["Mkt Message Log"] = {
	add_fields: ["status", "channel", "recipient", "category"],
	get_indicator: function (doc) {
		const status_colors = {
			SENT: "green",
			FAILED: "red",
			POSTPONED: "orange",
			SKIPPED: "gray",
		};
		const status_labels = {
			SENT: __("ارسال‌شده"),
			FAILED: __("ناموفق"),
			POSTPONED: __("موکول‌شده"),
			SKIPPED: __("رد شده"),
		};
		const color = status_colors[doc.status] || "gray";
		const label = status_labels[doc.status] || doc.status;
		return [label, color, "status,=," + doc.status];
	},
	formatters: {
		channel: function (val) {
			if (!val) return "";
			const badges = {
				SMS: `<span class="badge" style="background:#e0f2fe; color:#0369a1; padding:2px 6px; border-radius:4px;">SMS</span>`,
				TELEGRAM: `<span class="badge" style="background:#f0f9ff; color:#0284c7; padding:2px 6px; border-radius:4px;">Telegram</span>`,
				WHATSAPP: `<span class="badge" style="background:#dcfce7; color:#15803d; padding:2px 6px; border-radius:4px;">WhatsApp</span>`,
				EMAIL: `<span class="badge" style="background:#f3e8ff; color:#7e22ce; padding:2px 6px; border-radius:4px;">Email</span>`,
			};
			return badges[val] || val;
		},
	},
};
