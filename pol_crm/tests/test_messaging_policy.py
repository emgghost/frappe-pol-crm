"""
Unit & Integration Tests for Story 2 (Issue #3):
Messaging Policy Engine, Quiet Hours, Frequency Capping & Opt-Out Tests.
"""

import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime
import pytz

from pol_crm.tests.frappe_mock import setup_mock_frappe, reset_mock_frappe

mock_frappe = setup_mock_frappe()

import frappe
from pol_crm.messaging.policy import (
    get_messaging_settings,
    is_in_quiet_hours,
    check_frequency_cap,
    is_customer_opted_out,
    log_message,
    send_marketing_message,
    process_postponed_messages,
)


class TestMessagingSettings(unittest.TestCase):
    """Tests for loading messaging settings from DB or defaults."""

    def setUp(self):
        reset_mock_frappe()

    def test_get_settings_from_db(self):
        frappe.db.exists.side_effect = None
        frappe.db.exists.return_value = True

        mock_doc = MagicMock(
            quiet_hours_enabled=1,
            quiet_start_hour=22,
            quiet_end_hour=8,
            timezone="Asia/Tehran",
            cap_per_day=3,
            cap_per_week=5,
            test_mode=1,
            test_phone="09121112233",
        )
        frappe.get_single.return_value = mock_doc

        settings = get_messaging_settings()
        self.assertEqual(settings["quiet_hours_enabled"], 1)
        self.assertEqual(settings["quiet_start_hour"], 22)
        self.assertEqual(settings["quiet_end_hour"], 8)
        self.assertEqual(settings["timezone"], "Asia/Tehran")
        self.assertEqual(settings["cap_per_day"], 3)
        self.assertEqual(settings["cap_per_week"], 5)
        self.assertEqual(settings["test_mode"], 1)
        self.assertEqual(settings["test_phone"], "09121112233")

    def test_get_settings_defaults(self):
        frappe.db.exists.side_effect = None
        frappe.db.exists.return_value = False

        settings = get_messaging_settings()
        self.assertEqual(settings["quiet_hours_enabled"], 1)
        self.assertEqual(settings["quiet_start_hour"], 21)
        self.assertEqual(settings["quiet_end_hour"], 9)
        self.assertEqual(settings["timezone"], "Asia/Tehran")
        self.assertEqual(settings["cap_per_day"], 1)
        self.assertEqual(settings["cap_per_week"], 2)
        self.assertEqual(settings["test_mode"], 0)
        self.assertIsNone(settings["test_phone"])


