from frappe import _


def get_data():
	return {
		"fieldname": "scenario",
		"transactions": [
			{
				"label": _("پیام‌ها"),
				"items": ["Mkt Message Log"],
			},
		],
	}
