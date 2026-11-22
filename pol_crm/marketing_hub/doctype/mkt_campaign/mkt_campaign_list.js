frappe.listview_settings["Mkt Campaign"] = {
	add_fields: ["status", "channel", "campaign_type", "scheduled_at"],
	get_indicator(doc) {
		const colors = { Draft: "gray", Scheduled: "orange", Sending: "blue", Sent: "green", Cancelled: "darkgrey", Failed: "red" };
		return [__(doc.status), colors[doc.status] || "gray", "status,=," + doc.status];
	},
	onload(listview) {
		listview.page.add_inner_button(__("From Template"), () => pol_crm.marketing.pick_template("campaign"));
	},
};
