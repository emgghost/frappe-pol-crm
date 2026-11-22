"""
Meta Marketing API: sends a Meta Ad Campaign (campaign -> ad sets -> ads) to the
merchant's ad account, pauses and resumes it, and reads back status and results.

Budgets are typed in IQD. Meta bills in the ad account's currency, so amounts are
converted with the rate in Marketing Hub Settings before they are sent.
"""

import json
import re

import frappe
import requests
from frappe.utils import cint, flt, getdate

API_VERSION = "v25.0"
GRAPH = f"https://graph.facebook.com/{API_VERSION}"
TIMEOUT = 30
BAGHDAD_OFFSET = "+0300"
# Currencies Meta counts in whole units; every other one is sent in cents.
ZERO_DECIMAL = {"CLP", "COP", "CRC", "HUF", "ISK", "IDR", "JPY", "KRW", "PYG", "TWD", "VND"}

OBJECTIVES = {
	"Awareness": "OUTCOME_AWARENESS",
	"Traffic": "OUTCOME_TRAFFIC",
	"Engagement": "OUTCOME_ENGAGEMENT",
	"Leads": "OUTCOME_LEADS",
	"Sales": "OUTCOME_SALES",
}
SPECIAL_CATEGORIES = {
	"Credit": "FINANCIAL_PRODUCTS_SERVICES",
	"Employment": "EMPLOYMENT",
	"Housing": "HOUSING",
	"Social Issues": "ISSUES_ELECTIONS_POLITICS",
}
GOALS = {
	"Reach": "REACH",
	"Impressions": "IMPRESSIONS",
	"Link clicks": "LINK_CLICKS",
	"Landing page views": "LANDING_PAGE_VIEWS",
	"Conversations": "CONVERSATIONS",
	"Post engagement": "POST_ENGAGEMENT",
	"Leads": "LEAD_GENERATION",
	"Purchases": "OFFSITE_CONVERSIONS",
}
CTAS = {
	"Shop Now": "SHOP_NOW",
	"Learn More": "LEARN_MORE",
	"Order Now": "ORDER_NOW",
	"Sign Up": "SIGN_UP",
	"Send Message": "MESSAGE_PAGE",
	"Send WhatsApp Message": "WHATSAPP_MESSAGE",
	"Call Now": "CALL_NOW",
	"Get Quote": "GET_QUOTE",
	"Apply Now": "APPLY_NOW",
	"Follow": "LIKE_PAGE",
}
GENDERS = {"Men": [1], "Women": [2]}
# What Meta reports -> the status shown here.
REVIEWING = {"PENDING_REVIEW", "IN_PROCESS", "PREAPPROVED", "PENDING_BILLING_INFO"}
CAMPAIGN_STATUS = {"ACTIVE": "Active", "PAUSED": "Paused", "ARCHIVED": "Completed", "DELETED": "Completed", "IN_PROCESS": "In Review", "WITH_ISSUES": "In Review"}


class MetaError(Exception):
	pass


# ---------------------------------------------------------------- settings and HTTP
def get_config():
	"""Connection details, or None when Meta Ads is not set up."""
	if not frappe.db.exists("DocType", "Marketing Hub Settings"):
		return None
	settings = frappe.get_single("Marketing Hub Settings")
	token = settings.get_password("meta_access_token", raise_exception=False)
	account = re.sub(r"^act_", "", (settings.meta_ad_account_id or "").strip())
	if not (token and account and settings.meta_page_id):
		return None
	return frappe._dict(
		token=token,
		account=f"act_{account}",
		page_id=settings.meta_page_id.strip(),
		pixel_id=(settings.meta_pixel_id or "").strip(),
		instagram_id=(settings.instagram_account_id or "").strip(),
		currency=(settings.meta_account_currency or "USD").strip().upper(),
		rate=flt(settings.meta_exchange_rate),
	)


def is_configured():
	return get_config() is not None