class TestQuietHours(unittest.TestCase):
    """
    Tests for Quiet Hours enforcement across timezones (Asia/Tehran)
    and midnight-crossing intervals.
    """

    def setUp(self):
        reset_mock_frappe()

    def test_quiet_hours_disabled(self):
        settings = {"quiet_hours_enabled": 0, "timezone": "Asia/Tehran"}
        self.assertFalse(is_in_quiet_hours(settings))

    @patch("pol_crm.messaging.policy.datetime")
    def test_quiet_hours_overnight_spanning_midnight(self, mock_dt):
        """Interval 21:00 to 09:00 spans midnight."""
        settings = {
            "quiet_hours_enabled": 1,
            "quiet_start_hour": 21,
            "quiet_end_hour": 9,
            "timezone": "Asia/Tehran",
        }
        tz = pytz.timezone("Asia/Tehran")

        # 21:00 -> Quiet hours active
        mock_dt.now.return_value = datetime(2026, 10, 18, 21, 0, 0, tzinfo=tz)
        self.assertTrue(is_in_quiet_hours(settings))

        # 23:45 -> Quiet hours active
        mock_dt.now.return_value = datetime(2026, 10, 18, 23, 45, 0, tzinfo=tz)
        self.assertTrue(is_in_quiet_hours(settings))

        # 04:30 (next morning) -> Quiet hours active
        mock_dt.now.return_value = datetime(2026, 10, 19, 4, 30, 0, tzinfo=tz)
        self.assertTrue(is_in_quiet_hours(settings))

        # 08:59 -> Quiet hours active
        mock_dt.now.return_value = datetime(2026, 10, 19, 8, 59, 59, tzinfo=tz)
        self.assertTrue(is_in_quiet_hours(settings))

        # 09:00 -> Quiet hours end
        mock_dt.now.return_value = datetime(2026, 10, 19, 9, 0, 0, tzinfo=tz)
        self.assertFalse(is_in_quiet_hours(settings))

        # 14:00 (afternoon) -> Quiet hours inactive
        mock_dt.now.return_value = datetime(2026, 10, 19, 14, 0, 0, tzinfo=tz)
        self.assertFalse(is_in_quiet_hours(settings))

        # 20:59 -> Quiet hours inactive
        mock_dt.now.return_value = datetime(2026, 10, 19, 20, 59, 0, tzinfo=tz)
        self.assertFalse(is_in_quiet_hours(settings))

    @patch("pol_crm.messaging.policy.datetime")
    def test_quiet_hours_daytime_window(self, mock_dt):
        """Interval 13:00 to 16:00 within same day."""
        settings = {
            "quiet_hours_enabled": 1,
            "quiet_start_hour": 13,
            "quiet_end_hour": 16,
            "timezone": "Asia/Tehran",
        }
        tz = pytz.timezone("Asia/Tehran")

        # 12:59 -> Inactive
        mock_dt.now.return_value = datetime(2026, 10, 18, 12, 59, 0, tzinfo=tz)
        self.assertFalse(is_in_quiet_hours(settings))

        # 13:00 -> Active
        mock_dt.now.return_value = datetime(2026, 10, 18, 13, 0, 0, tzinfo=tz)
        self.assertTrue(is_in_quiet_hours(settings))

        # 15:30 -> Active
        mock_dt.now.return_value = datetime(2026, 10, 18, 15, 30, 0, tzinfo=tz)
        self.assertTrue(is_in_quiet_hours(settings))

        # 16:00 -> Inactive
        mock_dt.now.return_value = datetime(2026, 10, 18, 16, 0, 0, tzinfo=tz)
        self.assertFalse(is_in_quiet_hours(settings))


class TestFrequencyCapping(unittest.TestCase):
    """Tests for daily and weekly marketing message frequency limits."""

    def setUp(self):
        reset_mock_frappe()

    def test_frequency_capping_no_log_doctype(self):
        frappe.db.exists.side_effect = None
        frappe.db.exists.return_value = False

        capped, reason = check_frequency_cap("CUST-1", {"cap_per_day": 1, "cap_per_week": 2})
        self.assertFalse(capped)
        self.assertIsNone(reason)

    def test_frequency_capping_daily_exceeded(self):
        frappe.db.exists.side_effect = None
        frappe.db.exists.return_value = True
        frappe.db.count.return_value = 1  # 1 message already sent today

        capped, reason = check_frequency_cap("CUST-1", {"cap_per_day": 1, "cap_per_week": 2})
        self.assertTrue(capped)
        self.assertEqual(reason, "DAILY_CAP_REACHED")

    def test_frequency_capping_weekly_exceeded(self):
        frappe.db.exists.side_effect = None
        frappe.db.exists.return_value = True

        # First call for day count = 0, second call for week count = 2
        frappe.db.count.side_effect = [0, 2]

        capped, reason = check_frequency_cap("CUST-1", {"cap_per_day": 1, "cap_per_week": 2})
        self.assertTrue(capped)
        self.assertEqual(reason, "WEEKLY_CAP_REACHED")

    def test_frequency_capping_within_limits(self):
        frappe.db.exists.side_effect = None
        frappe.db.exists.return_value = True
        frappe.db.count.side_effect = [0, 1]  # 0 today, 1 this week

        capped, reason = check_frequency_cap("CUST-1", {"cap_per_day": 1, "cap_per_week": 2})
        self.assertFalse(capped)
        self.assertIsNone(reason)


