"""
Meta Ads (Pro plan): rules shared by Meta Ad Campaign, Meta Ad Set and Meta Ad.
Boost and Ad are the same three-level tree with a single ad set and a single ad.
"""

import re

import frappe
from frappe.utils import add_days, cint, date_diff, flt, getdate, nowdate

from pol_crm.marketing_hub.utils import IRAQ_GOVERNORATES, require_pro, split_csv

OBJECTIVES = {
	"Awareness": {"goals": ["Reach", "Impressions"], "destinations": ["No button destination", "Website"]},
	"Traffic": {"goals": ["Link clicks", "Landing page views"], "destinations": ["Website", "Messages"]},
	"Engagement": {"goals": ["Conversations", "Post engagement"], "destinations": ["Messages", "No button destination"]},
	"Leads": {"goals": ["Leads", "Conversations"], "destinations": ["Instant form", "Messages", "Phone call"]},
	"Sales": {"goals": ["Purchases", "Conversations"], "destinations": ["Website", "Messages", "Phone call"]},
}
CTAS = {
	"Website": ["Shop Now", "Learn More", "Order Now", "Sign Up"],
	"Messages": ["Send Message", "Send WhatsApp Message"],
	"Phone call": ["Call Now"],
	"Instant form": ["Sign Up", "Get Quote", "Apply Now"],
	"No button destination": ["Learn More", "Follow"],
}
MIN_DAILY_BUDGET = 1000
MAX_DAILY_BUDGET = 200000
CPM_IQD = 1400  # cost per 1,000 impressions used for estimates
CTR = 0.012
EDITABLE = ("Draft", "Rejected", "Paused")
URL_RE = re.compile(r"^https?://\S+\.\S+")


def estimate_results(cost):
	"""Rough reach for a budget: (impressions, link clicks)."""
	impressions = max(0, round(flt(cost) / CPM_IQD * 1000))
	return impressions, round(impressions * CTR)


def ad_set_days(start_date, end_date):
	if not start_date or not end_date:
		return 0
	return max(date_diff(end_date, start_date), 0)


def ad_set_issues(ad_set, campaign):
	"""What stops this ad set from being published."""
	out = []
	label = f'"{ad_set.ad_set_name}": '
	if flt(ad_set.daily_budget) < MIN_DAILY_BUDGET:
		out.append(label + "daily budget must be at least 1,000 IQD.")
	if flt(ad_set.daily_budget) > MAX_DAILY_BUDGET:
		out.append(label + "daily budget can be at most 200,000 IQD.")
	if ad_set_days(ad_set.start_date, ad_set.end_date) < 1:
		out.append(label + "end date must be after the start date.")
	if not any(cint(ad_set.get(f)) for f in ("placement_facebook", "placement_instagram", "placement_whatsapp", "placement_wafi")):
		out.append(label + "pick at least one placement.")
	if cint(ad_set.placement_wafi) and flt(ad_set.wafi_daily_budget) < MIN_DAILY_BUDGET:
		out.append(label + "Wafi App daily budget must be at least 1,000 IQD.")

	manual = ad_set.audience_mode == "Manual targeting"
	if manual and campaign.special_ad_category and campaign.special_ad_category != "None":
		out.append(label + "a special ad category cannot use age, gender or location targeting. Use Advantage+ Audience.")
	if manual:
		governorates = split_csv(ad_set.governorates)
		if not governorates:
			out.append(label + "pick at least one location.")
		unknown = [g for g in governorates if g not in IRAQ_GOVERNORATES]
		if unknown:
			out.append(label + "unknown governorate " + ", ".join(unknown) + ".")
		if cint(ad_set.age_to) < cint(ad_set.age_from):
			out.append(label + "age range is reversed.")

	rules = OBJECTIVES.get(campaign.objective, {})
	if ad_set.destination and ad_set.destination not in rules.get("destinations", []):
		out.append(label + f"destination {ad_set.destination} does not fit the {campaign.objective} objective.")
	if ad_set.optimization_goal and ad_set.optimization_goal not in rules.get("goals", []):
		out.append(label + f"optimizing for {ad_set.optimization_goal} does not fit the {campaign.objective} objective.")
	return out


