frappe.ui.form.on("Mkt Scenario", {
	refresh(frm) {
		const m = pol_crm.marketing;
		m.add_tier_picker(frm, "club_tiers");
		m.add_picker(frm, "activity_segments", __("Activity"), ["No Activity", "Re-engage"]);
		m.add_picker(frm, "occasions", __("Occasions"), () => frappe.db.get_list("Mkt Occasion", { pluck: "name", limit: 100 }));
		if (frm.is_new()) return;

		frm.add_custom_button(frm.doc.enabled ? __("Turn Off") : __("Turn On"), () => {
			frm.set_value("enabled", frm.doc.enabled ? 0 : 1);
			frm.save();
		});
		frm.add_custom_button(__("Messages"), () => frappe.set_route("List", "Mkt Message Log", { scenario: frm.doc.name }));
		frm.add_custom_button(__("Queue"), () => frappe.set_route("List", "Mkt Scenario Run", { scenario: frm.doc.name }));

		// Results of the last 30 days.
		frappe.call("pol_crm.marketing_automation.engine.scenario_stats", { scenario: frm.doc.name }).then((r) => {
			const s = r.message;
			if (!s) return;
			frm.dashboard.add_indicator(__("Reached (30 days): {0}", [s.entered]), "blue");
			frm.dashboard.add_indicator(__("Bought after: {0}", [s.converted]), s.converted ? "green" : "gray");
			frm.dashboard.add_indicator(__("Revenue: {0}", [m.iqd(s.revenue)]), "green");
			frm.dashboard.add_indicator(__("Cost: {0}", [m.iqd(s.cost)]), "orange");
			frm.dashboard.add_indicator(__("Waiting to send: {0}", [s.pending]), "gray");
		});
	},
});
