# POL CRM for Frappe Framework & ERPNext

[![CI](https://github.com/emgghost/frappe-pol-crm/actions/workflows/ci.yml/badge.svg)](https://github.com/emgghost/frappe-pol-crm/actions/workflows/ci.yml)
[![Frappe Version](https://img.shields.io/badge/Frappe-v15%20%7C%20v16-blue.svg)](https://frappeframework.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](license.txt)
[![Tests Passing](https://img.shields.io/badge/Tests-139%20passed-brightgreen.svg)](pol_crm/tests/)

**POL CRM** is an enterprise-grade Frappe custom application providing RFM Customer Segmentation, Smart Loyalty Discount Offers, Multi-Channel Iranian Messaging (Kavenegar SMS & Telegram Bot) with strict Quiet-Hours & Frequency Policy, and Trigger-Based Marketing Automation.

---

## 🌟 Key Capabilities

### 1. RFM Segmentation Engine (`rfm` module)
- **Mathematical Scoring (1–5):** Calculates Recency ($R$), Frequency ($F$), and Monetary ($M$) scores based on submitted `Sales Invoice` and `Sales Order` records. Returns and credit notes are automatically deducted.
- **11 Lifecycle Segments:** Deterministic segment mapping (*Champions*, *Loyal*, *Potential Loyalist*, *New Customers*, *Promising*, *Need Attention*, *About to Sleep*, *At Risk*, *Can't Lose*, *Hibernating*, *Lost*).
- **High-Speed Bulk & Nightly Recalculation:** High-performance SQL set operations executed via real-time invoice submit/cancel hooks, listview bulk actions, and automated nightly scheduler jobs.
- **Resilient Background Queue & Lock:** Prevents race conditions during massive bulk runs using single-instance concurrency locking (`tabSingles` tracking) with real-time progress recovery.
- **Customer 360 UX:** Modern UI badges and dedicated **Loyalty & RFM** tab inside Customer forms, with quick recalculate and offer action buttons.

### 2. Smart Loyalty Offer Engine (`rfm` module)
- **Algorithmic Coupon Generation:** Issues dynamic single-use discount coupons (`POL-XXXXXX`) using ERPNext `Coupon Code` linked to automated `Pricing Rule` records.
- **Targeted Incentive Rules:** Second-order conversion incentives (`SECOND_ORDER`), retention offers for `AT_RISK` and `CANT_LOSE`, and upgrade rewards for `POTENTIAL_LOYALIST`.
- **Anti-Fatigue Guardrails:** Cooldown windows (`cooldown_days`) and lifetime grant limits (`once_per_lifetime`) preventing spam and excessive discounting.

### 3. Multi-Channel Messaging & Localized Policy Engine (`messaging` module)
- **Iranian SMS Gateway (Kavenegar / FarazSMS):** Template / pattern dispatch (`خدماتی / پترن`) with phone number E.164 normalization.
- **Telegram Bot Integration:** Bot relay and proxy support with dedicated test mode redirection.
- **Quiet Hours Enforcement (ساعات سکوت شبانه):** Strict timezone-aware restriction (Asia/Tehran) postponing non-urgent marketing dispatches during night hours (e.g. 21:00 to 09:00).
- **Frequency Capping (سقف ارسال):** Enforces configurable daily/weekly message limits per customer with bypass for high-priority transactional messages.
- **Postponed Message Queue:** Automatic hourly flush of postponed messages when quiet hours expire (`process_postponed_messages`).
- **Consent & Compliance:** Enforces global and channel-specific opt-out (`custom_mkt_opted_out_all`, `custom_mkt_sms_opted_out`).

### 4. Marketing Automation Scenarios (`marketing_automation` module)
- **Event-Driven Scenarios:** Triggers on customer segment changes, inactivity thresholds, first purchases, and birthdays.
- **Dynamic Variable Replacement:** Supports Jinja templating with customer, invoice, and coupon code variables.
- **Granular Role Permissions:** Configured for `Marketing Manager`, `Sales Manager`, and `Sales User` roles.

---

## 🏗 App Architecture

```text
frappe-pol-crm/
├── .github/workflows/ci.yml       # GitHub Actions CI matrix test runner
├── docs/                          # Comprehensive technical specifications & reports
│   ├── QA_TEST_SPECIFICATION.md
│   ├── SRS_AUDIT_REPORT.md
│   ├── SYSTEM_REQUIREMENTS_SPECIFICATION.md
│   └── adr/
│       └── 0001-standalone-frappe-test-mock-architecture.md
├── pol_crm/                       # Frappe Python package
│   ├── fixtures/
│   │   └── custom_field.json      # Custom field fixtures (Customer, Contact, Deal)
│   ├── marketing_automation/      # Scenario runner & Mkt Scenario DocType
│   ├── messaging/                 # Kavenegar, Telegram, Policy & Message Log
│   ├── public/                    # Desk assets (customer_form.js, customer_list.js, logo.svg)
│   ├── rfm/                       # RFM calculator, Offer engine, Job tracker & Dashboards
│   ├── tests/                     # 139 automated tests with standalone Frappe mock
│   ├── hooks.py                   # Standard Frappe hooks configuration
│   ├── modules.txt                # Registered modules
│   └── patches.txt                # Database patches
├── pyproject.toml                 # Flit core build configuration & metadata
├── requirements.txt               # Python package dependencies
├── license.txt                    # MIT License
└── README.md
```

---

## 🚀 Installation

### 1. Fetch the App
Run inside your Frappe Bench directory:
```bash
bench get-app https://github.com/emgghost/frappe-pol-crm.git
```

### 2. Install onto Site
```bash
bench --site <site-name> install-app pol_crm
```

### 3. Run Migrations & Import Fixtures
```bash
bench --site <site-name> migrate
```

---

## 🧪 Automated Testing

POL CRM includes an isolated in-memory test suite that validates all 139 business logic specifications in **~0.1 seconds** without needing a running database instance.

To run the unit tests:
```bash
python3 -m unittest discover -s pol_crm/tests
```
or with `pytest`:
```bash
pytest pol_crm/tests
```

### Test Matrix Summary
- **RFM & Phone Normalization:** 12 tests
- **Messaging Policy & Quiet Hours:** 15 tests
- **Offer Decision Engine:** 12 tests
- **Messaging Gateway Adapters:** 15 tests
- **Marketing Automation Runner:** 70+ tests
- **Security, Job Concurrency & Role Permissions:** 15 tests
- **Total:** 139 / 139 tests passed (0 failures, 0 errors).

---

## 📄 License

This project is licensed under the [MIT License](license.txt) - see the file for details.
