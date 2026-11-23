"""
Ready-made campaigns and automations. Each one already answers who, what and when; the
merchant picks one, changes what they like and sends it (a campaign) or turns it on (an
automation). Nothing goes out until they do.
"""

import frappe
from frappe import _

# who / what / when are the lines shown on the template card.
CAMPAIGNS = [
	{
		"id": "nowruz",
		"title": "تبریک نوروز با عیدی",
		"who": "مشتریانی که در یک سال اخیر خرید کرده‌اند",
		"what": "تبریک نوروز و کد تخفیف ۱۰٪ با اعتبار دو هفته",
		"when": "پیشنهاد: ۲۵ تا ۲۸ اسفند، ساعت ۱۰ صبح",
		"doc": {
			"campaign_name": "تبریک نوروز",
			"last_purchase": "BOUGHT_WITHIN",
			"last_purchase_days": 365,
			"discount_percent": 10,
			"code_valid_days": 14,
			"message": "{name} عزیز، نوروزتان پیروز! عیدی ما به شما {discount} تخفیف روی خرید بعدی است. کد: {code} (تا {expiry})",
		},
	},
	{
		"id": "yalda",
		"title": "شب یلدا",
		"who": "مشتریانی که در شش ماه اخیر خرید کرده‌اند",
		"what": "تبریک یلدا و کد تخفیف ۱۰٪ با اعتبار یک هفته",
		"when": "پیشنهاد: ۲۹ آذر، ساعت ۱۰ صبح",
		"doc": {
			"campaign_name": "شب یلدا",
			"last_purchase": "BOUGHT_WITHIN",
			"last_purchase_days": 180,
			"discount_percent": 10,
			"code_valid_days": 7,
			"message": "{name} عزیز، یلدایتان بلند و گرم! به مناسبت شب یلدا {discount} تخفیف با کد {code} تا {expiry}.",
		},
	},
	{
		"id": "mothers-day",
		"title": "روز مادر",
		"who": "همه‌ی مشتریانی که در یک سال اخیر خرید کرده‌اند",
		"what": "یادآوری هدیه‌ی روز مادر و کد تخفیف ۱۰٪",
		"when": "پیشنهاد: سه روز مانده به روز مادر",
		"doc": {
			"campaign_name": "روز مادر",
			"last_purchase": "BOUGHT_WITHIN",
			"last_purchase_days": 365,
			"discount_percent": 10,
			"code_valid_days": 5,
			"message": "{name} عزیز، روز مادر نزدیک است. برای خرید هدیه {discount} تخفیف با کد {code} تا {expiry}.",
		},
	},
	{
		"id": "fathers-day",
		"title": "روز پدر",
		"who": "همه‌ی مشتریانی که در یک سال اخیر خرید کرده‌اند",
		"what": "یادآوری هدیه‌ی روز پدر و کد تخفیف ۱۰٪",
		"when": "پیشنهاد: سه روز مانده به روز پدر",
		"doc": {
			"campaign_name": "روز پدر",
			"last_purchase": "BOUGHT_WITHIN",
			"last_purchase_days": 365,
			"discount_percent": 10,
			"code_valid_days": 5,
			"message": "{name} عزیز، روز پدر نزدیک است. برای خرید هدیه {discount} تخفیف با کد {code} تا {expiry}.",
		},
	},
	{
		"id": "season-sale",
		"title": "حراج پایان فصل",
		"who": "مشتریانی که بیش از یک بار خرید کرده‌اند",
		"what": "خبر حراج، بدون کد (تخفیف روی قیمت‌هاست)",
		"when": "روز شروع حراج، ساعت ۱۰ صبح",
		"doc": {
			"campaign_name": "حراج پایان فصل",
			"min_purchase_count": 2,
			"message": "{name} عزیز، حراج پایان فصل شروع شد! تا موجودی هست سر بزنید.",
		},
	},
	{
		"id": "new-products",
		"title": "محصولات جدید",
		"who": "مشتریانی که در سه ماه اخیر خرید کرده‌اند",
		"what": "خبر رسیدن محصولات جدید",
		"when": "همان روزی که محصولات می‌رسد",
		"doc": {
			"campaign_name": "محصولات جدید",
			"last_purchase": "BOUGHT_WITHIN",
			"last_purchase_days": 90,
			"message": "{name} عزیز، محصولات جدید رسید! برای دیدنشان سر بزنید.",
		},
	},
	{
		"id": "vip-thanks",
		"title": "تشکر از مشتریان وفادار",
		"who": "گروه‌های قهرمان و وفادار (RFM)",
		"what": "تشکر و کد تخفیف ۱۵٪ با اعتبار دو هفته",
		"when": "هر زمان که بخواهید",
		"doc": {
			"campaign_name": "تشکر از مشتریان وفادار",
			"segments": [{"segment": "CHAMPIONS"}, {"segment": "LOYAL"}],
			"discount_percent": 15,
			"code_valid_days": 14,
			"message": "{name} عزیز، از اینکه همیشه همراه ما هستید ممنونیم. هدیه‌ی ما: {discount} تخفیف با کد {code} تا {expiry}.",
		},
	},
]

