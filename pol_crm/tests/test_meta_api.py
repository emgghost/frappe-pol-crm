"""
Tests for what is sent to the Meta Marketing API and for the template cards.
No network: only the request bodies and the status mapping are checked.
"""

import unittest
from types import SimpleNamespace

from pol_crm.tests.frappe_mock import setup_mock_frappe

setup_mock_frappe()

from pol_crm.marketing_hub import meta_api, templates  # noqa: E402

CFG = SimpleNamespace(page_id="111", pixel_id="", instagram_id="999", currency="USD", rate=1300.0, account="act_1", token="t")


def ns(**values):
	obj = SimpleNamespace(**values)
	obj.get = lambda key, default=None: getattr(obj, key, default)
	return obj


def ad_set(**kw):
	values = dict(
		ad_set_name="Set 1", daily_budget=13000, start_date="2026-11-15", end_date="2026-11-22",
		placement_facebook=1, placement_instagram=1, audience_mode="Advantage+ Audience", governorates="",
		age_from=18, age_to=65, gender="All", destination="Messages", optimization_goal="Conversations",
	)
	values.update(kw)
	return ns(**values)


def ad(**kw):
	values = dict(
		ad_name="Ad 1", source="New creative", format="Image", media="/files/a.jpg", primary_text="Hello", hashtags="",
		headline="", cta="Send Message", website_url="", phone="", post_id="", identity="Facebook page", cards=[],
	)
	values.update(kw)
	return ns(**values)


CAMPAIGN = ns(campaign_name="Winter", objective="Engagement", special_ad_category="None")


class TestMoney(unittest.TestCase):
	def test_iqd_is_converted_to_cents_of_the_account_currency(self):
		self.assertEqual(meta_api.to_minor(13000, "USD", 1300), 1000)

	def test_zero_decimal_currency_is_not_multiplied(self):
		self.assertEqual(meta_api.to_minor(13000, "JPY", 10), 1300)

	def test_account_in_iqd_needs_no_rate(self):
		self.assertEqual(meta_api.to_minor(5000, "IQD", 0), 500000)

	def test_missing_rate_is_an_error(self):
		with self.assertRaises(meta_api.MetaError):
			meta_api.to_minor(5000, "USD", 0)


class TestCampaignAndAdSet(unittest.TestCase):
	def test_campaign(self):
		payload = meta_api.campaign_payload(CAMPAIGN)
		self.assertEqual(payload["objective"], "OUTCOME_ENGAGEMENT")
		self.assertEqual(payload["special_ad_categories"], [])
		self.assertIs(payload["is_adset_budget_sharing_enabled"], False)
		self.assertNotIn("special_ad_category_country", payload)

	def test_special_category(self):
		payload = meta_api.campaign_payload(ns(campaign_name="Flats", objective="Leads", special_ad_category="Housing"))
		self.assertEqual(payload["special_ad_categories"], ["HOUSING"])
		self.assertEqual(payload["special_ad_category_country"], ["IQ"])

	def test_ad_set(self):
		payload = meta_api.ad_set_payload(ad_set(), CAMPAIGN, CFG, "C1", ads=[ad()])
		self.assertEqual(payload["daily_budget"], 1000)
		self.assertEqual(payload["optimization_goal"], "CONVERSATIONS")
		self.assertEqual(payload["destination_type"], "MESSENGER")
		self.assertEqual(payload["promoted_object"], {"page_id": "111"})
		self.assertEqual(payload["start_time"], "2026-11-15T00:00:00+0300")
		self.assertEqual(payload["targeting"], {"geo_locations": {"countries": ["IQ"]}, "publisher_platforms": ["facebook", "instagram"]})

	def test_whatsapp_destination(self):
		payload = meta_api.ad_set_payload(ad_set(), CAMPAIGN, CFG, "C1", ads=[ad(cta="Send WhatsApp Message")])
		self.assertEqual(payload["destination_type"], "WHATSAPP")

	def test_manual_targeting(self):
		spec = meta_api.targeting(ad_set(audience_mode="Manual targeting", age_from=25, age_to=44, gender="Women", placement_facebook=0), ["1234"])
		self.assertEqual(spec["geo_locations"], {"regions": [{"key": "1234"}]})
		self.assertEqual((spec["age_min"], spec["age_max"], spec["genders"]), (25, 44, [2]))
		self.assertEqual(spec["publisher_platforms"], ["instagram"])

	def test_special_category_ignores_manual_targeting(self):
		spec = meta_api.targeting(ad_set(audience_mode="Manual targeting", gender="Men"), ["1234"], restricted=True)
		self.assertNotIn("genders", spec)
		self.assertEqual(spec["geo_locations"], {"countries": ["IQ"]})

	def test_purchases_need_a_pixel(self):
		with self.assertRaises(meta_api.MetaError):
			meta_api.ad_set_payload(ad_set(optimization_goal="Purchases", destination="Website"), CAMPAIGN, CFG, "C1")

	def test_instant_form_is_refused(self):
		with self.assertRaises(meta_api.MetaError):
			meta_api.ad_set_payload(ad_set(destination="Instant form"), CAMPAIGN, CFG, "C1")


