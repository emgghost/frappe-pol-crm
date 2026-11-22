frappe.ui.form.on("Wafi Promote Request", {
	refresh(frm) {
		pol_crm.marketing.wafi_review_buttons(frm);
	},
});
