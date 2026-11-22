frappe.ui.form.on("Meta Ad Campaign", {
	refresh(frm) {
		if (frm.is_new()) return;
		const status = frm.doc.status;
		const run = (method, args) => frm.call({ doc: frm.doc, method, args }).then((r) => frm.reload_doc().then(() => r.message));
		const open = (doctype) => (r) => r.message && frappe.set_route("Form", doctype, r.message);

		if (["Draft", "Rejected"].includes(status)) {
			frm.add_custom_button(__("Publish"), () =>
				run("publish").then((out) =>
					frappe.show_alert(
						{
							message:
								out && out.sent_to_meta
									? __("Sent to Meta. It goes live once Meta approves it.")
									: __("Marked In Review here only: Meta Ads is not connected in Marketing Hub Settings."),
							indicator: out && out.sent_to_meta ? "green" : "orange",
						},
						10
					)
				)
			).addClass("btn-primary");
		}
		if (frm.doc.meta_campaign_id) {
			frm.add_custom_button(__("Sync from Meta"), () =>
				frappe.call("pol_crm.marketing_hub.meta_api.sync_now", { campaign: frm.doc.name }).then(() => frm.reload_doc())
			);
		}
		if (status === "Active") frm.add_custom_button(__("Pause"), () => run("pause"));
		if (status === "Paused") frm.add_custom_button(__("Resume"), () => run("resume"));
		if (["Draft", "Rejected", "Paused"].includes(status)) {
			frm.add_custom_button(__("Add Ad Set"), () => frm.call({ doc: frm.doc, method: "add_ad_set" }).then(open("Meta Ad Set")));
		}
		frm.add_custom_button(__("Duplicate"), () => frm.call({ doc: frm.doc, method: "duplicate" }).then(open("Meta Ad Campaign")));
		if (frappe.user.has_role("System Manager")) {
			if (status === "In Review") frm.add_custom_button(__("Mark Active"), () => run("mark_active"), __("Review"));
			if (["In Review", "Active"].includes(status)) {
				frm.add_custom_button(
					__("Reject"),
					() => frappe.prompt({ fieldtype: "Small Text", fieldname: "reason", label: __("Reason"), reqd: 1 }, (v) => run("reject", v), __("Reject")),
					__("Review")
				);
			}
		}
		if (status === "Rejected" && frm.doc.rejection_reason) {
			frm.set_intro(__("Rejected: {0}", [frm.doc.rejection_reason]), "red");
		}

		// Campaign -> Ad Set -> Ad, with what still blocks publishing.
		frm.call({ doc: frm.doc, method: "get_tree" }).then((r) => {
			const tree = r.message || { ad_sets: [], issues: [] };
			const esc = frappe.utils.escape_html;
			let html = tree.ad_sets
				.map((s) => {
					const ads = s.ads
						.map((a) => `<li><a href="/app/meta-ad/${a.name}">${esc(a.ad_name)}</a> <span class="text-muted">${esc(a.source === "Existing post" ? "Post" : a.format || "")}</span></li>`)
						.join("");
					return `<div class="mb-2"><a href="/app/meta-ad-set/${s.name}"><b>${esc(s.ad_set_name)}</b></a>
						<span class="text-muted"> ${pol_crm.marketing.iqd(s.daily_budget)}/${__("day")} × ${s.days || 0} ${__("days")}</span>
						<ul class="mb-0">${ads || `<li class="text-muted">${__("No ads yet")}</li>`}</ul></div>`;
				})
				.join("");
			if (!html) html = `<div class="text-muted">${__("No ad sets yet. Use Add Ad Set.")}</div>`;
			if (tree.issues.length && ["Draft", "Rejected"].includes(status)) {
				html += `<div class="text-danger small mt-2"><b>${__("Before publishing")}</b><ul class="mb-0">${tree.issues
					.map((i) => `<li>${esc(i)}</li>`)
					.join("")}</ul></div>`;
			}
			frm.dashboard.add_section(html, __("Ad Sets and Ads"));
			frm.dashboard.show();
		});
	},
});
