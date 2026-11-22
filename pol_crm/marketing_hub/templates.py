"""
Ready-made campaigns and automations. Using a template creates a draft campaign or a
switched-off automation that the merchant reviews, edits and then sends or turns on.
"""

import frappe

from pol_crm.marketing_hub.utils import require_club

TEMPLATES = [
	# ---- campaigns: sent once
	{"id": "c-products", "kind": "campaign", "name": "New Products", "desc": "Tell your recent buyers what just arrived.",
		"doc": {"last_purchase": "In the last 90 days", "message": "Check out our new products! Visit us to see what just arrived."}},
	{"id": "c-branch", "kind": "campaign", "name": "New Branch", "desc": "Announce a new branch to your recent buyers.",
		"doc": {"last_purchase": "In the last 90 days", "message": "We opened a new branch! Come visit us at our new location."}},
	{"id": "c-seasonal", "kind": "campaign", "name": "Seasonal Discount", "desc": "Let your returning customers know the seasonal prices are on.",
		"doc": {"last_purchase": "Any time", "purchase_count": "More than once", "message": "Our seasonal discount is here! Enjoy special prices for a limited time."}},
	{"id": "c-occasion", "kind": "campaign", "name": "Occasion Greeting", "desc": "A one-time greeting for one occasion.",
		"doc": {"last_purchase": "In the last 90 days", "message": "Eid Mubarak! Wishing you and your family joy and peace, from all of us."}},
	{"id": "c-recent", "kind": "campaign", "name": "Recent Buyers Update", "desc": "A quick message to everyone who bought in the last 30 days.",
		"doc": {"last_purchase": "In the last 30 days", "message": "Thanks for shopping with us recently! Here's what's new this week."}},
	{"id": "c-winback", "kind": "campaign", "name": "Win-back Offer", "desc": "A one-time offer to customers who haven't bought in 45 days.",
		"doc": {"last_purchase": "Not in 45+ days", "offer": "Discount", "discount_percent": 10, "message": "We miss you! Come back this week and get {discount} off. Your code: {code}"}},
	{"id": "c-loyal", "kind": "campaign", "name": "Thank Your Repeat Buyers", "desc": "Thank customers who bought 5 times or more.",
		"doc": {"last_purchase": "Any time", "purchase_count": "5+ times", "offer": "Discount", "discount_percent": 10,
			"message": "You're one of our best customers, thank you! Enjoy {discount} off your next purchase. Your code: {code}"}},
	{"id": "c-event", "kind": "campaign", "name": "Event Invitation", "desc": "Invite customers, remind them 1 day before, thank them 1 day after.",
		"doc": {"campaign_type": "Event Invitation", "last_purchase": "In the last 90 days",
			"message": "You're invited! Join us for {event} on {date} at {place}. We'd love to see you there.",
			"reminder_enabled": 1, "reminder_message": "Reminder: {event} is tomorrow at {time}. See you there!",
			"thanks_enabled": 1, "thanks_message": "Thank you for coming! It was great to see you."}},
	{"id": "c-tier", "kind": "campaign", "club": 1, "name": "Top-Tier Reward", "desc": "Reward your Gold and Platinum club members.",
		"doc": {"campaign_type": "Retention", "club_tiers": "Gold, Platinum", "offer": "Discount", "discount_percent": 10,
			"message": "Thank you for being one of our top customers! Enjoy {discount} off your next purchase. Your code: {code}"}},
	# ---- automations: always on
	{"id": "a-bday", "kind": "automation", "name": "Birthday", "desc": "A birthday greeting with a gift, for every customer with a birthday on file.",
		"doc": {"trigger_type": "BIRTHDAY", "delay_days": 0, "discount_percent": 10, "coupon_validity_days": 7,
			"message_template": "Happy Birthday {name}! Here's a {discount} gift from us, valid for 7 days: {code}"}},
	{"id": "a-winback", "kind": "automation", "name": "Win-back", "desc": "Customers who stopped buying get a come-back offer.",
		"doc": {"trigger_type": "CHURN", "inactivity_days": 60, "discount_percent": 10, "max_sends": 1,
			"message_template": "We miss you! It's been a while. Come back and enjoy {discount} off: {code}"}},
	{"id": "a-lost", "kind": "automation", "name": "Lost Customers", "desc": "A discount to long-gone customers, repeated until they buy.",
		"doc": {"trigger_type": "CHURN", "inactivity_days": 120, "repeat_every_days": 45, "max_sends": 3, "discount_percent": 10,
			"message_template": "It's been a long time! Here's {discount} off to welcome you back: {code}"}},
	{"id": "a-first-rating", "kind": "automation", "name": "First Purchase Thanks & Rating", "desc": "Thank new customers and ask how the service was.",
		"doc": {"trigger_type": "AFTER_PURCHASE", "first_purchase_only": 1, "delay_days": 1,
			"message_template": "Thanks for your first order with us! How was your experience? Reply with a number from 1 to 5."}},
	{"id": "a-first-followup", "kind": "automation", "name": "First Purchase Follow-up", "desc": "A discount after the first purchase, so they come back soon.",
		"doc": {"trigger_type": "FIRST_PURCHASE", "delay_days": 1, "discount_percent": 10,
			"message_template": "Thanks for your first order! Here's {discount} off to welcome you back: {code}"}},
	{"id": "a-occasion", "kind": "automation", "name": "Occasion Greetings", "desc": "Greets your customers automatically, every year, on each occasion.",
		"doc": {"trigger_type": "OCCASION", "occasions": "Eid al-Fitr, Eid al-Adha, New Year", "delay_days": 0,
			"message_template": "Happy holidays from all of us! Wishing you and your family joy and peace."}},
	{"id": "a-spend", "kind": "automation", "name": "Spend Milestone Reward", "desc": "A reward when a customer's total spend reaches 500,000 IQD.",
		"doc": {"trigger_type": "SPEND_THRESHOLD", "spend_threshold": 500000, "discount_percent": 15,
			"message_template": "You've reached a spending milestone with us. Enjoy {discount} off as a thank-you: {code}"}},
	{"id": "a-count", "kind": "automation", "name": "Purchase Count Reward", "desc": "A reward on the 5th purchase.",
		"doc": {"trigger_type": "PURCHASE_COUNT", "purchase_count_target": 5, "discount_percent": 20,
			"message_template": "This is your 5th purchase with us. Here's {discount} off as a thank-you: {code}"}},
	{"id": "a-incomplete", "kind": "automation", "name": "Incomplete Order", "desc": "Reminds customers who started an order but didn't confirm.",
		"doc": {"trigger_type": "INCOMPLETE_ORDER", "delay_hours": 1,
			"message_template": "You still have an order waiting! Reply to finish it, we saved your items."}},
	{"id": "a-restock", "kind": "automation", "name": "Back-in-Stock Alert", "desc": "Tells waiting customers when a product is available again.",
		"doc": {"trigger_type": "BACK_IN_STOCK",
			"message_template": "Good news: {item} is back in stock! Order now before it runs out again."}},
	{"id": "a-bday-tier", "kind": "automation", "club": 1, "name": "Birthday Gift by Tier", "desc": "A birthday gift that grows with the club tier.",
		"doc": {"trigger_type": "BIRTHDAY_BY_TIER", "tier_discounts": "Bronze:5, Silver:10, Gold:15, Platinum:20",
			"message_template": "Happy Birthday {name}! Here's a special {discount} gift for you today: {code}"}},
	{"id": "a-thanks-points", "kind": "automation", "club": 1, "name": "Thanks + Points Balance", "desc": "After every purchase: a thank-you with the points balance.",
		"doc": {"trigger_type": "AFTER_PURCHASE", "delay_days": 0,
			"message_template": "Thank you for your purchase! You now have {points} points in our club."}},
	{"id": "a-usable", "kind": "automation", "club": 1, "name": "Usable Points Reminder", "desc": "Reminds customers they have points ready to use.",
		"doc": {"trigger_type": "POINTS_USABLE", "repeat_every_days": 14, "max_sends": 3,
			"message_template": "You have {points} points ready to use! Use them on your next visit."}},
	{"id": "a-expiry", "kind": "automation", "club": 1, "name": "Points Expiry Reminder", "desc": "Warns customers before their points expire.",
		"doc": {"trigger_type": "POINTS_EXPIRY", "points_before_days": "7",
			"message_template": "Heads up! {points} of your points expire on {date}. Use them before they're gone."}},
	{"id": "a-atrisk", "kind": "automation", "club": 1, "name": "At-Risk Platinum - Call Reminder", "desc": "A Platinum customer stopped buying: you get a reminder to call them.",
		"doc": {"trigger_type": "AT_RISK_CALL", "club_tiers": "Platinum", "inactivity_days": 30, "call_reminder": 1, "send_message": 0}},
]