class TestOptOutChecks(unittest.TestCase):
    """Tests for global, channel-specific, and subscription opt-outs."""

    def setUp(self):
        reset_mock_frappe()

    def test_opted_out_all(self):
        frappe.db.get_value.return_value = {"custom_mkt_opted_out_all": 1, "custom_mkt_sms_opted_out": 0}
        self.assertTrue(is_customer_opted_out("CUST-OPTED", "SMS"))
        self.assertTrue(is_customer_opted_out("CUST-OPTED", "TELEGRAM"))

    def test_opted_out_sms_only(self):
        frappe.db.get_value.return_value = {"custom_mkt_opted_out_all": 0, "custom_mkt_sms_opted_out": 1}
        self.assertTrue(is_customer_opted_out("CUST-SMS-OPT", "SMS"))
        # Telegram is not opted out
        self.assertFalse(is_customer_opted_out("CUST-SMS-OPT", "TELEGRAM"))

    def test_opted_out_via_mkt_subscription(self):
        frappe.db.get_value.side_effect = [
            {"custom_mkt_opted_out_all": 0, "custom_mkt_sms_opted_out": 0},  # Customer doc
            "OPTED_OUT",  # Mkt Subscription status
        ]
        frappe.db.exists.side_effect = lambda dt, n=None: True if dt == "DocType" else False

        self.assertTrue(is_customer_opted_out("CUST-SUB-OPT", "SMS"))

    def test_active_consent_not_opted_out(self):
        frappe.db.get_value.side_effect = [
            {"custom_mkt_opted_out_all": 0, "custom_mkt_sms_opted_out": 0},
            "SUBSCRIBED",
        ]
        self.assertFalse(is_customer_opted_out("CUST-OK", "SMS"))


class TestAuditLogging(unittest.TestCase):
    """Tests for persisting audit records into Mkt Message Log."""

    def setUp(self):
        reset_mock_frappe()

    def test_log_message_success(self):
        frappe.db.exists.side_effect = None
        frappe.db.exists.return_value = True

        mock_doc = MagicMock(name="LOG-2026-0001")
        mock_doc.name = "LOG-2026-0001"
        frappe.get_doc.return_value = mock_doc

        name = log_message(
            customer="CUST-1",
            channel="SMS",
            to_address="09121234567",
            text="Test discount",
            status="SENT",
            message_id=999888,
        )

        self.assertEqual(name, "LOG-2026-0001")
        mock_doc.insert.assert_called_once_with(ignore_permissions=True)
        frappe.db.commit.assert_called_once()

    def test_log_message_catches_exception(self):
        frappe.db.exists.side_effect = None
        frappe.db.exists.return_value = True
        frappe.get_doc.side_effect = Exception("DB error")

        name = log_message("CUST-1", "SMS", "09121234567", "Hello", "SENT")
        self.assertIsNone(name)
        frappe.logger().error.assert_called()


