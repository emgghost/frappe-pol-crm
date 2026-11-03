"""
Unit & Integration Tests for Story 4 (Issue #5):
Messaging Adapters (Kavenegar SMS & Telegram Bot) Integration Tests.
Mocking requests.post for complete offline isolation.
"""

import unittest
from unittest.mock import MagicMock, patch
import requests

from pol_crm.tests.frappe_mock import setup_mock_frappe, reset_mock_frappe

mock_frappe = setup_mock_frappe()

import frappe
from pol_crm.messaging.kavenegar import (
    get_kavenegar_config,
    send_kavenegar_sms,
    send_kavenegar_pattern,
)
from pol_crm.messaging.telegram import (
    get_telegram_config,
    send_telegram_message,
)


class TestKavenegarAdapter(unittest.TestCase):
    """Integration tests for Kavenegar SMS Gateway adapter."""

    def setUp(self):
        reset_mock_frappe()

    def test_get_kavenegar_config_from_settings(self):
        frappe.db.exists.side_effect = None
        frappe.db.exists.return_value = True

        mock_settings = MagicMock(
            kavenegar_api_key="KEY_FROM_SETTINGS_123",
            kavenegar_sender_line="10008888",
        )
        frappe.get_single.return_value = mock_settings

        api_key, sender = get_kavenegar_config()
        self.assertEqual(api_key, "KEY_FROM_SETTINGS_123")
        self.assertEqual(sender, "10008888")

    def test_get_kavenegar_config_fallback_to_frappe_conf(self):
        frappe.db.exists.side_effect = None
        frappe.db.exists.return_value = False
        frappe.conf = {"kavenegar_api_key": "CONF_API_KEY_456"}

        api_key, sender = get_kavenegar_config()
        self.assertEqual(api_key, "CONF_API_KEY_456")
        self.assertIsNone(sender)

    def test_send_sms_missing_api_key(self):
        frappe.db.exists.side_effect = None
        frappe.db.exists.return_value = False
        frappe.conf = {}

        res = send_kavenegar_sms("09121234567", "Hello")
        self.assertEqual(res, {"success": False, "error": "MISSING_API_KEY"})
        frappe.logger().warning.assert_called()

    @patch("pol_crm.messaging.kavenegar.get_kavenegar_config", return_value=("TEST_API_KEY", "10009999"))
    @patch("requests.post")
    def test_send_sms_success(self, mock_post, mock_config):
        mock_response = MagicMock(
            status_code=200,
            json=lambda: {
                "return": {"status": 200, "message": "تایید شد"},
                "entries": [{"messageid": 34567890, "message": "Hello", "status": 1}],
            },
        )
        mock_post.return_value = mock_response

        res = send_kavenegar_sms("09121234567", "Hello customer")

        self.assertEqual(res, {"success": True, "message_id": 34567890})
        mock_post.assert_called_once_with(
            "https://api.kavenegar.com/v1/TEST_API_KEY/sms/send.json",
            data={
                "receptor": "09121234567",
                "message": "Hello customer",
                "sender": "10009999",
            },
            timeout=10,
        )

    @patch("pol_crm.messaging.kavenegar.get_kavenegar_config", return_value=("TEST_API_KEY", "10009999"))
    @patch("requests.post")
    def test_send_sms_gateway_error(self, mock_post, mock_config):
        mock_response = MagicMock(
            status_code=200,
            json=lambda: {
                "return": {"status": 411, "message": "دریافت کننده نامعتبر است"},
                "entries": [],
            },
        )
        mock_post.return_value = mock_response

        res = send_kavenegar_sms("0912000", "Hello")
        self.assertEqual(res, {"success": False, "error": "دریافت کننده نامعتبر است"})

    @patch("pol_crm.messaging.kavenegar.get_kavenegar_config", return_value=("TEST_API_KEY", "10009999"))
    @patch("requests.post")
    def test_send_sms_network_timeout(self, mock_post, mock_config):
        mock_post.side_effect = requests.exceptions.Timeout("Connection timed out after 10s")

        res = send_kavenegar_sms("09121234567", "Hello")
        self.assertFalse(res["success"])
        self.assertIn("Connection timed out", res["error"])

    @patch("pol_crm.messaging.kavenegar.get_kavenegar_config", return_value=("TEST_API_KEY", "10009999"))
    @patch("requests.post")
    def test_send_sms_connection_error(self, mock_post, mock_config):
        mock_post.side_effect = requests.exceptions.ConnectionError("Name resolution failure")

        res = send_kavenegar_sms("09121234567", "Hello")
        self.assertFalse(res["success"])
        self.assertIn("Name resolution failure", res["error"])

    def test_send_pattern_missing_api_key(self):
        frappe.db.exists.side_effect = None
        frappe.db.exists.return_value = False
        frappe.conf = {}

        res = send_kavenegar_pattern("09121234567", "verify_otp", {"token": "1234"})
        self.assertEqual(res, {"success": False, "error": "MISSING_API_KEY"})

    @patch("pol_crm.messaging.kavenegar.get_kavenegar_config", return_value=("TEST_API_KEY", None))
    @patch("requests.post")
    def test_send_pattern_success(self, mock_post, mock_config):
        mock_response = MagicMock(
            status_code=200,
            json=lambda: {
                "return": {"status": 200, "message": "تایید شد"},
                "entries": [{"messageid": 88776655}],
            },
        )
        mock_post.return_value = mock_response

        tokens = {"token": "12345", "token2": "20percent", "token3": "POL"}
        res = send_kavenegar_pattern("09121234567", "OFFER_TEMPLATE", tokens)

        self.assertEqual(res, {"success": True, "message_id": 88776655})
        mock_post.assert_called_once_with(
            "https://api.kavenegar.com/v1/TEST_API_KEY/verify/lookup.json",
            data={
                "receptor": "09121234567",
                "template": "OFFER_TEMPLATE",
                "token": "12345",
                "token2": "20percent",
                "token3": "POL",
            },
            timeout=10,
        )

    @patch("pol_crm.messaging.kavenegar.get_kavenegar_config", return_value=("TEST_API_KEY", None))
    @patch("requests.post")
    def test_send_pattern_gateway_error(self, mock_post, mock_config):
        mock_response = MagicMock(
            status_code=200,
            json=lambda: {
                "return": {"status": 422, "message": "الگو یافت نشد"},
                "entries": [],
            },
        )
        mock_post.return_value = mock_response

        res = send_kavenegar_pattern("09121234567", "NON_EXISTENT_TEMPLATE", {"token": "1"})
        self.assertEqual(res, {"success": False, "error": "الگو یافت نشد"})

    @patch("pol_crm.messaging.kavenegar.get_kavenegar_config", return_value=("TEST_API_KEY", None))
    @patch("requests.post")
    def test_send_pattern_network_exception(self, mock_post, mock_config):
        mock_post.side_effect = requests.exceptions.RequestException("SSL Handshake failed")

        res = send_kavenegar_pattern("09121234567", "TEMPLATE", {"token": "1"})
        self.assertFalse(res["success"])
        self.assertIn("SSL Handshake failed", res["error"])


