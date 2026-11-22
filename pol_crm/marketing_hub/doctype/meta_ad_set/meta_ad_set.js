frappe.ui.form.on("Meta Ad Set", {
	refresh(frm) {
		const m = pol_crm.marketing;
		m.add_picker(frm, "governorates", __("Governorates"), m.GOVERNORATES);
		m.add_picker(frm, "interests", __("Interests"), [
			"Fashion", "Shopping", "Food & dining", "Beauty", "Home & furniture", "Electronics",
			"Sports & fitness", "Family & parenting", "Cars", "Travel", "Weddings", "Education",
		]);
		if (frm.is_new()) return;
		const open = (doctype) => (r) => r.message && frappe.set_route("Form", doctype, r.message);
		frm.add_custom_button(__("Add Ad"), () => frm.call({ doc: frm.doc, method: "add_ad" }).then(open("Meta Ad")));
		frm.add_custom_button(__("Duplicate"), () => frm.call({ doc: frm.doc, method: "duplicate" }).then(open("Meta Ad Set")));
		frm.add_custom_button(__("Ads"), () => frappe.set_route("List", "Meta Ad", { ad_set: frm.doc.name }));
	},
});