def _call(method, path, cfg, data=None, files=None):
	"""One Graph API request. Nested values are sent as JSON, the way the API expects."""
	params = {"access_token": cfg.token}
	body = {k: json.dumps(v) if isinstance(v, (dict, list)) else v for k, v in (data or {}).items() if v is not None}
	url = f"{GRAPH}/{path.lstrip('/')}"
	try:
		if method == "GET":
			response = requests.get(url, params={**params, **body}, timeout=TIMEOUT)
		else:
			response = requests.post(url, params=params, data=body, files=files, timeout=TIMEOUT)
		result = response.json()
	except Exception as e:
		raise MetaError(f"Could not reach Meta: {e}")
	if isinstance(result, dict) and result.get("error"):
		error = result["error"]
		raise MetaError(error.get("error_user_msg") or error.get("message") or "Meta rejected the request.")
	return result


# ---------------------------------------------------------------- building requests (pure)
def to_minor(amount_iqd, currency, rate):
	"""An IQD amount in the smallest unit of the ad account's currency."""
	currency = (currency or "USD").upper()
	amount = flt(amount_iqd)
	if currency != "IQD":
		if flt(rate) <= 0:
			raise MetaError(
				f"The ad account is in {currency}. Set 'IQD per 1 Unit of the Account Currency' in Marketing Hub Settings."
			)
		amount = amount / flt(rate)
	return int(round(amount if currency in ZERO_DECIMAL else amount * 100))


def campaign_payload(campaign, status="ACTIVE"):
	category = SPECIAL_CATEGORIES.get(campaign.special_ad_category)
	payload = {
		"name": campaign.campaign_name,
		"objective": OBJECTIVES.get(campaign.objective, "OUTCOME_ENGAGEMENT"),
		"status": status,
		"special_ad_categories": [category] if category else [],
		# Budgets live on the ad sets; Meta requires saying so explicitly.
		"is_adset_budget_sharing_enabled": False,
	}
	if category:
		payload["special_ad_category_country"] = ["IQ"]
	return payload


def targeting(ad_set, region_keys=None, restricted=False):
	"""restricted: a special ad category, where age, gender and location cannot be narrowed."""
	spec = {"geo_locations": {"countries": ["IQ"]}}
	platforms = [p for p, field in (("facebook", "placement_facebook"), ("instagram", "placement_instagram")) if cint(ad_set.get(field))]
	if platforms:
		spec["publisher_platforms"] = platforms
	if restricted or ad_set.audience_mode != "Manual targeting":
		return spec
	if region_keys:
		spec["geo_locations"] = {"regions": [{"key": key} for key in region_keys]}
	spec["age_min"] = max(cint(ad_set.age_from) or 18, 18)
	spec["age_max"] = min(cint(ad_set.age_to) or 65, 65)
	if ad_set.gender in GENDERS:
		spec["genders"] = GENDERS[ad_set.gender]
	return spec


def destination_type(ad_set, ads=()):
	if ad_set.destination == "Website":
		return "WEBSITE"
	if ad_set.destination == "Phone call":
		return "PHONE_CALL"
	if ad_set.destination == "Messages":
		return "WHATSAPP" if any(ad.cta == "Send WhatsApp Message" for ad in ads) else "MESSENGER"
	return None


