frappe.listview_settings["Meta Ad Campaign"] = {
	add_fields: ["status", "kind", "objective"],
	get_indicator(doc) {
		const colors = { Draft: "gray", "In Review": "orange", Active: "green", Paused: "blue", Completed: "darkgrey", Rejected: "red" };
		return [__(doc.status), colors[doc.status] || "gray", "status,=," + doc.status];
	},
	onload(listview) {
		// Boost a Post / Create an Ad: one dialog builds the campaign, ad set and ad as drafts.
		const quick = (kind) => () => {
			const boost = kind === "Boost";
			const dialog = new frappe.ui.Dialog({
				title: boost ? __("Boost a Post") : __("Create an Ad"),
				fields: [
					{ fieldtype: "Data", fieldname: "campaign_name", label: __("Name"), reqd: 1 },
					{ fieldtype: "Select", fieldname: "objective", label: __("Goal"), options: "Engagement\nTraffic\nAwareness\nLeads\nSales", default: "Engagement" },
					{ fieldtype: "Select", fieldname: "post_platform", label: __("Platform"), options: "Instagram\nFacebook", default: "Instagram", hidden: !boost },
					{ fieldtype: "Data", fieldname: "post_id", label: __("Post ID or Link"), reqd: boost, hidden: !boost },
					{ fieldtype: "Small Text", fieldname: "primary_text", label: __("Ad Text"), reqd: !boost, hidden: boost },
					{ fieldtype: "Attach", fieldname: "media", label: __("Image"), hidden: boost },
					{ fieldtype: "Currency", fieldname: "daily_budget", label: __("Daily Budget (IQD)"), default: 5000, reqd: 1 },
					{ fieldtype: "Int", fieldname: "days", label: __("Days"), default: 7, reqd: 1 },
				],
				primary_action_label: __("Create Draft"),
				primary_action(values) {
					frappe.call("pol_crm.marketing_hub.meta.quick_create", Object.assign({ kind }, values)).then((r) => {
						dialog.hide();
						frappe.set_route("Form", "Meta Ad Campaign", r.message);
					});
				},
			});
			dialog.show();
		};
		listview.page.add_inner_button(__("Boost a Post"), quick("Boost"));
		listview.page.add_inner_button(__("Create an Ad"), quick("Ad"));
	},
};
