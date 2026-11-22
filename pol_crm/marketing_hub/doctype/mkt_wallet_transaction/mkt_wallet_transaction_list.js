frappe.listview_settings["Mkt Wallet Transaction"] = {
	add_fields: ["txn_type", "amount"],
	get_indicator(doc) {
		return [__(doc.txn_type), doc.amount >= 0 ? "green" : "orange", "txn_type,=," + doc.txn_type];
	},
	onload(listview) {
		const show_balance = () =>
			frappe.call("pol_crm.marketing_hub.wallet.get_wallet_summary").then((r) => {
				const b = (r.message || {}).balance || {};
				const iqd = pol_crm.marketing.iqd;
				listview.page.set_indicator(
					__("Balance {0} (gift {1} + paid {2})", [iqd(b.total), iqd(b.gift), iqd(b.paid)]),
					b.total > 0 ? "green" : "red"
				);
			});
		show_balance();

		if (frappe.user.has_role("System Manager")) {
			listview.page.add_inner_button(__("Top Up"), () =>
				frappe.prompt(
					[
						{ fieldtype: "Currency", fieldname: "amount", label: __("Amount (IQD)"), reqd: 1, default: 50000 },
						{ fieldtype: "Data", fieldname: "description", label: __("Note") },
					],
					(values) =>
						frappe.call("pol_crm.marketing_hub.wallet.top_up", values).then(() => {
							listview.refresh();
							show_balance();
						}),
					__("Top Up the Marketing Wallet"),
					__("Add")
				)
			);
		}
	},
};