def ad_issues(ad, ad_set):
	"""What stops this ad from being published."""
	out = []
	label = f'"{ad.ad_name}": '
	if ad.source == "Existing post":
		if not ad.post_id:
			out.append(label + "choose a post.")
	else:
		cards = len(ad.get("cards") or [])
		if ad.format == "Carousel" and cards < 2:
			out.append(label + "a carousel needs at least 2 cards.")
		elif ad.format == "Carousel" and cards > 10:
			out.append(label + "a carousel can have at most 10 cards.")
		elif ad.format != "Carousel" and not ad.media:
			out.append(label + ("upload a video." if ad.format == "Video" else "upload an image."))
		if not (ad.primary_text or "").strip():
			out.append(label + "write the primary text.")
	destination = ad_set.destination if ad_set else None
	if destination == "Website" and not URL_RE.match(ad.website_url or ""):
		out.append(label + "add a valid website URL.")
	if destination == "Phone call" and len(re.sub(r"\D", "", ad.phone or "")) < 10:
		out.append(label + "add a phone number.")
	return out


def campaign_issues(campaign_name):
	campaign = frappe.get_doc("Meta Ad Campaign", campaign_name)
	out = []
	ad_sets = frappe.get_all("Meta Ad Set", filters={"campaign": campaign_name}, pluck="name", order_by="creation")
	if not ad_sets:
		out.append("Add at least one ad set.")
	for set_name in ad_sets:
		ad_set = frappe.get_doc("Meta Ad Set", set_name)
		out.extend(ad_set_issues(ad_set, campaign))
		ads = frappe.get_all("Meta Ad", filters={"ad_set": set_name}, pluck="name", order_by="creation")
		if not ads:
			out.append(f'"{ad_set.ad_set_name}": add at least one ad.')
		for ad_name in ads:
			out.extend(ad_issues(frappe.get_doc("Meta Ad", ad_name), ad_set))
	return [issue[0].upper() + issue[1:] for issue in out]


def recompute_campaign_totals(campaign_name):
	if not campaign_name or not frappe.db.exists("Meta Ad Campaign", campaign_name):
		return
	rows = frappe.get_all(
		"Meta Ad Set",
		filters={"campaign": campaign_name},
		fields=["daily_budget", "days", "placement_wafi", "wafi_daily_budget"],
	)
	total = sum(flt(r.daily_budget) * cint(r.days) for r in rows)
	wafi = sum(flt(r.wafi_daily_budget) * cint(r.days) for r in rows if cint(r.placement_wafi))
	impressions, clicks = estimate_results(total)
	frappe.db.set_value(
		"Meta Ad Campaign",
		campaign_name,
		{"total_budget": total, "wafi_budget": wafi, "est_impressions": impressions, "est_clicks": clicks},
		update_modified=False,
	)


def set_tree_status(campaign_name, status):
	"""A campaign's ad sets and ads follow its delivery status."""
	for doctype in ("Meta Ad Set", "Meta Ad"):
		for name in frappe.get_all(doctype, filters={"campaign": campaign_name}, pluck="name"):
			frappe.db.set_value(doctype, name, "status", status, update_modified=False)


def assert_editable(doc, campaign_name):
	"""Ad sets and ads can only change while their campaign is a draft, rejected or paused."""
	if doc.flags.ignore_lock or not campaign_name:
		return
	status = frappe.db.get_value("Meta Ad Campaign", campaign_name, "status")
	if status and status not in EDITABLE:
		frappe.throw(frappe._("This campaign is {0}. Pause it before changing its ad sets or ads.").format(status))


