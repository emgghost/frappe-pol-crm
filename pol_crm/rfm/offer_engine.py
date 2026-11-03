"""
Offer Decision Engine for POL CRM
Evaluates customer segments and purchase history to automatically provision
targeted offers (discount coupons or bonus points) to at-risk or high-potential customers.
"""

import random
import string
from datetime import datetime
import frappe
from frappe.utils import nowdate, add_days, getdate, date_diff, flt, cint

DEFAULT_OFFER_RULES = [
    {
        "reason": "SECOND_ORDER",
        "offer_type": "DISCOUNT_CODE",
        "percentage_value": 15,
        "min_days": 15,
        "max_days": 45,
        "validity_days": 7,
        "cooldown_days": 60,
        "once_per_lifetime": 1,
    },
    {
        "reason": "POTENTIAL_LOYALIST",
        "offer_type": "DISCOUNT_CODE",
        "percentage_value": 10,
        "min_days": 7,
        "max_days": 60,
        "validity_days": 10,
        "cooldown_days": 45,
        "once_per_lifetime": 0,
        "target_segment": "POTENTIAL_LOYALIST",
    },
    {
        "reason": "AT_RISK",
        "offer_type": "DISCOUNT_CODE",
        "percentage_value": 20,
        "min_days": 30,
        "max_days": 120,
        "validity_days": 7,
        "cooldown_days": 60,
        "once_per_lifetime": 0,
        "target_segment": "AT_RISK",
    },
    {
        "reason": "CANT_LOSE",
        "offer_type": "DISCOUNT_CODE",
        "percentage_value": 25,
        "min_days": 45,
        "max_days": 180,
        "validity_days": 5,
        "cooldown_days": 90,
        "once_per_lifetime": 0,
        "target_segment": "CANT_LOSE",
    },
]


def generate_coupon_code(prefix="POL"):
    """Generate a clean, unambiguous single-use discount code."""
    chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    random_str = "".join(random.choices(chars, k=6))
    return f"{prefix}-{random_str}"


def customer_has_recent_offer(customer, reason, cooldown_days, once_per_lifetime=False):
    """Check if customer has received this offer recently or ever."""
    if not frappe.db.exists("DocType", "Loyalty Offer"):
        return False

    filters = {"customer": customer, "reason": reason}
    if once_per_lifetime:
        return frappe.db.exists("Loyalty Offer", filters) is not None

    cutoff_date = add_days(nowdate(), -cooldown_days)
    recent_offers = frappe.db.sql(
        """
        SELECT name FROM `tabLoyalty Offer`
        WHERE customer = %s AND reason = %s AND creation >= %s
        LIMIT 1
        """,
        (customer, reason, cutoff_date),
    )
    return len(recent_offers) > 0


def get_or_create_loyalty_pricing_rule(percentage_discount):
    """
    Ensure a standard Pricing Rule exists in ERPNext for the given discount percentage.
    In ERPNext, Coupon Code requires a mandatory link to Pricing Rule.
    """
    if not frappe or not hasattr(frappe, "db") or not frappe.db.exists("DocType", "Pricing Rule"):
        return None

    rule_name = f"POL Loyalty {int(percentage_discount)}% Discount"

    # 1. Search for existing Pricing Rule by title or name
    existing = frappe.db.get_value(
        "Pricing Rule",
        {"title": rule_name, "coupon_code_based": 1},
        "name",
    )
    if existing:
        return existing

    if frappe.db.exists("Pricing Rule", rule_name):
        return rule_name

    # 2. Resolve default company if available
    company = None
    if hasattr(frappe, "defaults") and hasattr(frappe.defaults, "get_user_default"):
        company = frappe.defaults.get_user_default("Company")
    if not company and frappe.db.exists("DocType", "Global Defaults"):
        company = frappe.db.get_single_value("Global Defaults", "default_company")
    if not company and frappe.db.exists("DocType", "Company"):
        first_company = frappe.get_all("Company", limit=1, pluck="name")
        if first_company:
            company = first_company[0]

    # 3. Create Pricing Rule doc
    try:
        pr_data = {
            "doctype": "Pricing Rule",
            "title": rule_name,
            "pricing_rule_name": rule_name,
            "apply_on": "Transaction",
            "price_or_product_discount": "Price",
            "coupon_code_based": 1,
            "discount_percentage": flt(percentage_discount),
            "selling": 1,
        }
        if company:
            pr_data["company"] = company

        rule = frappe.get_doc(pr_data)
        rule.insert(ignore_permissions=True)
        return rule.name or rule_name
    except Exception as e:
        frappe.logger("pol_crm").warning(
            f"Could not auto-create Pricing Rule for {percentage_discount}%: {str(e)}"
        )
        return None


def create_erpnext_coupon(coupon_code, customer, percentage_discount, valid_until, pricing_rule=None):
    """
    Integrate with ERPNext Coupon Code if available.
    Ensures Pricing Rule link is resolved and attached to satisfy ERPNext schema.
    """
    if not frappe or not hasattr(frappe, "db") or not frappe.db.exists("DocType", "Coupon Code"):
        return False

    try:
        if not pricing_rule:
            pricing_rule = get_or_create_loyalty_pricing_rule(percentage_discount)

        coupon_data = {
            "doctype": "Coupon Code",
            "coupon_name": coupon_code,
            "coupon_code": coupon_code,
            "coupon_type": "Promotional",
            "valid_from": nowdate(),
            "valid_upto": valid_until,
            "maximum_use": 1,
        }
        if pricing_rule:
            coupon_data["pricing_rule"] = pricing_rule

        coupon = frappe.get_doc(coupon_data)
        coupon.insert(ignore_permissions=True)
        return True
    except Exception as e:
        frappe.logger("pol_crm").warning(f"Could not create native ERPNext coupon: {str(e)}")
        return False


