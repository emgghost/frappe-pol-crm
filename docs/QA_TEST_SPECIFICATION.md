# سند مشخصات آزمون‌های خودکار و تضمین کیفیت POL CRM (QA Test Specification)

این مستند تشریح‌کننده کامل معماری تست، راهبرد ایزولاسیون، ماتریس پوشش آزمون‌ها، معیارهای پذیرش (Acceptance Criteria) و سناریوهای مرزی برای پروژه **POL CRM** است.

---

## ۱. راهبرد فنی و ایزولاسیون تست‌ها (Test Architecture & Isolation Strategy)

برای اجرای مستقل، سریع و بدون وابستگی آزمون‌ها به پایگاه‌داده MariaDB یا محیط سرور Frappe Bench:
1. **فریم‌ورک Frappe Mock (`pol_crm/tests/frappe_mock.py`):**
   - یک محیط Mocking کامل برای ماژول‌های `frappe` و `frappe.utils` شامل توابع تاریخ (`nowdate`, `now_datetime`, `add_days`, `date_diff`, `getdate`) و تبدیل داده (`cint`, `flt`) پیاده‌سازی شده است.
   - لایه دیتابیس Frappe (`frappe.db`) شامل متدهای `exists`, `get_value`, `set_value`, `sql`, `count`, `delete`, `commit` به صورت کاملاً کنترل‌شده و ایزوله شبیه‌سازی شده است.
   - مکانیزم ریست سراسری (`reset_mock_frappe`) در متد `setUp()` هر کلاس تست فراخوانی می‌شود تا از تداخل حالت (State Leakage) بین تست‌ها جلوگیری شود.
2. **شبیه‌سازی تماس‌های شبکه (HTTP Network Mocking):**
   - کلیه درخواست‌های ارسالی به وب‌سرویس‌های خارجی (مانند وب‌سرویس پیامک کاوه‌نگار و تلگرام بات) با `unittest.mock.patch` روی کتابخانه `requests.post` ایزوله شده‌اند.
   - خطاهای شبکه، قطعی اینترنت و تایم‌اوت (`requests.exceptions.Timeout`, `requests.exceptions.ConnectionError`, `requests.exceptions.RequestException`) تست شده‌اند تا عدم کرش کل سیستم اثبات شود.
3. **سازگاری دوگانه:**
   - کلیه آزمون‌ها قابلیت اجرا به هر دو روش استاندارد پایتون را دارا هستند:
     - `pytest pol_crm/tests`
     - `python3 -m unittest discover pol_crm/tests`

---

## ۲. ماتریس داستان‌های کاربری و سرفصل آزمون‌ها

### Story 1 (Issue #2): آزمون‌های RFM و چرخه حیات مشتری (`pol_crm/tests/test_rfm_calculator.py`)
- **محاسبه امتیازات سه‌گانه R، F و M:**
  - آزمون Recency با حد آستانه پیش‌فرض `[30, 60, 90, 180]` و آزمون با حد آستانه سفارشی.
  - آزمون Frequency با حد آستانه پیش‌فرض `[1, 3, 6, 12]` و مقادیر مرزی (۰، ۱، ۳، ۶، ۱۲ و بالاتر).
  - آزمون Monetary با حد آستانه پیش‌فرض `[1M, 3M, 8M, 20M]` بر حسب ریال و حدود آستانه سفارشی.
- **مشتق‌گیری تمام ۱۱ سگمنت مشتریان (Segment Derivation):**
  - پوشش قطعی و جامع تک‌تک ۱۱ سگمنت طبق ماتریس استاندارد:
    1. `CHAMPIONS` (مثال: R=5, F=5, M=5)
    2. `CANT_LOSE` (مثال: R=2, F=5, M=5)
    3. `AT_RISK` (مثال: R=2, F=3, M=3)
    4. `LOYAL` (مثال: R=3, F=4, M=2)
    5. `POTENTIAL_LOYALIST` (مثال: R=4, F=2, M=3)
    6. `NEW_CUSTOMERS` (مثال: R=5, F=1, M=1)
    7. `PROMISING` (مثال: R=4, F=1, M=2)
    8. `NEED_ATTENTION` (مثال: R=3, F=2, M=1)
    9. `ABOUT_TO_SLEEP` (مثال: R=2, F=2, M=1)
    10. `HIBERNATING` (مثال: R=1, F=1, M=1)
    11. `LOST` (مثال: R=3, F=1, M=1)
