frappe.views.calendar["Loyalty Offer"] = {
	field_map: {
		start: "valid_from",
		end: "valid_until",
		id: "name",
		title: "discount_code",
		allDay: "all_day",
	},
	style_map: {
		ACTIVE: "success",
		USED: "info",
		EXPIRED: "danger",
	},
	get_events_method: "frappe.desk.calendar.get_events",
};
