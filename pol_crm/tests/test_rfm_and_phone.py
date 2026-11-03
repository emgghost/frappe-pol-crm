"""
Unit tests for POL CRM RFM Scoring and Phone Normalization
Can be executed directly via pytest or python unittest.
"""

from pol_crm.tests.frappe_mock import setup_mock_frappe

setup_mock_frappe()

import os
import json
import unittest

from pol_crm.messaging.phone_utils import normalize_iranian_mobile
from pol_crm.rfm.rfm_calculator import (
    score_recency,
    score_frequency,
    score_monetary,
    derive_segment,
    DEFAULT_RECENCY_THRESHOLDS,
    DEFAULT_FREQUENCY_THRESHOLDS,
    DEFAULT_MONETARY_THRESHOLDS,
)


class TestPhoneNormalization(unittest.TestCase):
    def test_iranian_numbers(self):
        cases = [
            ("09123456789", ("+989123456789", "09123456789", True)),
            ("+989123456789", ("+989123456789", "09123456789", True)),
            ("00989123456789", ("+989123456789", "09123456789", True)),
            ("9123456789", ("+989123456789", "09123456789", True)),
            ("۰۹۱۲۳۴۵۶۷۸۹", ("+989123456789", "09123456789", True)),  # Persian digits
            ("+98 912 345 6789", ("+989123456789", "09123456789", True)),
            ("02112345678", (None, None, False)),  # Landline
            ("invalid", (None, None, False)),
        ]
        for raw, expected in cases:
            with self.subTest(raw=raw):
                res = normalize_iranian_mobile(raw)
                self.assertEqual(res, expected)


class TestRFMScoring(unittest.TestCase):
    def test_recency(self):
        th = DEFAULT_RECENCY_THRESHOLDS  # [30, 60, 90, 180]
        self.assertEqual(score_recency(10, th), 5)
        self.assertEqual(score_recency(30, th), 5)
        self.assertEqual(score_recency(45, th), 4)
        self.assertEqual(score_recency(80, th), 3)
        self.assertEqual(score_recency(150, th), 2)
        self.assertEqual(score_recency(200, th), 1)

    def test_frequency(self):
        th = DEFAULT_FREQUENCY_THRESHOLDS  # [1, 3, 6, 12]
        self.assertEqual(score_frequency(1, th), 1)
        self.assertEqual(score_frequency(2, th), 2)
        self.assertEqual(score_frequency(5, th), 3)
        self.assertEqual(score_frequency(10, th), 4)
        self.assertEqual(score_frequency(20, th), 5)

    def test_monetary(self):
        th = DEFAULT_MONETARY_THRESHOLDS  # [1m, 3m, 8m, 20m]
        self.assertEqual(score_monetary(500000, th), 1)
        self.assertEqual(score_monetary(2000000, th), 2)
        self.assertEqual(score_monetary(5000000, th), 3)
        self.assertEqual(score_monetary(15000000, th), 4)
        self.assertEqual(score_monetary(30000000, th), 5)

    def test_segment_derivation(self):
        # Champions: R >= 4, F >= 4, M >= 4
        self.assertEqual(derive_segment(5, 5, 5), "CHAMPIONS")
        self.assertEqual(derive_segment(4, 4, 4), "CHAMPIONS")

        # Cant Lose: R <= 2, F >= 4, M >= 4
        self.assertEqual(derive_segment(2, 5, 5), "CANT_LOSE")

        # At Risk: R <= 2, F >= 3, M >= 3
        self.assertEqual(derive_segment(1, 3, 3), "AT_RISK")

        # New Customers: R == 5, F == 1
        self.assertEqual(derive_segment(5, 1, 1), "NEW_CUSTOMERS")


class TestCustomFieldsAndFixtures(unittest.TestCase):
    """Verifies that mandatory CRM custom fields (including Telegram Chat ID) are correctly defined."""

    def test_telegram_custom_fields_defined_in_json(self):
        fixture_path = os.path.join(
            os.path.dirname(__file__), "..", "fixtures", "custom_field.json"
        )
        self.assertTrue(os.path.exists(fixture_path), "custom_field.json must exist")
        with open(fixture_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        field_names = [cf.get("name") for cf in data]
        self.assertIn("Customer-custom_telegram_chat_id", field_names)
        self.assertIn("Contact-custom_telegram_chat_id", field_names)

        # Check Customer field properties
        cust_tg = next(cf for cf in data if cf.get("name") == "Customer-custom_telegram_chat_id")
        self.assertEqual(cust_tg.get("dt"), "Customer")
        self.assertEqual(cust_tg.get("fieldname"), "custom_telegram_chat_id")
        self.assertEqual(cust_tg.get("fieldtype"), "Data")
        self.assertEqual(cust_tg.get("insert_after"), "custom_mkt_preferred_channel")

        # Check Contact field properties
        contact_tg = next(cf for cf in data if cf.get("name") == "Contact-custom_telegram_chat_id")
        self.assertEqual(contact_tg.get("dt"), "Contact")
        self.assertEqual(contact_tg.get("fieldname"), "custom_telegram_chat_id")
        self.assertEqual(contact_tg.get("fieldtype"), "Data")
        self.assertEqual(contact_tg.get("insert_after"), "custom_rfm_segment")

    def test_hooks_fixtures_contains_telegram_fields(self):
        from pol_crm import hooks
        fixture_filters = hooks.fixtures[0]["filters"][0][2]
        self.assertIn("Customer-custom_telegram_chat_id", fixture_filters)
        self.assertIn("Contact-custom_telegram_chat_id", fixture_filters)

    def test_hooks_add_to_apps_screen_configured(self):
        """Verifies Frappe v15/v16 add_to_apps_screen hook for Apps Screen & Desk Switcher."""
        from pol_crm import hooks
        self.assertTrue(hasattr(hooks, "add_to_apps_screen"), "hooks.py must define add_to_apps_screen")
        self.assertIsInstance(hooks.add_to_apps_screen, list)
        self.assertGreater(len(hooks.add_to_apps_screen), 0)

        app_meta = hooks.add_to_apps_screen[0]
        self.assertEqual(app_meta.get("name"), "pol_crm")
        self.assertEqual(app_meta.get("title"), "POL CRM")
        self.assertEqual(app_meta.get("route"), "/app/pol-crm")
        self.assertTrue(app_meta.get("logo"), "Logo path must be provided")

    def test_logo_asset_file_exists_on_disk(self):
        """Verifies that the logo asset defined in hooks actually exists in public/images/."""
        logo_path = os.path.join(
            os.path.dirname(__file__), "..", "public", "images", "logo.svg"
        )
        self.assertTrue(os.path.exists(logo_path), f"Logo SVG must exist at {logo_path}")
        with open(logo_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("<svg", content)


if __name__ == "__main__":
    unittest.main()
