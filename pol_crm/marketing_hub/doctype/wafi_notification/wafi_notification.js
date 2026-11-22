frappe.ui.form.on("Wafi Notification", {
	refresh(frm) {
		pol_crm.marketing.wafi_review_buttons(frm);
	},
});
