from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, add_to_date, now_datetime, nowdate

from pol_crm.marketing_automation import runner
from pol_crm.marketing_automation.doctype.mkt_campaign.mkt_campaign import process_due_campaigns
from pol_crm.marketing_automation.templates import AUTOMATIONS, CAMPAIGNS, create_from_template

SMS_OK = {"success": True, "message_id": "1"}

# The tests make their own customers. Generating records for Customer Group pulls in
# ERPNext's whole accounting chain, down to apps a POL CRM site may not have.
IGNORE_TEST_RECORD_DEPENDENCIES = ["Customer Group"]


def make_customer(name, segment="LOYAL", mobile="09121234567", **extra):
	if frappe.db.exists("Customer", name):
		frappe.delete_doc("Customer", name, force=True)
	return frappe.get_doc(
		{
			"doctype": "Customer",
			"customer_name": name,
			"customer_type": "Individual",
			"mobile_no": mobile,
			"custom_rfm_segment": segment,
			**extra,
		}
	).insert(ignore_permissions=True, ignore_mandatory=True)


class TestIranMarketing(IntegrationTestCase):
	def setUp(self):
		settings = frappe.get_single("Messaging Settings")
		settings.quiet_hours_enabled = 0
		settings.cap_per_day = 100
		settings.cap_per_week = 100
		settings.test_mode = 0
		settings.save()
		for dt in ("Mkt Message Log", "Mkt Campaign", "Mkt Scenario", "Loyalty Offer"):
			frappe.db.delete(dt)
		frappe.db.delete("Customer", {"customer_name": ("like", "POLT %")})
		self.ali = make_customer("POLT Ali", "CHAMPIONS")
		self.sara = make_customer("POLT Sara", "LOYAL", mobile="09351234567")
		self.reza = make_customer("POLT Reza", "LOST", mobile="09191234567")
		self.nophone = make_customer("POLT NoPhone", "CHAMPIONS", mobile=None)
		self.optout = make_customer("POLT OptOut", "CHAMPIONS", mobile="09131234567", custom_mkt_opted_out_all=1)

	def ours(self, names):
		return sorted(n for n in names if n.startswith("POLT "))

	def test_every_template_makes_a_document(self):
		for t in CAMPAIGNS:
			doc = frappe.get_doc("Mkt Campaign", create_from_template("campaign", t["id"]))
			self.assertEqual(doc.status, "Draft")
			self.assertTrue(doc.message)
		for t in AUTOMATIONS:
			doc = frappe.get_doc("Mkt Scenario", create_from_template("automation", t["id"]))
			self.assertEqual(doc.enabled, 0)

	def test_audience_follows_segments_phone_and_opt_out(self):
		campaign = frappe.get_doc(
			{
				"doctype": "Mkt Campaign",
				"campaign_name": "t",
				"message": "سلام {name}",
				"segments": [{"segment": "CHAMPIONS"}, {"segment": "LOYAL"}],
			}
		).insert()
		from pol_crm.marketing_automation.audience import get_audience

		self.assertEqual(self.ours(c.name for c in get_audience(campaign)), ["POLT Ali", "POLT Sara"])

	def test_code_placeholder_needs_a_discount(self):
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc(
				{"doctype": "Mkt Campaign", "campaign_name": "t", "message": "کد: {code}"}
			).insert()

	@patch("pol_crm.messaging.policy.send_plain_sms", return_value=SMS_OK)
	def test_campaign_sends_each_customer_their_own_code(self, sms):
		campaign = frappe.get_doc(
			{
				"doctype": "Mkt Campaign",
				"campaign_name": "یلدا",
				"segments": [{"segment": "CHAMPIONS"}, {"segment": "LOYAL"}],
				"discount_percent": 10,
				"code_valid_days": 7,
				"message": "{name} عزیز، {discount} تخفیف با کد {code} تا {expiry}",
			}
		).insert()
		campaign.schedule()
		campaign.reload()

		self.assertEqual(campaign.status, "Sent")
		self.assertEqual(campaign.sent_count, 2)
		texts = {call.args[0]: call.args[1] for call in sms.call_args_list}
		self.assertEqual(sorted(texts), ["09121234567", "09351234567"])
		self.assertIn("POLT Ali عزیز", texts["09121234567"])
		self.assertIn("۱۰٪", texts["09121234567"])

		codes = frappe.get_all("Loyalty Offer", filters={"reason": "CAMPAIGN"}, pluck="discount_code")
		self.assertEqual(len(set(codes)), 2)
		for code in codes:
			self.assertTrue(any(code in t for t in texts.values()))
		self.assertEqual(frappe.db.count("Mkt Message Log", {"campaign": campaign.name, "status": "SENT"}), 2)

	@patch("pol_crm.messaging.policy.send_plain_sms", return_value=SMS_OK)
	def test_scheduled_campaign_waits_for_its_time(self, sms):
		campaign = frappe.get_doc(
			{
				"doctype": "Mkt Campaign",
				"campaign_name": "بعداً",
				"segments": [{"segment": "LOST"}],
				"message": "سلام {name}",
				"send_at": add_to_date(now_datetime(), hours=2),
			}
		).insert()
		campaign.schedule()
		process_due_campaigns()
		self.assertEqual(frappe.db.get_value("Mkt Campaign", campaign.name, "status"), "Scheduled")
		sms.assert_not_called()

		frappe.db.set_value("Mkt Campaign", campaign.name, "send_at", add_to_date(now_datetime(), minutes=-1))
		process_due_campaigns()
		self.assertEqual(frappe.db.get_value("Mkt Campaign", campaign.name, "status"), "Sent")
		self.assertEqual(sms.call_args.args[0], "09191234567")

	def scenario(self, **values):
		return frappe.get_doc(
			{"doctype": "Mkt Scenario", "scenario_name": "t", "enabled": 1, "message_template": "سلام {name}", **values}
		).insert()

	@patch("pol_crm.messaging.policy.send_plain_sms", return_value=SMS_OK)
	def test_fifth_purchase_rewards_once(self, sms):
		self.scenario(trigger_type="PURCHASE_COUNT", purchase_count_target=5, discount_percent=15)
		with patch.object(runner, "purchase_totals", return_value=(5, 1000)):
			runner.run_purchase_automations(self.ali.name, 100)
			runner.run_purchase_automations(self.ali.name, 100)
		with patch.object(runner, "purchase_totals", return_value=(4, 900)):
			runner.run_purchase_automations(self.sara.name, 100)
		self.assertEqual([c.args[0] for c in sms.call_args_list], ["09121234567"])

	@patch("pol_crm.messaging.policy.send_plain_sms", return_value=SMS_OK)
	def test_spend_threshold_fires_when_crossed(self, sms):
		self.scenario(trigger_type="SPEND_THRESHOLD", spend_threshold=5000)
		with patch.object(runner, "purchase_totals", return_value=(3, 5200)):
			runner.run_purchase_automations(self.ali.name, 400)  # 4800 -> 5200: crossed
		with patch.object(runner, "purchase_totals", return_value=(3, 9000)):
			runner.run_purchase_automations(self.sara.name, 400)  # was already above
		self.assertEqual([c.args[0] for c in sms.call_args_list], ["09121234567"])

	@patch("pol_crm.messaging.policy.send_plain_sms", return_value=SMS_OK)
	def test_daily_automation_runs_once_at_its_hour(self, sms):
		scenario = self.scenario(trigger_type="INACTIVITY", inactivity_days=60, send_hour=10)
		early = runner.local_now().replace(hour=8)
		late = runner.local_now().replace(hour=11)
		with patch.object(runner, "customers_with_invoice_on", return_value=[self.reza.name]):
			with patch.object(runner, "local_now", return_value=early):
				runner.run_daily_automations()
			sms.assert_not_called()
			with patch.object(runner, "local_now", return_value=late):
				runner.run_daily_automations()
				runner.run_daily_automations()
		self.assertEqual([c.args[0] for c in sms.call_args_list], ["09191234567"])
		self.assertEqual(str(frappe.db.get_value("Mkt Scenario", scenario.name, "last_run_on")), str(late.date()))

	@patch("pol_crm.messaging.policy.send_plain_sms", return_value=SMS_OK)
	def test_birthday(self, sms):
		frappe.db.set_value(
			"Customer", self.sara.name, "custom_birth_date", f"1995-{nowdate()[5:]}"
		)
		scenario = self.scenario(trigger_type="BIRTHDAY", send_hour=0)
		runner.run_scenario_for_day(scenario, runner.getdate(nowdate()))
		self.assertEqual([c.args[0] for c in sms.call_args_list], ["09351234567"])

	@patch("pol_crm.messaging.policy.send_plain_sms", return_value=SMS_OK)
	def test_segment_change_messages_once_a_month(self, sms):
		self.scenario(trigger_type="RFM_SEGMENT_CHANGE", target_rfm_segment="AT_RISK")
		runner.trigger_segment_change_automations(self.ali.name, "LOYAL", "AT_RISK")
		runner.trigger_segment_change_automations(self.ali.name, "LOYAL", "AT_RISK")
		runner.trigger_segment_change_automations(self.ali.name, "LOYAL", "LOST")
		self.assertEqual(len(sms.call_args_list), 1)


class TestSignaladsRoute(IntegrationTestCase):
	def test_plain_sms_goes_through_iran_settings_when_iran_base_is_installed(self):
		from pol_crm.messaging import policy

		apps = [*frappe.get_installed_apps(), "iran_base"]
		with (
			patch.object(policy.frappe, "get_installed_apps", return_value=apps),
			patch("iran_base.utils.sms.send_sms", return_value={"data": {"message_id": 77}}) as send,
			patch.object(policy, "send_kavenegar_sms") as kavenegar,
		):
			result = policy.send_plain_sms("09121234567", "سلام")
		send.assert_called_once_with("09121234567", "سلام")
		kavenegar.assert_not_called()
		self.assertEqual(result, {"success": True, "message_id": 77})

	def test_a_gateway_error_is_a_failed_message_not_a_crash(self):
		from iran_base.utils.sms import SMSNotConfigured

		from pol_crm.messaging import policy

		apps = [*frappe.get_installed_apps(), "iran_base"]
		with (
			patch.object(policy.frappe, "get_installed_apps", return_value=apps),
			patch("iran_base.utils.sms.send_sms", side_effect=SMSNotConfigured("no token")),
		):
			result = policy.send_plain_sms("09121234567", "سلام")
		self.assertFalse(result["success"])