def duplicate_ad(ad_name, ad_set=None, suffix=" (copy)"):
	copy = frappe.copy_doc(frappe.get_doc("Meta Ad", ad_name))
	copy.ad_name += suffix
	copy.status = "Draft"
	if ad_set:
		copy.ad_set = ad_set
		copy.campaign = frappe.db.get_value("Meta Ad Set", ad_set, "campaign")
	copy.insert()
	return copy.name


def duplicate_ad_set(set_name, campaign=None, suffix=" (copy)"):
	copy = frappe.copy_doc(frappe.get_doc("Meta Ad Set", set_name))
	copy.ad_set_name += suffix
	copy.status = "Draft"
	if campaign:
		copy.campaign = campaign
	copy.insert()
	for ad_name in frappe.get_all("Meta Ad", filters={"ad_set": set_name}, pluck="name", order_by="creation"):
		duplicate_ad(ad_name, copy.name, suffix="" if campaign else suffix)
	return copy.name


def duplicate_campaign(campaign_name):
	copy = frappe.copy_doc(frappe.get_doc("Meta Ad Campaign", campaign_name))
	copy.campaign_name += " (copy)"
	copy.status = "Draft"
	copy.insert()
	for set_name in frappe.get_all("Meta Ad Set", filters={"campaign": campaign_name}, pluck="name", order_by="creation"):
		duplicate_ad_set(set_name, copy.name, suffix="")
	recompute_campaign_totals(copy.name)
	return copy.name


@frappe.whitelist()
def quick_create(kind, campaign_name, objective="Engagement", daily_budget=5000, days=7, primary_text=None, post_platform=None, post_id=None, media=None):
	"""Boost a Post / Create an Ad: one call builds the campaign, its ad set and its ad as drafts."""
	require_pro()
	if kind not in ("Boost", "Ad"):
		frappe.throw(frappe._("Quick create is for Boost or Ad."))
	if not frappe.has_permission("Meta Ad Campaign", "create"):
		frappe.throw(frappe._("Not permitted"), frappe.PermissionError)

	rules = OBJECTIVES.get(objective) or OBJECTIVES["Engagement"]
	campaign = frappe.get_doc(
		{"doctype": "Meta Ad Campaign", "campaign_name": campaign_name, "kind": kind, "objective": objective}
	).insert()
	ad_set = frappe.get_doc(
		{
			"doctype": "Meta Ad Set",
			"campaign": campaign.name,
			"ad_set_name": campaign_name,
			"destination": rules["destinations"][0],
			"daily_budget": flt(daily_budget) or 5000,
			"start_date": nowdate(),
			"end_date": add_days(nowdate(), cint(days) or 7),
		}
	).insert()
	ad = {
		"doctype": "Meta Ad",
		"ad_set": ad_set.name,
		"campaign": campaign.name,
		"ad_name": campaign_name,
		"cta": CTAS[rules["destinations"][0]][0],
		"primary_text": primary_text,
	}
	if kind == "Boost":
		ad.update(source="Existing post", post_platform=post_platform or "Instagram", post_id=post_id)
	else:
		ad.update(source="New creative", format="Image", media=media)
	frappe.get_doc(ad).insert()
	return campaign.name


def create_draft_from_message(name, text, media=None):
	"""After a customer campaign is sent: the same message as a draft ad for new people."""
	return quick_create("Ad", f"{name} - Meta ad", primary_text=text, media=media)


def complete_finished_campaigns():
	"""Daily: an active campaign whose ad sets have all ended is completed."""
	if not frappe.db.exists("DocType", "Meta Ad Campaign"):
		return
	today = getdate(nowdate())
	for name in frappe.get_all("Meta Ad Campaign", filters={"status": "Active"}, pluck="name"):
		ends = frappe.get_all("Meta Ad Set", filters={"campaign": name}, pluck="end_date")
		if ends and all(end and getdate(end) < today for end in ends):
			frappe.db.set_value("Meta Ad Campaign", name, "status", "Completed")
			set_tree_status(name, "Completed")