class TestSendMarketingMessage(unittest.TestCase):
    """
    Comprehensive tests for send_marketing_message dispatcher:
    opt-out, quiet hours, frequency capping, urgent/transactional bypass,
    test mode redirection, SMS (normal & pattern), and Telegram.
    """

    def setUp(self):
        reset_mock_frappe()

    @patch("pol_crm.messaging.policy.is_customer_opted_out", return_value=True)
    def test_send_opted_out_skipped(self, mock_opt):
        res = send_marketing_message(customer="CUST-OPT", phone="09121234567", text="Hi")
        self.assertEqual(res, {"status": "SKIPPED", "reason": "OPTED_OUT"})

    @patch("pol_crm.messaging.policy.is_customer_opted_out", return_value=False)
    @patch("pol_crm.messaging.policy.is_in_quiet_hours", return_value=True)
    def test_send_quiet_hours_postponed(self, mock_qh, mock_opt):
        res = send_marketing_message(customer="CUST-1", phone="09121234567", text="Hi", category="marketing")
        self.assertEqual(res, {"status": "POSTPONED", "reason": "QUIET_HOURS"})

    @patch("pol_crm.messaging.policy.is_customer_opted_out", return_value=False)
    @patch("pol_crm.messaging.policy.is_in_quiet_hours", return_value=True)
    @patch("pol_crm.messaging.policy.send_kavenegar_sms", return_value={"success": True, "message_id": 111})
    def test_send_urgent_bypasses_quiet_hours(self, mock_sms, mock_qh, mock_opt):
        """Urgent message should bypass quiet hours and send immediately."""
        res = send_marketing_message(
            customer="CUST-1",
            phone="09121234567",
            text="Your OTP is 1234",
            urgent=True,
            category="marketing",
        )
        self.assertEqual(res, {"status": "SENT", "message_id": 111})
        mock_sms.assert_called_once()

    @patch("pol_crm.messaging.policy.is_customer_opted_out", return_value=False)
    @patch("pol_crm.messaging.policy.is_in_quiet_hours", return_value=True)
    @patch("pol_crm.messaging.policy.send_kavenegar_sms", return_value={"success": True, "message_id": 222})
    def test_send_transactional_category_bypasses_quiet_hours(self, mock_sms, mock_qh, mock_opt):
        """Transactional messages (non-marketing) bypass quiet hours."""
        res = send_marketing_message(
            customer="CUST-1",
            phone="09121234567",
            text="Invoice #1001 paid",
            category="transactional",
        )
        self.assertEqual(res, {"status": "SENT", "message_id": 222})
        mock_sms.assert_called_once()

    @patch("pol_crm.messaging.policy.is_customer_opted_out", return_value=False)
    @patch("pol_crm.messaging.policy.is_in_quiet_hours", return_value=False)
    @patch("pol_crm.messaging.policy.check_frequency_cap", return_value=(True, "DAILY_CAP_REACHED"))
    def test_send_frequency_cap_skipped(self, mock_cap, mock_qh, mock_opt):
        res = send_marketing_message(customer="CUST-1", phone="09121234567", text="Offer", category="marketing")
        self.assertEqual(res, {"status": "SKIPPED", "reason": "DAILY_CAP_REACHED"})

    @patch("pol_crm.messaging.policy.is_customer_opted_out", return_value=False)
    @patch("pol_crm.messaging.policy.is_in_quiet_hours", return_value=False)
    @patch("pol_crm.messaging.policy.check_frequency_cap", return_value=(False, None))
    @patch("pol_crm.messaging.policy.get_messaging_settings")
    @patch("pol_crm.messaging.policy.send_kavenegar_sms", return_value={"success": True, "message_id": 333})
    def test_send_test_mode_redirection(self, mock_sms, mock_settings, mock_cap, mock_qh, mock_opt):
        """In test mode, messages are redirected to test_phone."""
        mock_settings.return_value = {
            "test_mode": 1,
            "test_phone": "09120000000",
            "quiet_hours_enabled": 0,
        }
        res = send_marketing_message(
            customer="CUST-1",
            phone="09129999999",  # Original customer phone
            text="Testing promo",
            channel="SMS",
        )
        self.assertEqual(res, {"status": "SENT", "message_id": 333})
        # Verifies SMS was sent to test phone 09120000000, NOT the original phone
        mock_sms.assert_called_once_with("09120000000", "Testing promo")

    @patch("pol_crm.messaging.policy.is_customer_opted_out", return_value=False)
    @patch("pol_crm.messaging.policy.is_in_quiet_hours", return_value=False)
    @patch("pol_crm.messaging.policy.check_frequency_cap", return_value=(False, None))
    @patch("pol_crm.messaging.policy.get_messaging_settings")
    @patch("pol_crm.messaging.policy.send_telegram_message", return_value={"success": True, "message_id": 444})
    def test_send_telegram_test_mode_redirection(self, mock_tg, mock_settings, mock_cap, mock_qh, mock_opt):
        """In test mode, Telegram messages are redirected to test_phone/test chat."""
        mock_settings.return_value = {
            "test_mode": 1,
            "test_phone": "999888777",
            "quiet_hours_enabled": 0,
        }
        res = send_marketing_message(
            customer="CUST-TG-TEST",
            telegram_chat_id="111222333",  # Original customer chat ID
            text="Testing Telegram promo",
            channel="TELEGRAM",
        )
        self.assertEqual(res, {"status": "SENT", "message_id": 444})
        # Verifies message was redirected to test chat ID 999888777, NOT the original chat ID
        mock_tg.assert_called_once_with("999888777", "Testing Telegram promo")

    @patch("pol_crm.messaging.policy.is_customer_opted_out", return_value=False)
    @patch("pol_crm.messaging.policy.is_in_quiet_hours", return_value=False)
    @patch("pol_crm.messaging.policy.check_frequency_cap", return_value=(False, None))
    def test_send_sms_invalid_phone(self, mock_cap, mock_qh, mock_opt):
        res = send_marketing_message(customer="CUST-1", phone="02112345678", text="Invalid phone")
        self.assertEqual(res, {"status": "SKIPPED", "reason": "INVALID_PHONE"})

    @patch("pol_crm.messaging.policy.is_customer_opted_out", return_value=False)
    @patch("pol_crm.messaging.policy.is_in_quiet_hours", return_value=False)
    @patch("pol_crm.messaging.policy.check_frequency_cap", return_value=(False, None))
    @patch("pol_crm.messaging.policy.send_kavenegar_sms", return_value={"success": True, "message_id": 555})
    def test_send_sms_standard_success(self, mock_sms, mock_cap, mock_qh, mock_opt):
        res = send_marketing_message(customer="CUST-1", phone="09121234567", text="Standard promo")
        self.assertEqual(res, {"status": "SENT", "message_id": 555})
        mock_sms.assert_called_once_with("09121234567", "Standard promo")

    @patch("pol_crm.messaging.policy.is_customer_opted_out", return_value=False)
    @patch("pol_crm.messaging.policy.is_in_quiet_hours", return_value=False)
    @patch("pol_crm.messaging.policy.check_frequency_cap", return_value=(False, None))
    @patch("pol_crm.messaging.policy.send_kavenegar_sms", return_value={"success": False, "error": "INSUFFICIENT_CREDIT"})
    def test_send_sms_standard_failure(self, mock_sms, mock_cap, mock_qh, mock_opt):
        res = send_marketing_message(customer="CUST-1", phone="09121234567", text="Promo")
        self.assertEqual(res, {"status": "FAILED", "error": "INSUFFICIENT_CREDIT"})

    @patch("pol_crm.messaging.policy.is_customer_opted_out", return_value=False)
    @patch("pol_crm.messaging.policy.is_in_quiet_hours", return_value=False)
    @patch("pol_crm.messaging.policy.check_frequency_cap", return_value=(False, None))
    @patch("pol_crm.messaging.policy.send_kavenegar_pattern", return_value={"success": True, "message_id": 777})
    def test_send_sms_pattern_success(self, mock_pattern, mock_cap, mock_qh, mock_opt):
        res = send_marketing_message(
            customer="CUST-1",
            phone="09121234567",
            template_code="OFFER_PROMO",
            template_tokens={"code": "POL-123456", "percent": "20"},
        )
        self.assertEqual(res, {"status": "SENT", "message_id": 777})
        mock_pattern.assert_called_once_with("09121234567", "OFFER_PROMO", {"code": "POL-123456", "percent": "20"})

    @patch("pol_crm.messaging.policy.is_customer_opted_out", return_value=False)
    @patch("pol_crm.messaging.policy.is_in_quiet_hours", return_value=False)
    @patch("pol_crm.messaging.policy.check_frequency_cap", return_value=(False, None))
    @patch("pol_crm.messaging.policy.send_telegram_message", return_value={"success": True, "message_id": 888})
    def test_send_telegram_success(self, mock_tg, mock_cap, mock_qh, mock_opt):
        res = send_marketing_message(
            customer="CUST-1",
            telegram_chat_id="123456789",
            channel="TELEGRAM",
            text="Telegram update",
        )
        self.assertEqual(res, {"status": "SENT", "message_id": 888})
        mock_tg.assert_called_once_with("123456789", "Telegram update")

    @patch("pol_crm.messaging.policy.is_customer_opted_out", return_value=False)
    @patch("pol_crm.messaging.policy.is_in_quiet_hours", return_value=False)
    @patch("pol_crm.messaging.policy.check_frequency_cap", return_value=(False, None))
    def test_send_telegram_missing_chat_id(self, mock_cap, mock_qh, mock_opt):
        res = send_marketing_message(
            customer="CUST-1",
            telegram_chat_id=None,
            channel="TELEGRAM",
            text="Telegram update",
        )
        self.assertEqual(res, {"status": "SKIPPED", "reason": "NO_CHAT_ID"})

    @patch("pol_crm.messaging.policy.is_customer_opted_out", return_value=False)
    @patch("pol_crm.messaging.policy.is_in_quiet_hours", return_value=False)
    @patch("pol_crm.messaging.policy.check_frequency_cap", return_value=(False, None))
    def test_send_unsupported_channel(self, mock_cap, mock_qh, mock_opt):
        res = send_marketing_message(customer="CUST-1", channel="WHATSAPP", text="Test")
        self.assertEqual(res, {"status": "SKIPPED", "reason": "UNSUPPORTED_CHANNEL"})


