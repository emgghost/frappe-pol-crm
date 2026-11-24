frappe.query_reports["Marketing Performance"] = {
	filters: [
		{ fieldname: "from_date", label: __("از تاریخ"), fieldtype: "Date", default: frappe.datetime.add_days(frappe.datetime.get_today(), -30), reqd: 1 },
		{ fieldname: "to_date", label: __("تا تاریخ"), fieldtype: "Date", default: frappe.datetime.get_today(), reqd: 1 },
		{
			fieldname: "kind",
			label: __("نوع"),
			fieldtype: "Select",
			options: [
				{ value: "", label: __("همه") },
				{ value: "Campaign", label: __("کمپین") },
				{ value: "Automation", label: __("اتوماسیون") },
			],
		},
		{ fieldname: "window_days", label: __("خرید تا چند روز بعد از پیام"), fieldtype: "Int", default: 14 },
	],
};