class TestTelegramAdapter(unittest.TestCase):
    """Integration tests for Telegram Bot adapter (relay & proxy support)."""

    def setUp(self):
        reset_mock_frappe()

    def test_get_telegram_config_from_settings(self):
        frappe.db.exists.side_effect = None
        frappe.db.exists.return_value = True

        mock_settings = MagicMock(
            telegram_bot_token="BOT_TOKEN_123:ABC",
            telegram_proxy_url="socks5://127.0.0.1:1080",
            telegram_relay_url="https://relay.polcrm.ir",
        )
        frappe.get_single.return_value = mock_settings

        token, proxy, relay = get_telegram_config()
        self.assertEqual(token, "BOT_TOKEN_123:ABC")
        self.assertEqual(proxy, "socks5://127.0.0.1:1080")
        self.assertEqual(relay, "https://relay.polcrm.ir")

    def test_get_telegram_config_fallback_to_frappe_conf(self):
        frappe.db.exists.side_effect = None
        frappe.db.exists.return_value = False
        frappe.conf = {"telegram_bot_token": "BOT_FROM_CONF"}

        token, proxy, relay = get_telegram_config()
        self.assertEqual(token, "BOT_FROM_CONF")
        self.assertIsNone(proxy)
        self.assertIsNone(relay)

    def test_send_telegram_missing_token(self):
        frappe.db.exists.side_effect = None
        frappe.db.exists.return_value = False
        frappe.conf = {}

        res = send_telegram_message("123456", "Hello")
        self.assertEqual(res, {"success": False, "error": "MISSING_BOT_TOKEN"})
        frappe.logger().warning.assert_called()

    @patch("pol_crm.messaging.telegram.get_telegram_config", return_value=("BOT_TOKEN_XYZ", None, None))
    @patch("requests.post")
    def test_send_telegram_standard_success(self, mock_post, mock_config):
        mock_response = MagicMock(
            status_code=200,
            json=lambda: {
                "ok": True,
                "result": {"message_id": 998877, "text": "Hello Telegram"},
            },
        )
        mock_post.return_value = mock_response

        res = send_telegram_message("123456789", "Hello Telegram", parse_mode="HTML")

        self.assertEqual(res, {"success": True, "message_id": 998877})
        mock_post.assert_called_once_with(
            "https://api.telegram.org/botBOT_TOKEN_XYZ/sendMessage",
            json={"chat_id": "123456789", "text": "Hello Telegram", "parse_mode": "HTML"},
            proxies=None,
            timeout=12,
        )

    @patch("pol_crm.messaging.telegram.get_telegram_config", return_value=("BOT_TOKEN_XYZ", "http://proxy.local:8080", "https://custom-relay.example.com/"))
    @patch("requests.post")
    def test_send_telegram_with_relay_and_proxy(self, mock_post, mock_config):
        """Tests that custom relay URL (stripped of trailing slash) and proxy dict are passed."""
        mock_response = MagicMock(
            status_code=200,
            json=lambda: {
                "ok": True,
                "result": {"message_id": 554433},
            },
        )
        mock_post.return_value = mock_response

        res = send_telegram_message("987654", "Relayed message")

        self.assertEqual(res, {"success": True, "message_id": 554433})
        mock_post.assert_called_once_with(
            "https://custom-relay.example.com/botBOT_TOKEN_XYZ/sendMessage",
            json={"chat_id": "987654", "text": "Relayed message", "parse_mode": "HTML"},
            proxies={"https": "http://proxy.local:8080", "http": "http://proxy.local:8080"},
            timeout=12,
        )

    @patch("pol_crm.messaging.telegram.get_telegram_config", return_value=("BOT_TOKEN_XYZ", None, None))
    @patch("requests.post")
    def test_send_telegram_api_error(self, mock_post, mock_config):
        mock_response = MagicMock(
            status_code=403,
            json=lambda: {
                "ok": False,
                "error_code": 403,
                "description": "Forbidden: bot was blocked by the user",
            },
        )
        mock_post.return_value = mock_response

        res = send_telegram_message("123456", "Hello")
        self.assertEqual(res, {"success": False, "error": "Forbidden: bot was blocked by the user"})

    @patch("pol_crm.messaging.telegram.get_telegram_config", return_value=("BOT_TOKEN_XYZ", None, None))
    @patch("requests.post")
    def test_send_telegram_network_timeout(self, mock_post, mock_config):
        mock_post.side_effect = requests.exceptions.Timeout("Telegram server timed out")

        res = send_telegram_message("123456", "Hello")
        self.assertFalse(res["success"])
        self.assertIn("Telegram server timed out", res["error"])

    @patch("pol_crm.messaging.telegram.get_telegram_config", return_value=("BOT_TOKEN_XYZ", None, None))
    @patch("requests.post")
    def test_send_telegram_connection_error(self, mock_post, mock_config):
        mock_post.side_effect = requests.exceptions.ConnectionError("Failed to establish connection")

        res = send_telegram_message("123456", "Hello")
        self.assertFalse(res["success"])
        self.assertIn("Failed to establish connection", res["error"])


if __name__ == "__main__":
    unittest.main()