class TestProcessPostponedMessages(unittest.TestCase):
    """Tests for hourly processing of messages postponed during quiet hours."""

    def setUp(self):
        reset_mock_frappe()

    @patch("pol_crm.messaging.policy.is_in_quiet_hours", return_value=True)
    def test_process_postponed_during_quiet_hours_noop(self, mock_qh):
        process_postponed_messages()
        frappe.get_all.assert_not_called()

    @patch("pol_crm.messaging.policy.is_in_quiet_hours", return_value=False)
    @patch("pol_crm.messaging.policy.send_marketing_message", return_value={"status": "SENT", "message_id": 999})
    def test_process_postponed_messages_success(self, mock_send, mock_qh):
        frappe.db.exists.side_effect = None
        frappe.db.exists.return_value = True

        mock_item = MagicMock(
            customer="CUST-P1",
            recipient="09121234567",
            channel="SMS",
            message_body="Delayed message",
            category="marketing",
        )
        mock_item.name = "LOG-POSTPONED-1"
        frappe.get_all.return_value = [mock_item]

        process_postponed_messages()

        mock_send.assert_called_once_with(
            customer="CUST-P1",
            phone="09121234567",
            text="Delayed message",
            channel="SMS",
            category="marketing",
            existing_log_name="LOG-POSTPONED-1",
        )
        frappe.db.delete.assert_not_called()

    @patch("pol_crm.messaging.policy.is_in_quiet_hours", return_value=False)
    @patch("pol_crm.messaging.policy.send_marketing_message", return_value={"status": "SENT", "message_id": 888})
    def test_process_postponed_telegram_messages_success(self, mock_send, mock_qh):
        """Verifies Telegram postponed messages pass telegram_chat_id correctly (Blocker Bug Fix)."""
        frappe.db.exists.side_effect = None
        frappe.db.exists.return_value = True

        mock_item = MagicMock(
            customer="CUST-TG",
            recipient="123456789",
            channel="TELEGRAM",
            message_body="Delayed Telegram alert",
            category="marketing",
        )
        mock_item.name = "LOG-POSTPONED-TG"
        frappe.get_all.return_value = [mock_item]

        process_postponed_messages()

        mock_send.assert_called_once_with(
            customer="CUST-TG",
            telegram_chat_id="123456789",
            text="Delayed Telegram alert",
            channel="TELEGRAM",
            category="marketing",
            existing_log_name="LOG-POSTPONED-TG",
        )
        frappe.db.delete.assert_not_called()


