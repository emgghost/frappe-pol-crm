frappe.query_reports["Marketing Performance"] = {
	filters: [
		{ fieldname: "from_date", label: __("From"), fieldtype: "Date", default: frappe.datetime.add_days(frappe.datetime.get_today(), -30), reqd: 1 },
		{ fieldname: "to_date", label: __("To"), fieldtype: "Date", default: frappe.datetime.get_today(), reqd: 1 },
		{ fieldname: "platform", label: __("Platform"), fieldtype: "Select", options: "\nWhatsApp\nInstagram\nFacebook\nWafi App\nSMS\nTelegram" },
		{ fieldname: "type", label: __("Type"), fieldtype: "Select", options: "\nCampaign\nAutomation\nMeta Ad\nWafi" },
		{ fieldname: "status", label: __("Status"), fieldtype: "Data" },
	],
};
