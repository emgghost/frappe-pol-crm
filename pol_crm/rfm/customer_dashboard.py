import frappe
from frappe import _


def get_dashboard_for_customer(data=None):
	if not data:
		data = frappe._dict()

	transactions = list(data.get("transactions", []))
	transactions.append(
		{
			"label": _("باشگاه مشتریان و بازاریابی (POL CRM)"),
			"items": ["Loyalty Offer", "Mkt Message Log"],
		}
	)
	data["transactions"] = transactions
	return data
