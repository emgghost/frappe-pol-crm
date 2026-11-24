frappe.ui.form.on("Mkt Campaign", {
	setup(frm) {
		pol_crm.marketing.set_options(frm, "last_purchase");
		pol_crm.marketing.set_options(frm, "channel");
		pol_crm.marketing.set_options(frm, "campaign_type");
		frm.fields_dict.segments.grid.update_docfield_property(
			"segment",
			"options",
			pol_crm.marketing.options("segment")
		);
	},

	refresh(frm) {
		const [label, color] = pol_crm.marketing.labels.status[frm.doc.status] || [frm.doc.status, "gray"];
		frm.page.set_indicator(label, color);
		const draft = frm.doc.status === "Draft";
		if (!draft) {
			// Once it is scheduled or sent the campaign is a record of what went out.
			frm.disable_form();
		}
		if (frm.is_new()) return;

		if (draft) {
			frm.add_custom_button(__("پیش‌نمایش"), () => show_preview(frm));
			frm.add_custom_button(__("ارسال آزمایشی"), () => pol_crm.marketing.test_send(frm));
			frm.add_custom_button(frm.doc.send_at ? __("زمان‌بندی ارسال") : __("ارسال"), () => confirm_send(frm)).addClass(
				"btn-primary"
			);
		}
		if (frm.doc.status === "Scheduled") {
			frm.add_custom_button(__("لغو ارسال"), () => frm.call("cancel_campaign").then(() => frm.reload_doc()));
		}
		if (["Scheduled", "Cancelled"].includes(frm.doc.status)) {
			frm.add_custom_button(__("برگشت به پیش‌نویس"), () => frm.call("back_to_draft").then(() => frm.reload_doc()));
		}
	},
});

function show_preview(frm) {
	frm.call("preview").then((r) => {
		const p = r.message;
		frappe.msgprint({
			title: __("پیش‌نمایش کمپین"),
			message: `
				<p><b>${__("تعداد مخاطبان")}:</b> ${p.count}</p>
				${p.sample.length ? `<p class="text-muted">${__("مثلاً")}: ${p.sample.map(frappe.utils.escape_html).join("، ")}</p>` : ""}
				<p><b>${__("متن پیام")}:</b></p>
				<div style="white-space:pre-wrap;border:1px solid var(--border-color);border-radius:8px;padding:10px">${frappe.utils.escape_html(p.text)}</div>`,
		});
	});
}

function confirm_send(frm) {
	const save = frm.is_dirty() ? frm.save() : Promise.resolve();
	save.then(() =>
		frm.call("preview").then((r) => {
			const when = frm.doc.send_at ? frappe.datetime.str_to_user(frm.doc.send_at) : __("همین حالا");
			frappe.confirm(
				__("این کمپین برای {0} مشتری، {1} فرستاده می‌شود. ادامه می‌دهید؟", [r.message.count, when]),
				() => frm.call("schedule").then(() => frm.reload_doc())
			);
		})
	);
}
