import frappe
from frappe.model.document import Document
from frappe.utils import cint, flt

# Reasons that rely on club tiers or points.
CLUB_TRIGGERS = ("BIRTHDAY_BY_TIER", "POINTS_USABLE", "POINTS_EXPIRY", "AT_RISK_CALL")


class MktScenario(Document):
    def validate(self):
        from pol_crm.marketing_hub.utils import parse_tier_discounts, require_club, split_csv

        trigger = self.trigger_type
        if trigger in CLUB_TRIGGERS or split_csv(self.get("club_tiers")) or self.get("tier_discounts"):
            require_club(frappe._("This automation"))

        if trigger == "SPEND_THRESHOLD" and flt(self.get("spend_threshold")) <= 0:
            frappe.throw(frappe._("Set the total spend that triggers this automation."))
        if trigger == "PURCHASE_COUNT" and cint(self.get("purchase_count_target")) <= 0:
            frappe.throw(frappe._("Set the number of purchases that triggers this automation."))
        if trigger == "BIRTHDAY_BY_TIER" and not parse_tier_discounts(self.get("tier_discounts")):
            frappe.throw(frappe._("Set the discount per club tier, e.g. Bronze:5, Silver:10."))
        if trigger == "AT_RISK_CALL" and not (cint(self.get("call_reminder")) or cint(self.get("send_message"))):
            frappe.throw(frappe._("Choose a call reminder, a message, or both."))

        needs_message = trigger != "AT_RISK_CALL" or cint(self.get("send_message"))
        if needs_message and not (self.message_template or "").strip():
            frappe.throw(frappe._("Write the message."))
        if cint(self.get("followup_enabled")) and not (self.get("followup_message") or "").strip():
            frappe.throw(frappe._("Write the follow-up message."))
