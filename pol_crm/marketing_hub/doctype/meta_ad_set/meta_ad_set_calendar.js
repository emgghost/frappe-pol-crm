frappe.views.calendar["Meta Ad Set"] = {
	field_map: {
		start: "start_date",
		end: "end_date",
		id: "name",
		title: "ad_set_name",
		allDay: "all_day",
	},
	get_events_method: "frappe.desk.calendar.get_events",
};