def ad_set_payload(ad_set, campaign, cfg, meta_campaign_id, region_keys=None, ads=(), status="ACTIVE"):
	if ad_set.destination == "Instant form":
		raise MetaError(f'"{ad_set.ad_set_name}": instant forms are not sent to Meta from here yet. Use Messages or Phone call.')
	goal = GOALS.get(ad_set.optimization_goal, "REACH")
	payload = {
		"name": ad_set.ad_set_name,
		"campaign_id": meta_campaign_id,
		"daily_budget": to_minor(ad_set.daily_budget, cfg.currency, cfg.rate),
		"billing_event": "IMPRESSIONS",
		"optimization_goal": goal,
		"bid_strategy": "LOWEST_COST_WITHOUT_CAP",
		"start_time": f"{getdate(ad_set.start_date)}T00:00:00{BAGHDAD_OFFSET}",
		"end_time": f"{getdate(ad_set.end_date)}T23:59:00{BAGHDAD_OFFSET}",
		"targeting": targeting(ad_set, region_keys, restricted=campaign.special_ad_category in SPECIAL_CATEGORIES),
		"status": status,
	}
	destination = destination_type(ad_set, ads)
	if destination:
		payload["destination_type"] = destination
	if goal == "OFFSITE_CONVERSIONS":
		if not cfg.pixel_id:
			raise MetaError(f'"{ad_set.ad_set_name}": optimizing for Purchases needs the Pixel ID in Marketing Hub Settings.')
		payload["promoted_object"] = {"pixel_id": cfg.pixel_id, "custom_event_type": "PURCHASE"}
	elif goal in ("CONVERSATIONS", "POST_ENGAGEMENT", "LEAD_GENERATION"):
		payload["promoted_object"] = {"page_id": cfg.page_id}
	return payload


def call_to_action(ad, ad_set, cfg):
	kind = CTAS.get(ad.cta, "LEARN_MORE")
	destination = ad_set.destination
	if destination == "Website":
		return {"type": kind, "value": {"link": ad.website_url}}, ad.website_url
	if destination == "Phone call":
		from pol_crm.messaging.phone_utils import normalize_mobile

		phone = normalize_mobile(ad.phone)[0] or "+" + re.sub(r"\D", "", ad.phone or "")
		return {"type": "CALL_NOW", "value": {"link": f"tel:{phone}"}}, f"https://www.facebook.com/{cfg.page_id}"
	if destination == "Messages":
		app = "WHATSAPP" if ad.cta == "Send WhatsApp Message" else "MESSENGER"
		return {"type": kind, "value": {"app_destination": app}}, "https://fb.com/messenger_doc/"
	return {"type": kind, "value": {"page": cfg.page_id}} if kind == "LIKE_PAGE" else None, f"https://www.facebook.com/{cfg.page_id}"


def creative_payload(ad, ad_set, cfg, image_hashes=None):
	"""image_hashes: {file_url: hash} for the uploaded images of this ad."""
	image_hashes = image_hashes or {}
	if ad.source == "Existing post":
		post_id = str(ad.post_id).strip().rstrip("/").split("/")[-1]
		story = post_id if "_" in post_id else f"{cfg.page_id}_{post_id}"
		return {"name": ad.ad_name, "object_story_id": story}

	if ad.format == "Video":
		raise MetaError(f'"{ad.ad_name}": video ads are not sent to Meta from here yet. Use an image or a carousel, or boost an existing video post.')

	action, link = call_to_action(ad, ad_set, cfg)
	text = (ad.primary_text or "").strip()
	if ad.hashtags:
		text = f"{text}\n\n{ad.hashtags.strip()}"
	link_data = {"message": text, "link": link}
	if ad.headline:
		link_data["name"] = ad.headline
	if action:
		link_data["call_to_action"] = action

	if ad.format == "Carousel":
		link_data["child_attachments"] = [
			{k: v for k, v in {"link": card.link or link, "name": card.headline, "image_hash": image_hashes.get(card.media)}.items() if v}
			for card in ad.cards
		]
	else:
		link_data["image_hash"] = image_hashes.get(ad.media)

	story = {"page_id": cfg.page_id, "link_data": link_data}
	if ad.identity == "Instagram account" and cfg.instagram_id:
		story["instagram_user_id"] = cfg.instagram_id
	return {"name": ad.ad_name, "object_story_spec": story}


def local_status(campaign_status, ad_statuses):
	"""Meta's campaign and ad statuses -> the status shown here."""
	ad_statuses = set(ad_statuses or [])
	if "DISAPPROVED" in ad_statuses:
		return "Rejected"
	if ad_statuses & REVIEWING:
		return "In Review"
	return CAMPAIGN_STATUS.get(campaign_status, "In Review")