- **حالات مرزی و هوک‌ها:**
  - مشتری بدون فاکتور (Edge Case: ۰ فاکتور فروش) -> بازگرداندن امتیاز 111، سگمنت `None` و عدم کرش سیستم.
  - مشتری با یک فاکتور خرید جدید -> مشتق‌گیری صحیح سگمنت `NEW_CUSTOMERS`.
  - مشتری با فاکتورهای متعدد و گذار سگمنت (Segment Transition) -> اعتبارسنجی فراخوانی هوک `on_segment_changed`.
  - هوک‌های ثبتی/لغو فاکتور فروش (`on_sales_invoice_submit`, `on_sales_invoice_cancel`).
  - پردازش دسته‌ای شبانه (`nightly_recalculate_all_customers_rfm`) و تاب‌آوری در برابر خطای پایگاه‌داده یک مشتری خاص.
  - همگام‌سازی سگمنت با مخاطبین (`Contact`) و معاملات (`CRM Deal`).

### Story 2 (Issue #3): موتور خط‌مشی پیام‌رسانی و صف معوق (`pol_crm/tests/test_messaging_policy.py`)
- **ساعات سکوت (Quiet Hours):**
  - تبدیل تایم‌زون به `Asia/Tehran` مستقل از زمان محلی سرور.
  - آزمون بازه سکوت شبانه که از نیمه‌شب عبور می‌کند (ساعت ۲۱:۰۰ الی ۰۹:۰۰).
  - آزمون حالات فعال (۲۱:۰۰، ۲۳:۴۵، ۰۴:۳۰، ۰۸:۵۹) و غیرفعال (۰۹:۰۰، ۱۴:۰۰، ۲۰:۵۹).
  - آزمون بازه سکوت درون‌روز (ساعت ۱۳:۰۰ الی ۱۶:۰۰).
  - غیرفعال بودن ساعات سکوت (`quiet_hours_enabled = 0`).
- **سقف ارسال (Frequency Capping):**
  - سقف روزانه (`cap_per_day >= 1`) -> بازگرداندن وضعیت `SKIPPED` با علت `DAILY_CAP_REACHED`.
  - سقف هفتگی (`cap_per_week >= 2`) -> بازگرداندن وضعیت `SKIPPED` با علت `WEEKLY_CAP_REACHED`.
  - معافیت پیام‌های ضروری/فوری (`urgent=True`) و دسته‌بندی غیربازاریابی (`category="transactional"`).
- **انصراف و رضایت مشتری (Consent & Opt-Out):**
  - انصراف سراسری (`custom_mkt_opted_out_all = 1`).
  - انصراف فقط از پیامک (`custom_mkt_sms_opted_out = 1`).
  - لغو اشتراک در داک‌تایپ `Mkt Subscription` (`status = OPTED_OUT`).
- **حالت آزمایشی (Test Mode):**
  - بازنویسی و هدایت شماره گیرنده به شماره تست (`test_phone`) در صورت فعال بودن `test_mode`.
- **اعتبارسنجی کانال‌ها و ثبت لاگ:**
  - شماره همراه نامعتبر یا تلفن ثابت -> وضعیت `SKIPPED` با علت `INVALID_PHONE`.
  - کانال تلگرام بدون شناسه چت (`NO_CHAT_ID`).
  - کانال پشتیبانی نشده -> وضعیت `SKIPPED` با علت `UNSUPPORTED_CHANNEL`.
  - درج موفقیت‌آمیز در `Mkt Message Log` و مدیریت خطای دیتابیس.
  - پردازش صف پیام‌های معوقه (`process_postponed_messages`) در خارج از ساعات سکوت.

### Story 3 (Issue #4): موتور آفر و تخفیف‌ها (`pol_crm/tests/test_offer_engine.py`)
- **تولید کدهای تخفیف پویا (`generate_coupon_code`):**
  - فرمت استاندارد ۶ کاراکتری با پیشوند مشخص (مانند `POL-XXXXXX` یا `SECO-XXXXXX`).
  - حذف کاراکترهای ابهام‌برانگیز (`0`, `O`, `1`, `I`) از کد تولیدی و تست با رجکس.
  - آزمون یکتایی و عدم تداخل در تولید انبوه (۲۰۰ کد متوالی).
- **قوانین اعطای تخفیف:**
  - قانون خرید دوم (`SECOND_ORDER`): الزام به دقیقاً ۱ خرید قبلی و بازه زمانی بین ۱۵ تا ۴۵ روز از آخرین خرید.
  - رد درخواست در صورت داشتن ۲ خرید یا فاصله زمانی خارج از بازه (مثلاً ۱۰ روز یا ۵۰ روز).
  - ارزیابی سگمنت‌های `AT_RISK`، `POTENTIAL_LOYALIST` و `CANT_LOSE`.
- **محدودیت‌های تکرار:**
  - رعایت دوره استراحت (`cooldown_days`).
  - رعایت قاعده فقط یکبار در طول عمر (`once_per_lifetime`).