def provision_offer(customer, rule):
    """Create a new Loyalty Offer record and notify the customer."""
    valid_until = add_days(nowdate(), rule.get("validity_days", 7))
    coupon_code = generate_coupon_code(rule.get("reason")[:4])

    # If native ERPNext coupon is supported, link it
    create_erpnext_coupon(coupon_code, customer, rule.get("percentage_value"), valid_until)

    offer_doc = None
    if frappe.db.exists("DocType", "Loyalty Offer"):
        offer_doc = frappe.get_doc({
            "doctype": "Loyalty Offer",
            "customer": customer,
            "reason": rule["reason"],
            "offer_type": rule.get("offer_type", "DISCOUNT_CODE"),
            "discount_code": coupon_code,
            "percentage_value": rule.get("percentage_value"),
            "valid_from": nowdate(),
            "valid_until": valid_until,
            "status": "ACTIVE",
        })
        offer_doc.insert(ignore_permissions=True)
        frappe.db.commit()

    frappe.logger("pol_crm").info(
        f"Provisioned offer {coupon_code} ({rule['reason']}) for customer {customer}"
    )

    # Trigger messaging engine to send the offer SMS
    try:
        from pol_crm.messaging.policy import enqueue_marketing_message
        customer_doc = frappe.get_doc("Customer", customer)
        mobile_no = customer_doc.mobile_no or customer_doc.phone
        if mobile_no:
            message_text = (
                f"مشتری گرامی {customer_doc.customer_name}، "
                f"کد تخفیف اختصاصی {rule.get('percentage_value')}% برای شما: {coupon_code}\n"
                f"مهلت استفاده: تا {valid_until}"
            )
            enqueue_marketing_message(
                customer=customer,
                phone=mobile_no,
                text=message_text,
                channel="SMS",
                template_code="OFFER_PROMO",
                template_tokens={
                    "token": coupon_code,
                    "token2": str(rule.get("percentage_value")),
                    "code": coupon_code,
                    "percent": str(rule.get("percentage_value")),
                },
                category="marketing",
            )
    except Exception as e:
        frappe.logger("pol_crm").error(f"Failed to dispatch offer notification: {str(e)}")

    return coupon_code


def evaluate_customer_for_offers(customer_doc):
    """Check a single customer against all active offer rules."""
    # Check marketing consent
    if customer_doc.get("custom_mkt_opted_out_all") or customer_doc.get("custom_mkt_sms_opted_out"):
        return None

    days_since_purchase = cint(customer_doc.get("custom_days_since_last_purchase") or 0)
    purchase_count = cint(customer_doc.get("custom_paid_invoices_count") or 0)
    segment = customer_doc.get("custom_rfm_segment")

    for rule in DEFAULT_OFFER_RULES:
        reason = rule["reason"]

        # Rule 1: Second Order (requires exactly 1 previous purchase)
        if reason == "SECOND_ORDER":
            if purchase_count != 1:
                continue
            if not (rule["min_days"] <= days_since_purchase <= rule["max_days"]):
                continue

        # Rule 2: Segment-based offer (AT_RISK, POTENTIAL_LOYALIST, CANT_LOSE)
        else:
            if segment != rule.get("target_segment"):
                continue
            if days_since_purchase < rule.get("min_days", 0):
                continue
            if rule.get("max_days") and days_since_purchase > rule["max_days"]:
                continue

        # Check cooldown and lifetime restrictions
        if customer_has_recent_offer(
            customer_doc.name,
            reason,
            rule.get("cooldown_days", 30),
            rule.get("once_per_lifetime", False),
        ):
            continue

        # Passed all checks -> provision offer!
        return provision_offer(customer_doc.name, rule)

    return None


def daily_offer_decision_pass(batch_size=1000):
    """Nightly scheduler job running offer decisions across customer base using batch chunking."""
    frappe.logger("pol_crm").info("Starting daily offer decision pass...")

    fields = [
        "name",
        "customer_name",
        "mobile_no",
        "phone",
        "custom_rfm_segment",
        "custom_days_since_last_purchase",
        "custom_paid_invoices_count",
        "custom_mkt_opted_out_all",
        "custom_mkt_sms_opted_out",
    ]
    filters = {"disabled": 0}

    offers_count = 0
    start = 0

    while True:
        kwargs = {
            "fields": fields,
            "filters": filters,
            "order_by": "name asc",
        }
        if batch_size:
            kwargs["limit_start"] = start
            kwargs["limit_page_length"] = batch_size

        chunk = frappe.get_all("Customer", **kwargs)
        if not chunk:
            break

        for cust in chunk:
            res = evaluate_customer_for_offers(cust)
            if res:
                offers_count += 1

        if not batch_size or len(chunk) < batch_size:
            break

        start += len(chunk)

    frappe.logger("pol_crm").info(f"Daily offer decision pass completed. Provisioned {offers_count} offers.")
    return offers_count