AUTOMATIONS = [
	{
		"id": "winback-60",
		"title": "برگرداندن مشتری (۶۰ روز بی‌خرید)",
		"who": "هر مشتری که ۶۰ روز از آخرین خریدش گذشته",
		"what": "دلتنگی و کد تخفیف ۱۰٪ با اعتبار دو هفته",
		"when": "همان روز شصتم، ساعت ۱۰ صبح",
		"doc": {
			"scenario_name": "برگرداندن مشتری بعد از ۶۰ روز",
			"trigger_type": "INACTIVITY",
			"inactivity_days": 60,
			"send_hour": 10,
			"discount_percent": 10,
			"code_valid_days": 14,
			"message_template": "{name} عزیز، دلمان برایتان تنگ شده! {discount} تخفیف برای خرید بعدی با کد {code} تا {expiry}.",
		},
	},
	{
		"id": "at-risk",
		"title": "مشتری در خطر ریزش",
		"who": "هر مشتری که وارد گروه «در خطر» (AT_RISK) شود",
		"what": "کد تخفیف ۱۵٪ با اعتبار ده روز",
		"when": "همان لحظه که گروهش عوض شود (حداکثر یک بار در ماه)",
		"doc": {
			"scenario_name": "مشتری در خطر ریزش",
			"trigger_type": "RFM_SEGMENT_CHANGE",
			"target_rfm_segment": "AT_RISK",
			"discount_percent": 15,
			"code_valid_days": 10,
			"message_template": "{name} عزیز، مدتی است از شما خبری نداریم. با کد {code} تا {expiry} {discount} تخفیف دارید.",
		},
	},
	{
		"id": "first-thanks",
		"title": "تشکر از اولین خرید",
		"who": "هر مشتری که اولین خریدش را کرده",
		"what": "تشکر و درخواست نظر",
		"when": "یک روز بعد از اولین خرید، ساعت ۱۰ صبح",
		"doc": {
			"scenario_name": "تشکر از اولین خرید",
			"trigger_type": "FIRST_ORDER",
			"delay_days": 1,
			"send_hour": 10,
			"message_template": "{name} عزیز، از اولین خریدتان ممنونیم! اگر نظری دارید خوشحال می‌شویم بشنویم.",
		},
	},
	{
		"id": "after-purchase",
		"title": "پیگیری بعد از خرید",
		"who": "هر مشتری که خرید کرده",
		"what": "پرسیدن رضایت از خرید",
		"when": "هفت روز بعد از هر خرید، ساعت ۱۱ صبح",
		"doc": {
			"scenario_name": "پیگیری بعد از خرید",
			"trigger_type": "AFTER_PURCHASE",
			"delay_days": 7,
			"send_hour": 11,
			"message_template": "{name} عزیز، از خریدتان راضی بودید؟ اگر سؤال یا مشکلی هست کافی است پاسخ دهید.",
		},
	},
	{
		"id": "birthday",
		"title": "تبریک تولد",
		"who": "هر مشتری که تاریخ تولدش ثبت شده",
		"what": "تبریک تولد و کد تخفیف ۲۰٪ با اعتبار یک هفته",
		"when": "روز تولد، ساعت ۹ صبح",
		"doc": {
			"scenario_name": "تبریک تولد",
			"trigger_type": "BIRTHDAY",
			"send_hour": 9,
			"discount_percent": 20,
			"code_valid_days": 7,
			"message_template": "{name} عزیز، تولدتان مبارک! هدیه‌ی ما {discount} تخفیف با کد {code} تا {expiry}.",
		},
	},
	{
		"id": "fifth-purchase",
		"title": "جایزه‌ی خرید پنجم",
		"who": "هر مشتری که پنجمین خریدش را کرده",
		"what": "تشکر و کد تخفیف ۱۵٪",
		"when": "همان لحظه‌ی ثبت فاکتور پنجم",
		"doc": {
			"scenario_name": "جایزه‌ی خرید پنجم",
			"trigger_type": "PURCHASE_COUNT",
			"purchase_count_target": 5,
			"discount_percent": 15,
			"code_valid_days": 14,
			"message_template": "{name} عزیز، این پنجمین خرید شما بود، ممنونیم! {discount} تخفیف برای خرید بعدی با کد {code}.",
		},
	},
	{
		"id": "spend-milestone",
		"title": "جایزه‌ی رسیدن به سقف خرید",
		"who": "هر مشتری که جمع خریدش از مبلغی که تعیین می‌کنید بگذرد",
		"what": "تشکر و کد تخفیف ۱۰٪",
		"when": "همان لحظه‌ی ثبت فاکتوری که از سقف رد می‌شود",
		"needs": "مبلغ سقف را به واحد پول شرکت وارد کنید.",
		"doc": {
			"scenario_name": "جایزه‌ی رسیدن به سقف خرید",
			"trigger_type": "SPEND_THRESHOLD",
			"discount_percent": 10,
			"code_valid_days": 14,
			"message_template": "{name} عزیز، به جمع مشتریان ویژه‌ی ما پیوستید! {discount} تخفیف با کد {code} تا {expiry}.",
		},
	},
]

KINDS = {"campaign": ("Mkt Campaign", CAMPAIGNS), "automation": ("Mkt Scenario", AUTOMATIONS)}


@frappe.whitelist()
def get_templates(kind):
	if kind not in KINDS:
		frappe.throw(_("نوع قالب نامعتبر است."))
	return [{k: t.get(k) for k in ("id", "title", "who", "what", "when", "needs")} for t in KINDS[kind][1]]


@frappe.whitelist()
def create_from_template(kind, template_id):
	"""A draft campaign or a switched-off automation, filled from the template, for the merchant to edit."""
	if kind not in KINDS:
		frappe.throw(_("نوع قالب نامعتبر است."))
	doctype, templates = KINDS[kind]
	frappe.has_permission(doctype, "create", throw=True)
	template = next((t for t in templates if t["id"] == template_id), None)
	if not template:
		frappe.throw(_("این قالب پیدا نشد."))

	doc = frappe.get_doc({"doctype": doctype, **template["doc"]})
	if kind == "campaign":
		doc.suggested_time = template["when"]
	else:
		# Off until the merchant reviews it, so a missing amount can wait for them to fill it.
		doc.enabled = 0
		doc.flags.ignore_mandatory = True
	doc.insert()
	return doc.name
