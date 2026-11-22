frappe.ui.form.on("Marketing Hub Settings", {
	refresh(frm) {
		frm.add_custom_button(__("Test Meta Ads Connection"), () => {
			const test = () =>
				frappe.call("pol_crm.marketing_hub.meta_api.test_connection").then((r) => {
					const out = r.message;
					frappe.msgprint({
						title: __("Connected to Meta"),
						indicator: "green",
						message: __("Ad account: {0} ({1})<br>Page: {2}", [out.account, out.currency, out.page]),
					});
					frm.reload_doc();
				});
			frm.is_dirty() ? frm.save().then(test) : test();
		});
	},
});
