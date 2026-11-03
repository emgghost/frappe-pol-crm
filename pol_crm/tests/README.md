# سند نیازمندی‌های تست و معیارهای پذیرش دپارتمان QA (POL CRM)

این مستند راهنمای دپارتمان تضمین کیفیت (QA) برای پیاده‌سازی و اجرای آزمون‌های خودکار کل پروژه POL CRM است.
نسخه تفصیلی و معماری این سند در `crm-docs/QA_TEST_SPECIFICATION.md` و ایشوهای گیت‌هاب (شماره‌های ۱ تا ۶) درج شده است.

## سرفصل داستان‌های کاربری و فایل‌های آزمون:
1. **Story 1 (Issue #2):** آزمون‌های RFM و چرخه حیات مشتری (`pol_crm/tests/test_rfm_calculator.py`)
2. **Story 2 (Issue #3):** آزمون‌های لایه خط‌مشی پیام‌رسانی و صف معوق (`pol_crm/tests/test_messaging_policy.py`)
3. **Story 3 (Issue #4):** آزمون‌های موتور آفر و تخفیف‌ها (`pol_crm/tests/test_offer_engine.py`)
4. **Story 4 (Issue #5):** آزمون‌های آداپتورهای کاوه‌نگار و تلگرام (`pol_crm/tests/test_messaging_adapters.py`)
5. **Story 5 (Issue #6):** آزمون‌های سناریوهای اتوماسیون و قالب‌ساز Jinja2 (`pol_crm/tests/test_automation_runner.py`)
6. **اعتبارسنجی شماره‌های تماس:** آزمون‌های نرمال‌سازی شماره‌های ایران (`pol_crm/tests/test_rfm_and_phone.py`)
7. **ایزولاسیون و ماک Frappe:** شبیه‌ساز ماک مستقل فریم‌ورک Frappe و دیتابیس (`pol_crm/tests/frappe_mock.py`)

## نحوه اجرای آزمون‌ها

آزمون‌ها ۱۰۰٪ ایزوله و بدون نیاز به نصب بنچ یا اتصال به دیتابیس MariaDB طراحی شده‌اند.

```bash
# اجرای کلیه آزمون‌ها با pytest
pytest pol_crm/tests

# اجرای کلیه آزمون‌ها با unittest
python3 -m unittest discover pol_crm/tests
```
