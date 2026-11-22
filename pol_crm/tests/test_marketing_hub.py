"""
Tests for the Marketing Hub rules that need no site: Iraqi phone numbers, audience
filters, message placeholders, wallet split, Wafi prices and Meta ad checks.
"""

import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

from pol_crm.tests.frappe_mock import setup_mock_frappe

setup_mock_frappe()

from pol_crm.marketing_hub import meta, wafi, wallet  # noqa: E402
from pol_crm.marketing_hub.audience import build_customer_filters, segments_for_activity  # noqa: E402
from pol_crm.marketing_hub.utils import parse_tier_discounts, render_message, split_csv  # noqa: E402
from pol_crm.messaging import policy  # noqa: E402
from pol_crm.messaging.phone_utils import normalize_iraqi_mobile, normalize_mobile  # noqa: E402


class TestIraqiPhone(unittest.TestCase):
	def test_formats(self):
		for raw in ("07701234567", "+964 770 123 4567", "009647701234567", "9647701234567", "7701234567", "٠٧٧٠١٢٣٤٥٦٧"):
			with self.subTest(raw=raw):
				self.assertEqual(normalize_iraqi_mobile(raw), ("+9647701234567", "07701234567", True))

	def test_invalid(self):
		for raw in (None, "", "12345", "06701234567", "077012345", "+96477012345678"):
			with self.subTest(raw=raw):
				self.assertFalse(normalize_iraqi_mobile(raw)[2])

	def test_normalize_mobile_keeps_iranian_numbers_working(self):
		self.assertEqual(normalize_mobile("07701234567")[0], "+9647701234567")
		self.assertEqual(normalize_mobile("09121234567")[0], "+989121234567")
		self.assertFalse(normalize_mobile("abc")[2])


class TestAudienceFilters(unittest.TestCase):
	def test_all_customers_filters(self):
		filters = build_customer_filters(
			{"last_purchase": "In the last 30 days", "purchase_count": "5+ times", "min_spend": 100000, "governorates": "Baghdad, Basra"},
			today="2026-11-14",
		)
		self.assertIn(["custom_last_purchase_date", ">=", "2026-10-15"], filters)
		self.assertIn(["custom_paid_invoices_count", ">=", 5], filters)
		self.assertIn(["custom_total_spent", ">=", 100000.0], filters)
		self.assertIn(["custom_governorate", "in", ["Baghdad", "Basra"]], filters)
		self.assertIn(["custom_mkt_opted_out_all", "=", 0], filters)

	def test_not_bought_for_45_days(self):
		filters = build_customer_filters({"last_purchase": "Not in 45+ days"}, today="2026-11-14")
		self.assertIn(["custom_last_purchase_date", "<=", "2026-09-30"], filters)

	def test_any_time_adds_no_date_filter(self):
		filters = build_customer_filters({"last_purchase": "Any time", "purchase_count": "Any"}, today="2026-11-14")
		self.assertEqual(filters, [["disabled", "=", 0], ["custom_mkt_opted_out_all", "=", 0]])

	def test_segment_and_tier(self):
		filters = build_customer_filters({"activity_segments": ["Very Active", "New Lead"], "club_tiers": "Gold, Platinum"})
		self.assertIn(["custom_rfm_segment", "in", ["CHAMPIONS", "LOYAL", "NEW_CUSTOMERS"]], filters)
		self.assertIn(["loyalty_program_tier", "in", ["Gold", "Platinum"]], filters)

	def test_unknown_activity_is_ignored(self):
		self.assertEqual(segments_for_activity("Nonsense"), [])


