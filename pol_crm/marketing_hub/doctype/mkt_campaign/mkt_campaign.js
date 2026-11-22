frappe.ui.form.on("Mkt Campaign", {
	refresh(frm) {
		const m = pol_crm.marketing;
		m.add_picker(frm, "governorates", __("Governorates"), m.GOVERNORATES);
		m.add_picker(frm, "activity_segments", __("Activity"), m.ACTIVITIES);
		m.add_tier_picker(frm, "club_tiers");
		if (frm.is_new()) return;

		const status = frm.doc.status;
		const call = (method) => frm.call({ doc: frm.doc, method });
		const run = (method, message) =>
			call(method).then(() => {
				frappe.show_alert({ message, indicator: "green" });
				return frm.reload_doc();
			});
		const saved = (fn) => () => (frm.is_dirty() ? frm.save().then(fn) : fn());
		const audience_text = (a) => {
			let text = __("{0} customers will get this (limit {1} per send).", [a.count, a.limit]);
			if (a.cost) {
				text += "<br>" + __("WhatsApp cost: {0}. Marketing Wallet: {1}.", [m.iqd(a.cost), m.iqd(a.wallet)]);
			}
			if (a.sample && a.sample.length) {
				text += "<br><br>" + a.sample.map((s) => frappe.utils.escape_html(s)).join(", ") + (a.count > a.sample.length ? " …" : "");
			}
			return text;
		};

		if (["Draft", "Scheduled", "Failed", "Cancelled"].includes(status)) {
			frm.add_custom_button(
				__("Preview Audience"),
				saved(() => call("preview_audience").then((r) => frappe.msgprint({ title: __("Who gets it"), message: audience_text(r.message) })))
			);
		}
		if (["Draft", "Scheduled", "Failed"].includes(status)) {
			frm.add_custom_button(
				__("Send Now"),
				saved(() =>
					call("preview_audience").then((r) =>
						frappe.confirm(audience_text(r.message) + "<br><br>" + __("Send now?"), () => run("send_now", __("Sending started.")))
					)
				)
			).addClass("btn-primary");
		}
		if (["Draft", "Failed", "Cancelled"].includes(status) && frm.doc.scheduled_at) {
			frm.add_custom_button(__("Schedule"), saved(() => run("schedule", __("Scheduled."))));
		}
		if (status === "Scheduled") {
			frm.add_custom_button(__("Cancel Schedule"), () =>
				frappe.confirm(__("Cancel this campaign? It will not be sent."), () => run("cancel_schedule", __("Cancelled.")))
			);
		}
		if (status === "Sent") {
			frm.add_custom_button(__("Refresh Results"), () => run("refresh_results", __("Results updated.")));
			frm.add_custom_button(__("Messages"), () => frappe.set_route("List", "Mkt Message Log", { campaign: frm.doc.name }));
		}

		if (status === "Sending") {
			frm.set_intro(__("Sending in the background. Reload in a moment to see the result."), "blue");
		} else if (status === "Failed") {
			frm.set_intro(__("Not sent: {0}", [frm.doc.failure_reason || ""]), "red");
		} else if (status === "Scheduled") {
			frm.set_intro(__("Will be sent on {0}.", [frappe.datetime.str_to_user(frm.doc.scheduled_at)]), "orange");
		}
	},
});