ICONS = {
	"c-products": "🆕", "c-branch": "📍", "c-seasonal": "🏷️", "c-occasion": "🎊", "c-recent": "🛍️", "c-winback": "💌",
	"c-loyal": "🙌", "c-event": "🎟️", "c-tier": "🏅", "a-bday": "🎂", "a-winback": "💌", "a-lost": "🔄", "a-first-rating": "🙏",
	"a-first-followup": "🔁", "a-occasion": "🎊", "a-spend": "🏆", "a-count": "🛍️", "a-incomplete": "💬", "a-restock": "📦",
	"a-bday-tier": "🏅", "a-thanks-points": "⭐", "a-usable": "💰", "a-expiry": "⏳", "a-atrisk": "📞",
}
TRIGGER_LINES = {
	"BIRTHDAY": "On the customer's birthday",
	"BIRTHDAY_BY_TIER": "On the birthday, discount by club tier",
	"CHURN": "No purchase for {inactivity_days} days",
	"AFTER_PURCHASE": "After a purchase",
	"FIRST_PURCHASE": "After the first purchase",
	"OCCASION": "On each occasion, every year",
	"SPEND_THRESHOLD": "Total spend reaches {spend_threshold:,} IQD",
	"PURCHASE_COUNT": "On purchase number {purchase_count_target}",
	"INCOMPLETE_ORDER": "An order left unconfirmed for {delay_hours} hour(s)",
	"BACK_IN_STOCK": "Stock goes from 0 to available",
	"POINTS_USABLE": "Points reach the redeem level",
	"POINTS_EXPIRY": "{points_before_days} days before points expire",
	"AT_RISK_CALL": "No purchase for {inactivity_days} days: you get a call reminder",
}