class TestCreative(unittest.TestCase):
	def test_existing_post(self):
		self.assertEqual(meta_api.creative_payload(ad(source="Existing post", post_id="555"), ad_set(), CFG)["object_story_id"], "111_555")
		self.assertEqual(
			meta_api.creative_payload(ad(source="Existing post", post_id="https://facebook.com/x/posts/111_777/"), ad_set(), CFG)["object_story_id"],
			"111_777",
		)

	def test_website_image_ad(self):
		creative = meta_api.creative_payload(
			ad(cta="Shop Now", website_url="https://shop.example.com", headline="New", hashtags="#sale", identity="Instagram account"),
			ad_set(destination="Website"),
			CFG,
			{"/files/a.jpg": "HASH"},
		)
		story = creative["object_story_spec"]
		self.assertEqual(story["instagram_user_id"], "999")
		link = story["link_data"]
		self.assertEqual(link["link"], "https://shop.example.com")
		self.assertEqual(link["image_hash"], "HASH")
		self.assertEqual(link["message"], "Hello\n\n#sale")
		self.assertEqual(link["call_to_action"], {"type": "SHOP_NOW", "value": {"link": "https://shop.example.com"}})

	def test_messages_ad(self):
		link = meta_api.creative_payload(ad(), ad_set(), CFG, {"/files/a.jpg": "H"})["object_story_spec"]["link_data"]
		self.assertEqual(link["call_to_action"], {"type": "MESSAGE_PAGE", "value": {"app_destination": "MESSENGER"}})

	def test_call_ad(self):
		link = meta_api.creative_payload(ad(cta="Call Now", phone="0770 123 4567"), ad_set(destination="Phone call"), CFG, {"/files/a.jpg": "H"})
		self.assertEqual(link["object_story_spec"]["link_data"]["call_to_action"]["value"], {"link": "tel:+9647701234567"})

	def test_carousel(self):
		cards = [ns(media="/files/1.jpg", headline="One", link=""), ns(media="/files/2.jpg", headline="", link="https://x.example.com/2")]
		link = meta_api.creative_payload(
			ad(format="Carousel", cards=cards, website_url="https://x.example.com", cta="Learn More"),
			ad_set(destination="Website"),
			CFG,
			{"/files/1.jpg": "H1", "/files/2.jpg": "H2"},
		)["object_story_spec"]["link_data"]
		self.assertEqual(
			link["child_attachments"],
			[{"link": "https://x.example.com", "name": "One", "image_hash": "H1"}, {"link": "https://x.example.com/2", "image_hash": "H2"}],
		)
		self.assertNotIn("image_hash", link)

	def test_video_is_refused(self):
		with self.assertRaises(meta_api.MetaError):
			meta_api.creative_payload(ad(format="Video"), ad_set(), CFG)


class TestStatus(unittest.TestCase):
	def test_mapping(self):
		self.assertEqual(meta_api.local_status("ACTIVE", ["ACTIVE"]), "Active")
		self.assertEqual(meta_api.local_status("ACTIVE", ["PENDING_REVIEW", "ACTIVE"]), "In Review")
		self.assertEqual(meta_api.local_status("ACTIVE", ["DISAPPROVED", "PENDING_REVIEW"]), "Rejected")
		self.assertEqual(meta_api.local_status("PAUSED", ["CAMPAIGN_PAUSED"]), "Paused")
		self.assertEqual(meta_api.local_status("ARCHIVED", []), "Completed")


class TestTemplateCards(unittest.TestCase):
	def test_every_template_has_an_icon_and_lines(self):
		for template in templates.TEMPLATES:
			with self.subTest(template=template["id"]):
				self.assertIn(template["id"], templates.ICONS)
				lines = templates.preset_lines(template)
				self.assertTrue(lines and all(isinstance(line, str) and "{" not in line for line in lines), lines)

	def test_lines(self):
		by_id = {t["id"]: t for t in templates.TEMPLATES}
		self.assertEqual(templates.preset_lines(by_id["a-spend"]), ["Total spend reaches 500,000 IQD", "15% discount, single-use code"])
		self.assertEqual(templates.preset_lines(by_id["c-tier"])[0], "Gold, Platinum club members")
		self.assertIn("Repeats every 45 days, up to 3 times", templates.preset_lines(by_id["a-lost"]))


if __name__ == "__main__":
	unittest.main()