class TestMessageHelpers(unittest.TestCase):
	def test_placeholders(self):
		text = render_message("Hi {name}, {discount} off: {code}", {"name": "Ali", "discount": "10%", "code": "MKT-ABC"})
		self.assertEqual(text, "Hi Ali, 10% off: MKT-ABC")

	def test_unknown_placeholder_is_left_alone(self):
		self.assertEqual(render_message("Join {event} at [place]", {"name": "Ali"}), "Join {event} at [place]")

	def test_empty_value_becomes_blank(self):
		self.assertEqual(render_message("Code: {code}", {"code": ""}), "Code: ")

	def test_jinja_still_works(self):
		self.assertEqual(render_message("Hi {{ customer_name }} / {name}", {"customer_name": "Sara", "name": "Sara"}), "Hi Sara / Sara")

	def test_split_csv(self):
		self.assertEqual(split_csv(" Gold, Platinum ,\nSilver,"), ["Gold", "Platinum", "Silver"])
		self.assertEqual(split_csv(None), [])

	def test_tier_discounts(self):
		self.assertEqual(parse_tier_discounts("Bronze:5, Silver: 10%, Bad, Gold:0"), {"Bronze": 5.0, "Silver": 10.0})


class TestWallet(unittest.TestCase):
	def test_gift_is_spent_first(self):
		self.assertEqual(wallet.split_charge(9360, 50000), (9360, 0))
		self.assertEqual(wallet.split_charge(30000, 12000), (12000, 18000))
		self.assertEqual(wallet.split_charge(500, 0), (0, 500))

	def test_charge_writes_negative_amounts_from_both_buckets(self):
		with patch.object(wallet, "get_balance", return_value={"gift": 1000, "paid": 5000, "total": 6000}), patch.object(
			wallet, "_add", return_value="WTX-00001"
		) as add:
			self.assertEqual(wallet.charge(2500, "Wafi Ad: test", "Wafi Ad", "WAD-00001"), "WTX-00001")
			add.assert_called_once_with("Charge", -1000, -1500, "Wafi Ad: test", "Wafi Ad", "WAD-00001")

	def test_free_actions_do_not_touch_the_wallet(self):
		with patch.object(wallet, "_add") as add:
			self.assertIsNone(wallet.charge(0, "free offer"))
			add.assert_not_called()

	def test_can_pay(self):
		with patch.object(wallet, "get_balance", return_value={"gift": 100, "paid": 0, "total": 100}):
			self.assertTrue(wallet.can_pay(100))
			self.assertFalse(wallet.can_pay(101))


class TestWafiPrices(unittest.TestCase):
	def test_banner_price_is_per_five_days(self):
		self.assertEqual(wafi.ad_placement_price("Homepage Banner", 5), 35000)
		self.assertEqual(wafi.ad_placement_price("Search Results Banner", 7), 21000)

	def test_all_banners_get_twenty_percent_off(self):
		rows = [(name, 5) for name in wafi.AD_PLACEMENT_PRICES]
		self.assertEqual(wafi.ad_totals(rows), (90000, 18000, 72000))
		self.assertEqual(wafi.ad_totals(rows[:3]), (75000, 0, 75000))

	def test_offer_prices(self):
		self.assertEqual(wafi.offer_price(wafi.OFFER_FREE, size="Square", days=10), 0)
		self.assertEqual(wafi.offer_price(wafi.OFFER_FREE, size="Banner", days=10, is_extra=True), 6000)
		self.assertEqual(wafi.offer_price(wafi.OFFER_FREE, size="Large Tile", days=7, is_extra=True), 4000)
		self.assertEqual(wafi.offer_price(wafi.OFFER_TOP, tile="Large Tile"), 15000)
		self.assertEqual(wafi.offer_price(wafi.OFFER_TOP, tile="Square 3"), 5000)

	def test_promote_price_rounds_up_to_weeks(self):
		self.assertEqual(wafi.promote_price(["top_search", "map_pin"], 7), (1, 55000, 55000))
		self.assertEqual(wafi.promote_price(["wider_radius"], 8), (2, 10000, 20000))
		self.assertEqual(wafi.promote_price([], 14), (2, 0, 0))

	def test_inclusive_days(self):
		self.assertEqual(wafi.inclusive_days("2026-11-01", "2026-11-05"), 5)
		self.assertEqual(wafi.inclusive_days("2026-11-05", "2026-11-01"), 0)

	def test_ranges_overlap(self):
		self.assertTrue(wafi.ranges_overlap("2026-11-01", "2026-11-05", "2026-11-05", "2026-11-09"))
		self.assertFalse(wafi.ranges_overlap("2026-11-01", "2026-11-05", "2026-11-06", "2026-11-09"))