def preset_lines(template):
	"""The two or three facts shown on a template card: who, when, what they get."""
	doc = template["doc"]
	lines = []
	if template["kind"] == "campaign":
		kind = doc.get("campaign_type", "All Customers")
		if kind == "Retention":
			lines.append(f"{doc.get('club_tiers')} club members")
		else:
			who = doc.get("last_purchase", "Any time")
			count = doc.get("purchase_count")
			lines.append("Bought: " + who.lower() + (f" · {count.lower()}" if count else ""))
		lines.append("You set the event date" if kind == "Event Invitation" else "Sends now, or on your schedule")
	else:
		lines.append(TRIGGER_LINES.get(doc["trigger_type"], doc["trigger_type"]).format(**doc))
		if doc.get("repeat_every_days"):
			lines.append(f"Repeats every {doc['repeat_every_days']} days, up to {doc.get('max_sends', 1)} times")
	if doc.get("tier_discounts"):
		lines.append(doc["tier_discounts"].replace(":", " ").replace(",", "% ·") + "%")
	elif doc.get("discount_percent"):
		lines.append(f"{doc['discount_percent']}% discount, single-use code")
	return lines


@frappe.whitelist()
def get_gallery(kind):
	"""Everything the template page shows for 'campaign' or 'automation'."""
	frappe.only_for(["System Manager", "Marketing Manager"])
	from pol_crm.marketing_hub.utils import hub_settings

	club = bool(hub_settings().club_enabled)
	cards = [
		{
			"id": t["id"],
			"name": t["name"],
			"desc": t["desc"],
			"icon": ICONS.get(t["id"], "✉️"),
			"club": bool(t.get("club")),
			"locked": bool(t.get("club")) and not club,
			"lines": preset_lines(t),
			"message": t["doc"].get("message") or t["doc"].get("message_template") or "",
			"needs_setup": t["doc"].get("campaign_type") == "Event Invitation",
			"free": t["doc"].get("trigger_type") == "AT_RISK_CALL",
		}
		for t in TEMPLATES
		if t["kind"] == kind
	]
	if kind == "campaign":
		mine = frappe.get_all(
			"Mkt Campaign",
			fields=["name", "campaign_name as title", "status", "channel", "campaign_type as detail", "sent_count", "purchases_after", "revenue_after", "scheduled_at"],
			order_by="modified desc",
			limit=30,
		)
	else:
		mine = frappe.get_all(
			"Mkt Scenario",
			fields=["name", "scenario_name as title", "enabled", "channel", "trigger_type as detail"],
			order_by="modified desc",
			limit=30,
		)
		from pol_crm.marketing_automation.engine import scenario_stats

		for row in mine:
			row.update(scenario_stats(row.name))
	return {"templates": cards, "mine": mine, "club": club}