- **یکپارچه‌سازی و اجرا:**
  - ایجاد کد کوپن در داک‌تایپ بومی `Coupon Code` در صورت وجود.
  - ارسال پیامک اطلاع‌رسانی از طریق فراخوانی لایه خط‌مشی (`send_marketing_message`).
  - اجرای دسته‌ای شبانه (`daily_offer_decision_pass`) روی کلیه مشتریان فعال (`disabled = 0`).

### Story 4 (Issue #5): آداپتورهای پیام‌رسان کاوه‌نگار و تلگرام (`pol_crm/tests/test_messaging_adapters.py`)
- **آداپتور پیامک کاوه‌نگار (`kavenegar.py`):**
  - خواندن کلید API از تنظیمات یا پشتیبان در `frappe.conf`.
  - ارسال پیامک عادی (Standard SMS) با پاسخ موفقیت‌آمیز HTTP 200 و استخراج `message_id`.
  - مدیریت خطاهای درگاه کاوه‌نگار (مانند خطای ۴۱۱ و پیام خطای فارسی درگاه).
  - ارسال پیامک الگو/خدماتی (Verify / Pattern SMS) با تبدیل دیکشنری توکن‌ها (`token`, `token2`, ...).
  - مدیریت استثناهای شبکه (`requests.exceptions.Timeout`, `requests.exceptions.ConnectionError`, `requests.exceptions.RequestException`).
- **آداپتور تلگرام بات (`telegram.py`):**
  - خواندن توکن بات، پروکسی و آدرس رله (Relay URL) از تنظیمات.
  - ارسال موفق پیام و استخراج `message_id`.
  - پشتیبانی از آدرس رله اختصاصی برای سرورهای مستقر در ایران (`relay_url`).
  - ارسال از طریق سرور پروکسی (`proxies={"https": ..., "http": ...}`).
  - مدیریت خطاهای تلگرام (مانند `403 Forbidden: bot was blocked by the user`).
  - مدیریت خطاهای شبکه و تایم‌اوت تلگرام.

### Story 5 (Issue #6): سناریوهای بازاریابی و اتوماسیون (`pol_crm/tests/test_automation_runner.py`)
- **رندر ایمن قالب‌های Jinja2 (`render_template_string`):**
  - پشتیبانی از متغیرهای ساده (`{{ customer_name }}`) و ویژگی‌های آبجکت (`{{ customer.name }}`).
  - کنترل جریان و شروط (`{% if ... %} ... {% endif %}`).
  - تاب‌آوری در برابر خطاهای نحوی قالب (Syntax Errors): بازگرداندن متن اصلی قالب، ثبت لاگ اخطار و عدم توقف اجرای برنامه.
- **تریگر تغییر سگمنت (`trigger_segment_change_automations`):**
  - فیلتر سناریوهای فعال (`enabled = 1`) با نوع تریگر `RFM_SEGMENT_CHANGE` و سگمنت هدف.
  - مونتاژ کانتکست داینامیک مشتری و ارسال از طریق `send_marketing_message`.
  - انتخاب فیلد تلفن پشتیبان (`phone`) در صورت خالی بودن شماره همراه اصلی (`mobile_no`).
- **اسکن عدم فعالیت (`run_inactivity_scan`):**
  - اسکن مشتریان بر اساس تعداد دقیق روزهای عدم فعالیت (`inactivity_days`).
  - استخراج کاندیداها و ارسال پیام شخصی‌سازی شده.
  - وظیفه دوره‌ای شبانه (`daily_automation_scan`).

### نرمال‌سازی شماره‌های تماس ایران (`pol_crm/tests/test_rfm_and_phone.py`)
- پشتیبانی از ارقام فارسی و عربی (`۰۹۱۲...`).
- پشتیبانی از انواع پیشوندهای بین‌المللی (`+98`, `0098`, `98`, `09`, `9`).
- تبدیل به فرمت متعارف E.164 (`+98912...`) و فرمت محلی (`0912...`).
- تشخیص شماره‌های نامعتبر یا خطوط ثابت شهری تهران (`021...`).

---

## ۳. نحوه اجرای آزمون‌ها

### با استفاده از pytest:
```bash
pytest pol_crm/tests
```

### با استفاده از unittest:
```bash
python3 -m unittest discover pol_crm/tests
```

### اجرای فایل آزمون مشخص:
```bash
pytest pol_crm/tests/test_rfm_calculator.py
pytest pol_crm/tests/test_messaging_policy.py
pytest pol_crm/tests/test_offer_engine.py
pytest pol_crm/tests/test_messaging_adapters.py
pytest pol_crm/tests/test_automation_runner.py
```
