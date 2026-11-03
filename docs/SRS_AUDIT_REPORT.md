# گزارش ممیزی جامع سامانه POL CRM و ارزیابی انطباق با سند نیازمندی‌ها (SRS Audit Report)

**مرجع ارزیابی:** `pol_crm/docs/SYSTEM_REQUIREMENTS_SPECIFICATION.md` (نسخه 1.0.0 مصوب)  
**سند معماری تست:** `pol_crm/docs/adr/0001-standalone-frappe-test-mock-architecture.md`  
**وضعیت فعلی آزمون‌ها:** ۱۱۵ آزمون پاس‌شده در ۰.۰۶۳ ثانیه (با احتساب ایزولاسیون Mock)  
**نقش تحلیل‌گر:** Lead Software Architect & Senior Frappe/ERPNext Developer  
**تاریخ تدوین:** پاییز ۱۴۰۳ (۲۰۲۶)  

---

## فهرست مطالب
1. [خلاصه اجرایی (Executive Summary)](#خلاصه-اجرایی-executive-summary)
2. [🔴 مغایرت‌های بحرانی و باگ‌های مسدودکننده (Critical Discrepancies & Blocker Bugs)](#-۱-مغایرت‌های-بحرانی-و-باگ‌های-مسدودکننده-critical-discrepancies--blocker-bugs)
3. [🟠 ریسک‌های کارایی و معماری (Performance & Architectural Risks)](#-۲-ریسکهای-کارایی-و-معماری-performance--architectural-risks)
4. [🟡 نیازمندی‌های پیاده‌سازی‌نشده یا ناقص سند SRS (Missing Requirements)](#-۳-نیازمندیهای-پیادهسازینشده-یا-ناقص-سند-srs-missing-requirements)
5. [🟢 برنامه عملیاتی و اصلاحات مشخص کد (Concrete Refactoring Steps)](#-۴-برنامه-عملیاتی-و-اصلاحات-مشخص-کد-concrete-refactoring-steps)
6. [ماتریس ارزیابی کیفیت آزمون‌ها (ADR 0001 Evaluation)](#۵-ماتریس-ارزیابی-کیفیت-آزمونها-adr-0001-evaluation)

---

## خلاصه اجرایی (Executive Summary)
سامانه `pol_crm` یک گام مهندسی بسیار منسجم در بازمعماری افزونه‌های پراکنده Twenty CRM (`crmloyality` و `twenty-automation`) به هسته ERPNext است. معماری تست ایزوله (ADR 0001)، فرمول‌بندی ۱۱ سگمنت RFM، فیلدهای سفارشی، و رابط‌های دسک و نماهای اختصاصی CRM با دقت بالایی پایه‌گذاری شده‌اند.  
با این وجود، تطبیق خط‌به‌خط کد پیاده‌سازی‌شده با سند رسمی **SRS** و سناریوهای عملیاتی واقعی در محیط پروداکشن، **چند باگ مسدودکننده (Blocker Bugs)**، **گلوگاه‌های شدید کارایی (Performance Bottlenecks)** و **انحرافات ساختاری از نیازمندی‌ها** را آشکار کرد که نیازمند اصلاح پیش از استقرار نهایی هستند.

---

## 🔴 ۱. مغایرت‌های بحرانی و باگ‌های مسدودکننده (Critical Discrepancies & Blocker Bugs)

### ۱.۱. عدم لحاظ فاکتورهای مرجوعی / بستانکار (Credit Notes / Returns) در محاسبه RFM
- **مسیر فایل و شماره خطوط:** [`pol_crm/pol_crm/rfm/rfm_calculator.py#L196-L207`](file:///home/emg/Source/migrate-twenty-to-frappe/pol_crm/pol_crm/rfm/rfm_calculator.py#L196-L207) و [`pol_crm/pol_crm/rfm/rfm_calculator.py#L391-L400`](file:///home/emg/Source/migrate-twenty-to-frappe/pol_crm/pol_crm/rfm/rfm_calculator.py#L391-L400)
- **شرح باگ:** در ERPNext، فاکتورهای برگشت از فروش (Return / Credit Note) با `is_return = 1` و مبالغ منفی ثبت می‌شوند، اما دارای `docstatus = 1` هستند.  
  در متد `_calculate_rfm_for_single_customer`، کوئری فقط `docstatus = 1` را چک می‌کند. در نتیجه:
  1. فاکتور مرجوعی یک خرید مجزا شمرده شده و متغیر Frequency (تکرار خرید) مشتری به جای کسر، **یک واحد افزایش** می‌یابد!
  2. تاریخ ثبت مرجوعی به عنوان `last_purchase_date` شناسایی شده و تازگی خرید (Recency) مشتری بدون خرید واقعی به ۵ (عالی) ارتقا می‌یابد!
  3. در دستور تجمیعی SQL خط ۳۹۱ نیز شرط `is_return = 0` وجود ندارد.

---

### ۱.۲. محاسبه سفارش‌های پیش‌نویس (Draft Sales Orders) در امتیاز RFM
- **مسیر فایل و شماره خطوط:** [`pol_crm/pol_crm/rfm/rfm_calculator.py#L210-L221`](file:///home/emg/Source/migrate-twenty-to-frappe/pol_crm/pol_crm/rfm/rfm_calculator.py#L210-L221) و [`pol_crm/pol_crm/rfm/rfm_calculator.py#L395-L400`](file:///home/emg/Source/migrate-twenty-to-frappe/pol_crm/pol_crm/rfm/rfm_calculator.py#L395-L400)
- **شرح باگ:** طبق بند ۴.۱.۱ سند SRS:  
  > *«سیستم باید متغیرهای سه‌گانه را به ازای هر مشتری فقط بر اساس اسناد فروش قطعی و پرداخت‌شده (Sales Invoice با docstatus=1) محاسبه نماید.»*  
  اما در صورت عدم وجود فاکتور، کد به جدول `Sales Order` با شرط `docstatus != 2` بازمی‌گردد. مقدار `docstatus != 2` شامل `docstatus = 0` یعنی **سفارش‌های پیش‌نویس و تأییدنشده (Draft)** است. هر پیش‌نویس موقتی که کاربر در سیستم ثبت کند، باعث ارتقای کاذب امتیاز مشتری و قرارگیری اشتباه در سگمنت‌های طلایی می‌شود.

---

### ۱.۳. از کار افتادن قطعی پیام‌های معوقه تلگرام در پردازش صف ساعتی (`process_postponed_messages`)
- **مسیر فایل و شماره خطوط:** [`pol_crm/pol_crm/messaging/policy.py#L246-L252`](file:///home/emg/Source/migrate-twenty-to-frappe/pol_crm/pol_crm/messaging/policy.py#L246-L252) در مقایسه با [`pol_crm/pol_crm/messaging/policy.py#L212-L217`](file:///home/emg/Source/migrate-twenty-to-frappe/pol_crm/pol_crm/messaging/policy.py#L212-L217)
- **شرح باگ:** تابع `process_postponed_messages` هنگام بازپردازش پیام‌های معوق در ساعت ۰۹:۰۰ صبح، آرگومان گیرنده را بدون توجه به کانال، منحصراً به صورت `phone=item.recipient` به متد `send_marketing_message` ارسال می‌کند:
  ```python
  res = send_marketing_message(
      customer=item.customer,
      phone=item.recipient,  # برای تلگرام مقدار telegram_chat_id خالی می‌ماند!
      text=item.message_body,
      channel=item.channel,
      category=item.category,
  )
  ```
  در داخل `send_marketing_message` (خط ۲۱۳)، در صورت `channel == "TELEGRAM"`، متغیر `target_chat = telegram_chat_id` بررسی می‌شود که `None` است. بنابراین **۱۰۰٪ پیام‌های معوق تلگرام** با خطای `NO_CHAT_ID` متوقف و از دیتابیس حذف می‌شوند!

---

### ۱.۴. نادیده گرفتن حالت آزمایشی (Test Mode) در کانال تلگرام
- **مسیر فایل و شماره خطوط:** [`pol_crm/pol_crm/messaging/policy.py#L186-L191`](file:///home/emg/Source/migrate-twenty-to-frappe/pol_crm/pol_crm/messaging/policy.py#L186-L191) و [`pol_crm/pol_crm/messaging/policy.py#L212-L224`](file:///home/emg/Source/migrate-twenty-to-frappe/pol_crm/pol_crm/messaging/policy.py#L212-L224)
- **شرح باگ:** طبق بند ۴.۳.۱ سند SRS، در صورت فعال بودن `test_mode`، باید تمامی پیام‌ها به شماره/اکانت آزمایشی ارسال شوند تا از ارسال اشتباه در محیط‌های تستی و استیجینگ جلوگیری شود.  
  متغیر `final_recipient` فقط در شاخه SMS استفاده شده و در شاخه `TELEGRAM` مستقیماً به `telegram_chat_id` واقعی پیام ارسال می‌شود! در محیط استیجینگ، پیام‌های واقعی تلگرام به مشتریان ارسال خواهد شد.

---

### ۱.۵. عدم انطباق توکن‌های وب‌سرویس پترن کاوه‌نگار (Pattern SMS Incompatibility)
- **مسیر فایل و شماره خطوط:** [`pol_crm/pol_crm/rfm/offer_engine.py#L156`](file:///home/emg/Source/migrate-twenty-to-frappe/pol_crm/pol_crm/rfm/offer_engine.py#L156) و [`pol_crm/pol_crm/messaging/kavenegar.py#L69-L72`](file:///home/emg/Source/migrate-twenty-to-frappe/pol_crm/pol_crm/messaging/kavenegar.py#L69-L72)
- **شرح باگ:** در `offer_engine.py` توکن‌های پترن به صورت `template_tokens={"code": coupon_code, "percent": ...}` پاس داده می‌شوند. در `kavenegar.py`، مقادیر عینا در `payload` قرار می‌گیرند.  
  وب‌سرویس اعتبارسنجی کاوه‌نگار (`verify/lookup.json`) طبق مستندات رسمی تنها پارامترهای ثابت با نام‌های `token`, `token2`, `token3`, `token10`, `token20` را می‌پذیرد. ارسال کلیدهای دلخواه مثل `code` و `percent` منجر به خطای HTTP 412 کاوه‌نگار (`ارسال توکن الزامی است`) و عدم تحویل پیامک خدماتی به مشتری می‌شود.

---

### ۱.۶. شکست ایجاد کوپن بومی در ERPNext (`create_erpnext_coupon`)
- **مسیر فایل و شماره خطوط:** [`pol_crm/pol_crm/rfm/offer_engine.py#L95-L108`](file:///home/emg/Source/migrate-twenty-to-frappe/pol_crm/pol_crm/rfm/offer_engine.py#L95-L108)
- **شرح باگ:** طبق بند ۴.۲.۱ SRS:  
  > *«ثبت مستقیم در جدول استاندارد Coupon Code با تعریف تاریخ انقضا و اتصال به Pricing Rule جهت اعمال خودکار در هنگام صدور فاکتور.»*  
  در داک‌تایپ استاندارد `Coupon Code` در ERPNext، فیلد `pricing_rule` اجباری (Mandatory Link) است. در کد فعلی هیچ قانونی برای `pricing_rule` ست یا ارجاع داده نمی‌شود. به دلیل بلوک `try ... except Exception` در خط ۱۰۶، ایجاد کوپن در محیط واقعی با شکست اعتبارسنجی مواجه شده و در سکوت کامل نادیده گرفته می‌شود.

---

## 🟠 ۲. ریسک‌های کارایی و معماری (Performance & Architectural Risks)

### ۲.۱. گلوگاه شدید در جاب شبانه محاسبه RFM (حلقه ترتیبی پایتون در برابر SQL Bulk)
- **مسیر فایل و شماره خطوط:** [`pol_crm/pol_crm/rfm/rfm_calculator.py#L302-L333`](file:///home/emg/Source/migrate-twenty-to-frappe/pol_crm/pol_crm/rfm/rfm_calculator.py#L302-L333) و [`pol_crm/pol_crm/hooks.py#L48`](file:///home/emg/Source/migrate-twenty-to-frappe/pol_crm/pol_crm/hooks.py#L48)
- **تحلیل معماری:** در `hooks.py`، رویداد زمان‌بندی‌شده روزانه به متد `nightly_recalculate_all_customers_rfm` متصل است. این متد یک حلقه `for` روی تک‌تک مشتریان اجرا می‌کند و به ازای هر مشتری ۵ الی ۷ کوئری SQL رفت‌وبرگشتی انجام می‌دهد.  
  برای پایگاه داده‌ای با ۵۰,۰۰۰ تا ۱۰۰,۰۰۰ مشتری، این حلقه حداقل ۳۰۰,۰۰۰ کوئری جداگانه صادر می‌کند که ساعت‌ها طول کشیده و ورکر Scheduler ردیس را متوقف خواهد کرد.  
  این در حالی است که متد کاملاً بهینه `recalculate_all_customers_rfm` در خط ۳۳۶ با Temporary Table و Join سرتاسری پیاده‌سازی شده، اما در زمان‌بند شبانه فراخوانی نمی‌شود! (مغایرت با بند ۶.۱ SRS: الزام به پردازش ۱۰۰,۰۰۰ رکورد زیر ۳ دقیقه).

---

### ۲.۲. ارسال همگام وب‌سرویس‌های پیامک و تلگرام در چرخه ثبت فاکتور (Blocking Webhook Calls)
- **مسیر فایل و شماره خطوط:** [`pol_crm/pol_crm/rfm/rfm_calculator.py#L271-L288`](file:///home/emg/Source/migrate-twenty-to-frappe/pol_crm/pol_crm/rfm/rfm_calculator.py#L271-L288) و [`pol_crm/pol_crm/marketing_automation/runner.py#L25-L65`](file:///home/emg/Source/migrate-twenty-to-frappe/pol_crm/pol_crm/marketing_automation/runner.py#L25-L65)
- **تحلیل معماری:** با ثبت یا لغو فاکتور در Desk توسط کاربر (`on_submit`)، متد `calculate_rfm_for_customer` اجرا شده، تغییر سگمنت تشخیص داده می‌شود و بلافاصله `trigger_segment_change_automations` و سپس `send_marketing_message` فراخوانی می‌گردد.  
  این متد با `requests.post` یک درخواست HTTP همگام (با تایم‌اوت ۱۰ الی ۱۲ ثانیه) به کاوه‌نگار یا تلگرام ارسال می‌کند. در صورت کندی اینترنت یا فیلترینگ تلگرام، فرم ثبت فاکتور کاربر در ERPNext قفل شده یا با خطای Gateway Timeout (504) مواجه می‌شود.  
  **هیچ‌گونه استفاده‌ای از `frappe.enqueue` در کل اپلیکیشن نشده است**، که این امر نقض صریح بندهای ۶.۱ و ۶.۲ سند SRS است.

---

### ۲.۳. بارگذاری کل مشتریان در حافظه RAM در موتور آفر (`daily_offer_decision_pass`)
- **مسیر فایل و شماره خطوط:** [`pol_crm/pol_crm/rfm/offer_engine.py#L213-L227`](file:///home/emg/Source/migrate-twenty-to-frappe/pol_crm/pol_crm/rfm/offer_engine.py#L213-L227)
- **تحلیل معماری:** دستور `frappe.get_all("Customer", fields=[...], filters={"disabled": 0})` کلیه مشتریان فعال را به صورت یکجا در حافظه لود می‌کند. این ساختار بدون صفحه‌بندی یا چانک‌بندی (Batching)، در مقیاس‌های ده‌ها هزار مشتری با کمبود حافظه (OOM Killer) مواجه می‌شود.

---

### ۲.۴. از دست رفتن متغیرهای قالب و الگو در پیام‌های معوقه شبانه
- **مسیر فایل و شماره خطوط:** [`pol_crm/pol_crm/messaging/policy.py#L175-L177`](file:///home/emg/Source/migrate-twenty-to-frappe/pol_crm/pol_crm/messaging/policy.py#L175-L177) و داک‌تایپ `Mkt Message Log`
- **تحلیل معماری:** هنگامی که پیامی به علت ساعات سکوت (Quiet Hours) وضعیت `POSTPONED` می‌گیرد، فقط متن خام پیام در جدول لاگ ذخیره می‌شود و فیلدهای `template_code` و `template_tokens` ثبت نمی‌گردند.  
  صبح روز بعد، این پیام به عنوان پیامک عادی ارسال می‌شود که منجر به سوختن پیام در بلک‌لیست اپراتورها خواهد شد.

---

## 🟡 ۳. نیازمندی‌های پیاده‌سازی‌نشده یا ناقص سند SRS (Missing Requirements)

| ردیف | نیازمندی در سند SRS | بند SRS | وضعیت در کد فعلی | شرح کسری و اثر تجاری |
| :---: | :--- | :---: | :---: | :--- |
| **۱** | داک‌تایپ `Mkt Subscription` | ۵.۲ (مورد ۶) | ❌ **اصلاً وجود ندارد** | در `policy.py` وجود آن با `exists` چک شده اما تعریف داک‌تایپ در اپ ایجاد نشده است. امکان مدیریت لغو عضویت کانال‌محور مشتریان وجود ندارد. |
| **۲** | فیلد شناسه تلگرام مشتری (`Telegram ID`) | ۳.۱ و ۵.۱ | ❌ **ناقص و حذف‌شده** | در داده‌های Twenty CRM ستون `Telegram ID` وجود دارد، اما اسکریپت مایگریشن آن را حذف کرده و در فیلدهای سفارشی `Customer` یا `Contact` فیلدی برای آن ایجاد نشده است. |
| **۳** | تریگرهای `FIRST_ORDER` و `BIRTHDAY` | ۴.۴.۱ | ❌ **پیاده‌سازی‌نشده** | در داک‌تایپ `Mkt Scenario` گزینه‌ها در Select وجود دارند، اما در `runner.py` هیچ متد یا زمان‌بندی برای اجرای سناریوی اولین خرید یا تبریک تولد کدنویسی نشده است. |
| **۴** | پشتیبانی دکمه‌های شیشه‌ای تلگرام (`reply_markup`) | ۴.۳.۲ | ❌ **پیاده‌سازی‌نشده** | متد `send_telegram_message` تنها متن و parse_mode ارسال می‌کند و از کیبورد شیشه‌ای پشتیبانی نمی‌کند. |
| **۵** | پاک‌سازی خودکار لاگ‌های بالای ۱۸۰ روز | ۷.۲ | ❌ **پیاده‌سازی‌نشده** | هیچ تابع زمان‌بندی دوره‌ای برای پاک‌سازی رکوردهای قدیمی `Mkt Message Log` تعریف نشده است. |
| **۶** | نقش‌های دسترسی RBAC برای `Marketing Manager` | ۶.۳ | ⚠️ **ناقص** | در هیچ‌کدام از داک‌تایپ‌های اختصاصی نقشی به نام `Marketing Manager` تعریف نشده و فقط `System Manager` دسترسی دارد. |
| **۷** | نرمال‌سازی شماره‌های تماس در پایپ‌لاین مهاجرت | ۳.۱ و ۶.۴ | ⚠️ **بسیار ناقص** | اسکریپت `prepare_frappe_imports.py` ماژول قدرتمند `phone_utils.py` را دور زده و با یک شرط ساده فقط شماره‌های `98...` را بدون حذف `+` یا پیشوند `0098` یا ارقام فارسی بررسی می‌کند. |
| **۸** | نام‌گذاری شرکت در اسکریپت داده‌های ورودی | ۳.۱ | ⚠️ **هاردکد شده** | مقدار شرکت در خطوط ۲۸۹ و ۳۱۰ اسکریپت مایگریشن به صورت ثابت `"emg"` درج شده و در بنچ‌های دیگر با خطای عدم تطابق شرکت متوقف می‌شود. |

---

## 🟢 ۴. برنامه عملیاتی و اصلاحات مشخص کد (Concrete Refactoring Steps)

### گام ۱: اصلاح فوری متد `process_postponed_messages` در پیام‌رسانی
در فایل [`pol_crm/pol_crm/messaging/policy.py`](file:///home/emg/Source/migrate-twenty-to-frappe/pol_crm/pol_crm/messaging/policy.py):
```python
# جایگزینی حلقه بازپردازش در خط 245 به بعد:
for item in postponed:
    is_tg = (item.channel == "TELEGRAM")
    res = send_marketing_message(
        customer=item.customer,
        phone=None if is_tg else item.recipient,
        telegram_chat_id=item.recipient if is_tg else None,
        text=item.message_body,
        channel=item.channel,
        category=item.category,
    )
    if res.get("status") in ["SENT", "SKIPPED", "FAILED"]:
        frappe.db.delete("Mkt Message Log", {"name": item.name})
```

### گام ۲: تفکیک فاکتورهای مرجوعی و اصلاح شرط فاکتورها در RFM
در فایل [`pol_crm/pol_crm/rfm/rfm_calculator.py`](file:///home/emg/Source/migrate-twenty-to-frappe/pol_crm/pol_crm/rfm/rfm_calculator.py):
1. در خط ۱۹۶ کوئری محاسبه تک‌مشتری را اصلاح نمایید تا مرجوعی‌ها جدا شده و سفارش‌های Draft حذف شوند:
```sql
SELECT 
    posting_date,
    grand_total,
    is_return
FROM `tabSales Invoice`
WHERE customer = %s AND docstatus = 1 AND is_return = 0
ORDER BY posting_date DESC
```
2. خالص پرداختی به صورت تفاضل مبالغ مرجوعی محاسبه شود و تعداد خریدهای معتبر فقط شامل رکوردهای غیرمرجوعی باشد.
3. در خط ۲۱۶ و ۳۹۸ شرط `docstatus != 2` برای `Sales Order` را به `docstatus = 1` تغییر دهید تا فقط سفارش‌های ثبت و تاییدشده محاسبه گردند.

### گام ۳: جایگزینی جاب شبانه کند با متد SQL Bulk
در فایل [`pol_crm/pol_crm/rfm/rfm_calculator.py#L302`](file:///home/emg/Source/migrate-twenty-to-frappe/pol_crm/pol_crm/rfm/rfm_calculator.py#L302):
```python
def nightly_recalculate_all_customers_rfm():
    """Execute high-speed SQL batching instead of slow iterative Python loop."""
    frappe.logger("pol_crm").info("Starting nightly optimized RFM recalculation...")
    result = recalculate_all_customers_rfm()
    frappe.logger("pol_crm").info(f"Nightly RFM finished: {result}")
```

### گام ۴: تبدیل ارسال پیام‌ها به صف پس‌زمینه Redis Queue (`frappe.enqueue`)
در فایل [`pol_crm/pol_crm/marketing_automation/runner.py`](file:///home/emg/Source/migrate-twenty-to-frappe/pol_crm/pol_crm/marketing_automation/runner.py) و [`pol_crm/pol_crm/rfm/offer_engine.py`](file:///home/emg/Source/migrate-twenty-to-frappe/pol_crm/pol_crm/rfm/offer_engine.py):
جایگزینی فراخوانی مستقیم `send_marketing_message` با صف ناهمگام Frappe:
```python
frappe.enqueue(
    "pol_crm.messaging.policy.send_marketing_message",
    queue="short",
    customer=customer_name,
    phone=phone,
    text=body,
    channel=sc.channel or "SMS",
    template_code=sc.template_code,
    category="marketing",
)
```

### گام ۵: اصلاح نگاشت توکن‌های کاوه‌نگار در آفر انجین
در فایل [`pol_crm/pol_crm/rfm/offer_engine.py#L156`](file:///home/emg/Source/migrate-twenty-to-frappe/pol_crm/pol_crm/rfm/offer_engine.py#L156):
```python
# نگاشت کلیدهای توکن به نام‌های استاندارد مورد پذیرش وب‌سرویس کاوه‌نگار:
template_tokens = {
    "token": coupon_code,
    "token2": str(rule.get("percentage_value")),
}
```

### گام ۶: اضافه کردن فیلد شناسه تلگرام و داک‌تایپ `Mkt Subscription`
1. فیلد `custom_telegram_chat_id` به داک‌تایپ‌های `Customer` و `Contact` در `custom_field.json` اضافه شود.
2. داک‌تایپ استاندارد `Mkt Subscription` جهت ثبت وضعیت لغو اشتراک کانال‌ها ایجاد گردد.
3. در اسکریپت `prepare_frappe_imports.py` از توابع `normalize_iranian_mobile` موجود در `pol_crm.messaging.phone_utils` استفاده شود و ستون `Telegram ID` در فیلد سفارشی مشتری ذخیره گردد.

### گام ۷: افزودن تابع زمان‌بندی هفتگی پاک‌سازی لاگ‌ها
در `policy.py` و `hooks.py`:
```python
def purge_old_message_logs():
    """Purge message logs older than 180 days (SRS 7.2)."""
    cutoff = add_days(nowdate(), -180)
    frappe.db.sql("DELETE FROM `tabMkt Message Log` WHERE creation < %s", (cutoff,))
    frappe.db.commit()
```

---

## ۵. ماتریس ارزیابی کیفیت آزمون‌ها (ADR 0001 Evaluation)

| مؤلفه ارزیابی | انطباق با ADR 0001 | وضعیت فعلی | پیشنهاد بهبود |
| :--- | :---: | :---: | :--- |
| **سرعت اجرا** | ۱۰۰٪ | ۱۱۵ آزمون در ۰.۰۶۳ ثانیه | حفظ ساختار فعلی |
| **ایزولاسیون شبکه** | ۱۰۰٪ | استفاده از `patch` روی `requests.post` | حفظ ساختار فعلی |
| **اجرای دوگانه (Dual Runner)** | ۷۵٪ | نیاز به `PYTHONPATH=pol_crm` جهت جلوگیری از خطای ایمپورت | اصلاح مسیر ایمپورت در فایل‌های تست |
| **دقت شبیه‌سازی ERPNext** | ۶۰٪ | ماک کردن ناقص فیلد `pricing_rule` در Coupon Code و توکن‌های پترن کاوه‌نگار | ارتقای Contract Testing در شبیه‌سازها |
