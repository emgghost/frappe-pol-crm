// Shared desk helpers for the Marketing Hub forms and lists.
frappe.provide("pol_crm.marketing");

pol_crm.marketing.GOVERNORATES = [
	"Baghdad", "Basra", "Nineveh", "Erbil", "Najaf", "Karbala", "Sulaymaniyah", "Dhi Qar", "Anbar",
	"Diyala", "Kirkuk", "Babil", "Wasit", "Maysan", "Salah al-Din", "Al-Qadisiyyah", "Al-Muthanna", "Dohuk",
];
pol_crm.marketing.ACTIVITIES = ["Very Active", "Active", "New Lead", "Re-engage", "No Activity"];
pol_crm.marketing.DEFAULT_TIERS = ["Bronze", "Silver", "Gold", "Platinum"];

pol_crm.marketing.iqd = (value) => format_number(value || 0, null, 0) + " IQD";

// Tick several values for a comma-separated field (governorates, tiers, activity).
pol_crm.marketing.pick_many = function (frm, fieldname, title, options) {
	const current = (frm.doc[fieldname] || "").split(",").map((s) => s.trim()).filter(Boolean);
	const dialog = new frappe.ui.Dialog({
		title,
		fields: [
			{
				fieldtype: "MultiCheck",
				fieldname: "values",
				columns: 2,
				options: options.map((o) => ({ label: __(o), value: o, checked: current.includes(o) })),
			},
		],
		primary_action_label: __("Set"),
		primary_action(values) {
			frm.set_value(fieldname, (values.values || []).join(", "));
			dialog.hide();
		},
	});
	dialog.show();
};

pol_crm.marketing.add_picker = function (frm, fieldname, title, options) {
	const field = frm.get_field(fieldname);
	if (!field || field.$wrapper.find(".pol-pick").length) return;
	$(`<a class="pol-pick small">${__("Pick from list")}</a>`)
		.appendTo(field.$wrapper)
		.on("click", () => {
			Promise.resolve(typeof options === "function" ? options() : options).then((list) =>
				pol_crm.marketing.pick_many(frm, fieldname, title, list)
			);
		});
};

pol_crm.marketing.add_tier_picker = function (frm, fieldname) {
	pol_crm.marketing.add_picker(frm, fieldname, __("Club Tiers"), () =>
		frappe
			.call("pol_crm.marketing_hub.utils.get_club_tiers")
			.then((r) => (r.message && r.message.length ? r.message : pol_crm.marketing.DEFAULT_TIERS))
	);
};

// Ready-made campaigns / automations.
pol_crm.marketing.pick_template = function (kind) {
	frappe.call("pol_crm.marketing_hub.templates.get_templates", { kind }).then((r) => {
		const templates = r.message || [];
		const dialog = new frappe.ui.Dialog({
			title: kind === "campaign" ? __("Campaign Templates") : __("Automation Templates"),
			fields: [
				{
					fieldtype: "Select",
					fieldname: "template",
					label: __("Template"),
					reqd: 1,
					options: templates.map((t) => ({ value: t.id, label: t.name + (t.club ? " (Club)" : "") })),
					change() {
						const picked = templates.find((t) => t.id === dialog.get_value("template"));
						dialog.set_df_property("template", "description", picked ? __(picked.desc) : "");
					},
				},
				{ fieldtype: "Data", fieldname: "name", label: __("Name"), description: __("Leave empty to use the template name.") },
			],
			primary_action_label: __("Create"),
			primary_action(values) {
				frappe
					.call("pol_crm.marketing_hub.templates.create_from_template", { template_id: values.template, name: values.name })
					.then((res) => {
						dialog.hide();
						const out = res.message;
						if (out.name) frappe.set_route("Form", out.doctype, out.name);
						else frappe.new_doc(out.doctype, out.values);
					});
			},
		});
		dialog.show();
	});
};

// Meta Ad has no script of its own: its only action is Duplicate.
frappe.ui.form.on("Meta Ad", {
	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button(__("Duplicate"), () =>
			frm.call({ doc: frm.doc, method: "duplicate" }).then((r) => r.message && frappe.set_route("Form", "Meta Ad", r.message))
		);
	},
});

// Wafi Ad / Offer / Promote / Notification share one review flow.
pol_crm.marketing.review_indicator = function (doc) {
	const colors = {
		Draft: "gray",
		"In Review": "orange",
		Approved: "blue",
		Live: "green",
		Completed: "darkgrey",
		Rejected: "red",
		Cancelled: "gray",
	};
	return [__(doc.status), colors[doc.status] || "gray", "status,=," + doc.status];
};

pol_crm.marketing.wafi_review_buttons = function (frm) {
	if (frm.is_new()) return;
	const status = frm.doc.status;
	const run = (method, args) => frm.call({ doc: frm.doc, method, args }).then((r) => frm.reload_doc().then(() => r.message));

	if (["Draft", "Rejected"].includes(status)) {
		frm.add_custom_button(__("Send for Review"), () => {
			const go = () => {
				const price = frm.doc.total_price || 0;
				const question = price
					? __("{0} will be taken from the Marketing Wallet. It is returned if the request is rejected or cancelled. Send for review?", [
							pol_crm.marketing.iqd(price),
					  ])
					: __("This is free. Send it for review?");
				frappe.confirm(question, () =>
					run("submit_for_review").then((out) => {
						out = out || {};
						frappe.show_alert(
							{
								message: out.pushed_to_wafi
									? __("Sent to Wafi for review.")
									: __("Marked In Review here, but not delivered to Wafi: {0}", [out.wafi_error]),
								indicator: out.pushed_to_wafi ? "green" : "orange",
							},
							10
						);
					})
				);
			};
			frm.is_dirty() ? frm.save().then(go) : go();
		}).addClass("btn-primary");
	} else {
		frm.disable_form();
	}

	if (["Draft", "In Review", "Approved"].includes(status)) {
		frm.add_custom_button(__("Cancel Request"), () =>
			frappe.confirm(__("Cancel this request? Any payment goes back to the Marketing Wallet."), () => run("cancel_request"))
		);
	}
	if (frappe.user.has_role("System Manager")) {
		if (status === "In Review") {
			frm.add_custom_button(__("Approve"), () => run("approve"), __("Review"));
		}
		if (["In Review", "Approved"].includes(status)) {
			frm.add_custom_button(
				__("Reject"),
				() => frappe.prompt({ fieldtype: "Small Text", fieldname: "reason", label: __("Reason"), reqd: 1 }, (v) => run("reject", v), __("Reject")),
				__("Review")
			);
		}
	}
	if (status === "In Review") {
		frm.set_intro(__("In the review queue. It will not go live until it is approved."), "orange");
	} else if (status === "Rejected" && frm.doc.review_note) {
		frm.set_intro(__("Rejected: {0}", [frm.doc.review_note]), "red");
	}
};