def _ad_set(**kw):
	values = dict(
		ad_set_name="Set 1", daily_budget=5000, start_date="2026-11-14", end_date="2026-11-21",
		placement_facebook=1, placement_instagram=1, placement_whatsapp=0, placement_wafi=0, wafi_daily_budget=0,
		audience_mode="Advantage+ Audience", governorates="", age_from=18, age_to=65,
		destination="Messages", optimization_goal="Conversations",
	)
	values.update(kw)
	ns = SimpleNamespace(**values)
	ns.get = lambda key, default=None: getattr(ns, key, default)
	return ns


def _ad(**kw):
	values = dict(ad_name="Ad 1", source="New creative", format="Image", media="/files/a.jpg", primary_text="Hello", post_id="", website_url="", phone="", cards=[])
	values.update(kw)
	ns = SimpleNamespace(**values)
	ns.get = lambda key, default=None: getattr(ns, key, default)
	return ns


CAMPAIGN = SimpleNamespace(objective="Engagement", special_ad_category="None")


class TestMetaRules(unittest.TestCase):
	def test_estimate(self):
		self.assertEqual(meta.estimate_results(35000), (25000, 300))
		self.assertEqual(meta.estimate_results(0), (0, 0))

	def test_valid_ad_set_has_no_issues(self):
		self.assertEqual(meta.ad_set_issues(_ad_set(), CAMPAIGN), [])

	def test_budget_dates_and_placements(self):
		issues = meta.ad_set_issues(
			_ad_set(daily_budget=500, end_date="2026-11-14", placement_facebook=0, placement_instagram=0), CAMPAIGN
		)
		self.assertEqual(len(issues), 3)

	def test_manual_targeting_rules(self):
		issues = meta.ad_set_issues(_ad_set(audience_mode="Manual targeting", governorates="", age_from=45, age_to=24), CAMPAIGN)
		self.assertTrue(any("location" in i for i in issues))
		self.assertTrue(any("reversed" in i for i in issues))

	def test_special_category_blocks_manual_targeting(self):
		campaign = SimpleNamespace(objective="Engagement", special_ad_category="Housing")
		issues = meta.ad_set_issues(_ad_set(audience_mode="Manual targeting", governorates="Baghdad"), campaign)
		self.assertTrue(any("special ad category" in i for i in issues))

	def test_destination_must_fit_objective(self):
		issues = meta.ad_set_issues(_ad_set(destination="Instant form", optimization_goal="Leads"), CAMPAIGN)
		self.assertEqual(len(issues), 2)

	def test_ad_rules(self):
		ad_set = _ad_set(destination="Website")
		self.assertTrue(any("website URL" in i for i in meta.ad_issues(_ad(), ad_set)))
		self.assertEqual(meta.ad_issues(_ad(website_url="https://shop.example.com/p"), ad_set), [])
		self.assertTrue(any("2 cards" in i for i in meta.ad_issues(_ad(format="Carousel", cards=[1]), _ad_set())))
		self.assertTrue(any("choose a post" in i for i in meta.ad_issues(_ad(source="Existing post"), _ad_set())))
		self.assertTrue(any("primary text" in i for i in meta.ad_issues(_ad(primary_text=" "), _ad_set())))


class TestInstagramWindow(unittest.TestCase):
	def test_open_only_within_24_hours(self):
		now = datetime(2026, 11, 14, 12, 0, 0)
		with patch.object(policy, "now_datetime", return_value=now):
			self.assertTrue(policy.is_instagram_window_open("C1", now - timedelta(hours=23)))
			self.assertFalse(policy.is_instagram_window_open("C1", now - timedelta(hours=25)))
			self.assertFalse(policy.is_instagram_window_open("C1", ""))
			self.assertTrue(policy.is_instagram_window_open("C1", "2026-11-14 00:30:00"))


if __name__ == "__main__":
	unittest.main()
