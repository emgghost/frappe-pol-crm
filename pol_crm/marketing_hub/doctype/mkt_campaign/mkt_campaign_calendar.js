frappe.views.calendar["Mkt Campaign"] = {
	field_map: {
		start: "scheduled_at",
		end: "scheduled_at",
		id: "name",
		title: "campaign_name",
		allDay: "all_day",
	},
	get_events_method: "frappe.desk.calendar.get_events",
};