# ---------------------------------------------------------------- talking to Meta
def region_keys_for(governorates, cfg):
	"""Meta's region keys for Iraqi governorates (looked up once, then cached)."""
	keys = []
	for name in governorates:
		cache_key = f"pol_crm:meta_region:{name}"
		key = frappe.cache.get_value(cache_key)
		if not key:
			found = _call("GET", "search", cfg, {"type": "adgeolocation", "location_types": ["region"], "country_code": "IQ", "q": name})
			rows = found.get("data") or []
			if not rows:
				raise MetaError(f"Meta does not know the governorate {name}.")
			key = rows[0]["key"]
			frappe.cache.set_value(cache_key, key)
		keys.append(key)
	return keys


def upload_image(file_url, cfg):
	"""Upload one attached image to the ad account; returns its hash."""
	if not file_url:
		raise MetaError("An ad is missing its image.")
	file_doc = frappe.get_doc("File", {"file_url": file_url})
	result = _call("POST", f"{cfg.account}/adimages", cfg, files={"filename": (file_doc.file_name, file_doc.get_content())})
	images = result.get("images") or {}
	if not images:
		raise MetaError(f"Meta did not accept the image {file_doc.file_name}.")
	return next(iter(images.values()))["hash"]


def push_campaign(campaign_name):
	"""Create the campaign, its ad sets and its ads on Meta. Safe to call again after a
	failure: whatever was already created keeps its Meta ID and is not created twice."""
	cfg = get_config()
	if not cfg:
		raise MetaError("Meta Ads is not connected. Fill in the Meta Ads section of Marketing Hub Settings.")
	from pol_crm.marketing_hub.utils import split_csv

	def remember(doc, fieldname, meta_id):
		# Committed at once: if a later step fails, the next attempt must not create this again.
		doc.db_set(fieldname, meta_id, update_modified=False)
		frappe.db.commit()

	campaign = frappe.get_doc("Meta Ad Campaign", campaign_name)
	if not campaign.meta_campaign_id:
		created = _call("POST", f"{cfg.account}/campaigns", cfg, campaign_payload(campaign))
		remember(campaign, "meta_campaign_id", created["id"])

	for set_name in frappe.get_all("Meta Ad Set", filters={"campaign": campaign_name}, pluck="name", order_by="creation"):
		ad_set = frappe.get_doc("Meta Ad Set", set_name)
		ads = [frappe.get_doc("Meta Ad", n) for n in frappe.get_all("Meta Ad", filters={"ad_set": set_name}, pluck="name", order_by="creation")]
		if not ad_set.meta_adset_id:
			regions = None
			if ad_set.audience_mode == "Manual targeting" and campaign.special_ad_category not in SPECIAL_CATEGORIES:
				regions = region_keys_for(split_csv(ad_set.governorates), cfg)
			created = _call("POST", f"{cfg.account}/adsets", cfg, ad_set_payload(ad_set, campaign, cfg, campaign.meta_campaign_id, regions, ads))
			remember(ad_set, "meta_adset_id", created["id"])

		for ad in ads:
			if not ad.meta_creative_id:
				hashes = {}
				if ad.source != "Existing post" and ad.format != "Video":
					for url in [card.media for card in ad.cards] if ad.format == "Carousel" else [ad.media]:
						hashes[url] = upload_image(url, cfg)
				created = _call("POST", f"{cfg.account}/adcreatives", cfg, creative_payload(ad, ad_set, cfg, hashes))
				remember(ad, "meta_creative_id", created["id"])
			if not ad.meta_ad_id:
				created = _call(
					"POST",
					f"{cfg.account}/ads",
					cfg,
					{"name": ad.ad_name, "adset_id": ad_set.meta_adset_id, "creative": {"creative_id": ad.meta_creative_id}, "status": "ACTIVE"},
				)
				remember(ad, "meta_ad_id", created["id"])
	return campaign.meta_campaign_id