class TestEnqueueMarketingMessage(unittest.TestCase):
    """Tests for asynchronous background dispatch via frappe.enqueue."""

    def setUp(self):
        reset_mock_frappe()

    def test_enqueue_marketing_message_in_test_mode(self):
        """In unit testing (frappe.flags.in_test = True), executes synchronously."""
        from pol_crm.messaging.policy import enqueue_marketing_message

        with patch("pol_crm.messaging.policy.send_marketing_message", return_value={"status": "SENT"}) as mock_send:
            res = enqueue_marketing_message(customer="CUST-1", phone="09121234567", text="Sync test")
            self.assertEqual(res, {"status": "SENT"})
            mock_send.assert_called_once()
            frappe.enqueue.assert_not_called()

    def test_enqueue_marketing_message_calls_redis_queue(self):
        """In production (frappe.flags.in_test = False), enqueues to short Redis queue."""
        from pol_crm.messaging.policy import enqueue_marketing_message

        frappe.flags.in_test = False
        try:
            enqueue_marketing_message(
                customer="CUST-PROD",
                phone="09121234567",
                text="Async background task",
                channel="SMS",
                template_code="TPL_1",
            )
            frappe.enqueue.assert_called_once_with(
                "pol_crm.messaging.policy.send_marketing_message",
                queue="short",
                customer="CUST-PROD",
                phone="09121234567",
                telegram_chat_id=None,
                text="Async background task",
                channel="SMS",
                template_code="TPL_1",
                template_tokens=None,
                category="marketing",
                urgent=False,
            )
        finally:
            frappe.flags.in_test = True


if __name__ == "__main__":
    unittest.main()
