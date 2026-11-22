"""
Marketing Wallet: one balance for every paid marketing action.

Two buckets, kept as signed amounts on Mkt Wallet Transaction:
  gift - welcome credit, expires at the end of its month, spent first
  paid - what the merchant topped up, never expires
"""

import frappe
from frappe.utils import cint, flt, get_last_day, nowdate

from pol_crm.marketing_hub.utils import hub_settings, split_csv

TXN = "Mkt Wallet Transaction"


def split_charge(amount, gift_balance):
	"""Gift credit is used before paid balance. Returns (from_gift, from_paid)."""
	amount = max(flt(amount), 0)
	from_gift = min(max(flt(gift_balance), 0), amount)
	return from_gift, amount - from_gift


def get_balance():
	row = frappe.db.sql(
		f"select coalesce(sum(gift_amount), 0), coalesce(sum(paid_amount), 0) from `tab{TXN}`"
	)
	gift = max(flt(row[0][0]), 0) if row else 0
	paid = flt(row[0][1]) if row else 0
	return {"gift": gift, "paid": paid, "total": gift + paid}


def can_pay(amount):
	return flt(amount) <= 0 or get_balance()["total"] >= flt(amount)


def _add(txn_type, gift_amount, paid_amount, description, reference_doctype=None, reference_name=None, gift_expiry_date=None):
	doc = frappe.get_doc(
		{
			"doctype": TXN,
			"posting_date": nowdate(),
			"txn_type": txn_type,
			"gift_amount": flt(gift_amount),
			"paid_amount": flt(paid_amount),
			"amount": flt(gift_amount) + flt(paid_amount),
			"description": (description or txn_type)[:140],
			"reference_doctype": reference_doctype,
			"reference_name": reference_name,
			"gift_expiry_date": gift_expiry_date,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def charge(amount, description, reference_doctype=None, reference_name=None):
	"""Take `amount` from the wallet. Throws when the balance is too low."""
	amount = flt(amount)
	if amount <= 0:
		return None
	balance = get_balance()
	if balance["total"] < amount:
		frappe.throw(
			frappe._("The Marketing Wallet has {0} IQD but this costs {1} IQD. Top up the wallet first.").format(
				f"{balance['total']:,.0f}", f"{amount:,.0f}"
			),
			title=frappe._("Not enough wallet balance"),
		)
	from_gift, from_paid = split_charge(amount, balance["gift"])
	return _add("Charge", -from_gift, -from_paid, description, reference_doctype, reference_name)


def refund_transaction(txn_name, description=None):
	"""Give back what a charge took, to the same buckets."""
	if not txn_name or not frappe.db.exists(TXN, txn_name):
		return None
	txn = frappe.db.get_value(
		TXN, txn_name, ["gift_amount", "paid_amount", "description", "reference_doctype", "reference_name"], as_dict=True
	)
	return _add(
		"Refund",
		-flt(txn.gift_amount),
		-flt(txn.paid_amount),
		description or f"Refund: {txn.description}",
		txn.reference_doctype,
		txn.reference_name,
	)


@frappe.whitelist()
def top_up(amount, description=None):
	"""Record money added to the wallet. There is no payment gateway here: an administrator records it."""
	frappe.only_for("System Manager")
	amount = flt(amount)
	if amount <= 0:
		frappe.throw(frappe._("Enter an amount above zero."))
	name = _add("Top-up", 0, amount, description or "Top up")
	return {"transaction": name, "balance": get_balance()}


@frappe.whitelist()
def get_wallet_summary():
	frappe.only_for(["System Manager", "Marketing Manager"])
	settings = hub_settings()
	return {
		"balance": get_balance(),
		"whatsapp_message_price": settings.whatsapp_message_price,
		"transactions": frappe.get_all(
			TXN, fields=["name", "posting_date", "txn_type", "amount", "description"], order_by="creation desc", limit=10
		),
	}


def grant_monthly_gift():
	"""Daily: once a month, expire unused gift credit and grant the next welcome gift."""
	settings = hub_settings()
	month_key = nowdate()[:7]
	if settings.last_gift_month == month_key:
		return

	leftover = get_balance()["gift"]
	if leftover > 0:
		_add("Gift Expiry", -leftover, 0, "Unused gift credit expired")

	schedule = [flt(x) for x in split_csv(settings.gift_schedule)]
	granted = cint(settings.gift_months_granted)
	if granted < len(schedule) and schedule[granted] > 0:
		_add("Gift", schedule[granted], 0, f"Welcome gift - month {granted + 1}", gift_expiry_date=get_last_day(nowdate()))
		frappe.db.set_single_value("Marketing Hub Settings", "gift_months_granted", granted + 1)
	frappe.db.set_single_value("Marketing Hub Settings", "last_gift_month", month_key)
	frappe.clear_document_cache("Marketing Hub Settings", "Marketing Hub Settings")