def set_delivery(campaign_name, active):
	"""Pause or resume the campaign on Meta. Returns False when it was never sent there."""
	meta_id = frappe.db.get_value("Meta Ad Campaign", campaign_name, "meta_campaign_id")
	cfg = get_config()
	if not (meta_id and cfg):
		return False
	_call("POST", meta_id, cfg, {"status": "ACTIVE" if active else "PAUSED"})
	return True


def sync_campaign(campaign_name, cfg=None):
	"""Read status and results of one campaign back from Meta."""
	cfg = cfg or get_config()
	campaign = frappe.get_doc("Meta Ad Campaign", campaign_name)
	if not (cfg and campaign.meta_campaign_id):
		return None
	from pol_crm.marketing_hub import meta

	info = _call("GET", campaign.meta_campaign_id, cfg, {"fields": "effective_status"})
	ads = _call("GET", f"{campaign.meta_campaign_id}/ads", cfg, {"fields": "effective_status,ad_review_feedback", "limit": 100}).get("data") or []
	status = local_status(info.get("effective_status"), [a.get("effective_status") for a in ads])
	values = {"status": status}
	if status == "Rejected":
		feedback = next((a.get("ad_review_feedback") for a in ads if a.get("effective_status") == "DISAPPROVED"), None)
		values["rejection_reason"] = json.dumps(feedback, ensure_ascii=False)[:500] if feedback else "Disapproved by Meta."

	insights = _call("GET", f"{campaign.meta_campaign_id}/insights", cfg, {"fields": "spend,impressions,clicks", "date_preset": "maximum"}).get("data") or []
	if insights:
		row = insights[0]
		spend = flt(row.get("spend"))
		values.update(
			spend=spend * cfg.rate if cfg.currency != "IQD" and cfg.rate else spend,
			impressions=cint(row.get("impressions")),
			clicks=cint(row.get("clicks")),
		)
	previous = campaign.status
	campaign.db_set(values, update_modified=False)
	if status != previous:
		meta.set_tree_status(campaign_name, status)
	return values


def sync_all():
	"""Hourly: refresh every campaign that is live or waiting for Meta's review."""
	cfg = get_config()
	if not cfg:
		return
	names = frappe.get_all(
		"Meta Ad Campaign",
		filters={"meta_campaign_id": ["is", "set"], "status": ["in", ["In Review", "Active", "Paused"]]},
		pluck="name",
	)
	for name in names:
		try:
			sync_campaign(name, cfg)
			frappe.db.commit()
		except Exception:
			frappe.db.rollback()
			frappe.log_error(title=f"Meta Ads sync failed for {name}")


@frappe.whitelist()
def test_connection():
	"""Settings button: check the token, the ad account and the page, and store the account's currency."""
	frappe.only_for(["System Manager", "Marketing Manager"])
	cfg = get_config()
	if not cfg:
		frappe.throw(frappe._("Fill in the Ad Account ID, the Facebook Page ID and the Access Token first, then save."))
	try:
		account = _call("GET", cfg.account, cfg, {"fields": "name,currency,account_status"})
		page = _call("GET", cfg.page_id, cfg, {"fields": "name"})
	except MetaError as e:
		frappe.throw(str(e), title=frappe._("Meta did not accept the connection"))
	if account.get("currency"):
		frappe.db.set_single_value("Marketing Hub Settings", "meta_account_currency", account["currency"])
	return {"account": account.get("name"), "currency": account.get("currency"), "account_status": account.get("account_status"), "page": page.get("name")}


@frappe.whitelist()
def sync_now(campaign):
	frappe.has_permission("Meta Ad Campaign", "write", campaign, throw=True)
	try:
		return sync_campaign(campaign)
	except MetaError as e:
		frappe.throw(str(e), title=frappe._("Meta"))