@frappe.whitelist()
def run_template(template_id):
	"""Run a template as it is: a campaign is created and sent now, an automation is created and switched on."""
	out = create_from_template(template_id)
	if not out.get("name"):
		return out
	doc = frappe.get_doc(out["doctype"], out["name"])
	if doc.doctype == "Mkt Campaign":
		out["recipients"] = doc.send_now()["recipients"]
	else:
		doc.enabled = 1
		doc.save()
	return out


@frappe.whitelist()
def set_automation(scenario, enabled):
	"""The on/off switch on an automation card."""
	doc = frappe.get_doc("Mkt Scenario", scenario)
	doc.check_permission("write")
	doc.enabled = 1 if frappe.utils.cint(enabled) else 0
	doc.save()
	return doc.enabled


def get_template(template_id):
	for template in TEMPLATES:
		if template["id"] == template_id:
			return template
	frappe.throw(frappe._("Unknown template: {0}").format(template_id))


@frappe.whitelist()
def get_templates(kind=None):
	return [
		{"id": t["id"], "kind": t["kind"], "name": t["name"], "desc": t["desc"], "club": t.get("club", 0)}
		for t in TEMPLATES
		if not kind or t["kind"] == kind
	]


@frappe.whitelist()
def create_from_template(template_id, name=None):
	"""Create a draft campaign or a switched-off automation from a template; returns where to open it."""
	template = get_template(template_id)
	if template.get("club"):
		require_club(template["name"])

	if template["kind"] == "campaign":
		doc = frappe.new_doc("Mkt Campaign")
		doc.update({"campaign_type": "All Customers", "channel": "WhatsApp"})
		doc.update(template["doc"])
		doc.campaign_name = name or template["name"]
		doc.template_id = template_id
		if doc.campaign_type == "Event Invitation":
			# The merchant still has to say which event and when: hand back an unsaved draft.
			return {"doctype": doc.doctype, "name": None, "values": doc.as_dict(no_default_fields=True)}
	else:
		doc = frappe.new_doc("Mkt Scenario")
		doc.update({"channel": "WHATSAPP", "enabled": 0})
		doc.update(template["doc"])
		doc.scenario_name = name or template["name"]
	doc.insert()
	return {"doctype": doc.doctype, "name": doc.name}
