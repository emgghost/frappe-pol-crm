app_name = "pol_crm"
app_title = "POL CRM"
app_publisher = "POL CRM Team"
app_description = "Loyalty, RFM Segmentation, and Marketing Automation for Frappe/ERPNext"
app_email = "info@polcrm.ir"
app_license = "mit"

# Apps Screen (Frappe v15 / v16 Apps Page & App Switcher)
# --------------------------------------------------------
add_to_apps_screen = [
    {
        "name": "pol_crm",
        "logo": "/assets/pol_crm/images/logo.svg",
        "title": "POL CRM",
        "route": "/app/pol-crm",
    }
]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/pol_crm/css/pol_crm.css"
# app_include_js = "/assets/pol_crm/js/pol_crm.js"

# Document Events
# ---------------
# Hook on document methods and events

doc_events = {
    "Sales Invoice": {
        "on_submit": "pol_crm.rfm.rfm_calculator.on_sales_invoice_submit",
        "on_cancel": "pol_crm.rfm.rfm_calculator.on_sales_invoice_cancel",
    },
    "Sales Order": {
        "on_submit": "pol_crm.rfm.rfm_calculator.on_sales_invoice_submit",
        "on_cancel": "pol_crm.rfm.rfm_calculator.on_sales_invoice_cancel",
    },
    "Contact": {
        "before_save": "pol_crm.rfm.rfm_calculator.sync_contact_rfm_on_save",
    },
    "CRM Deal": {
        "before_save": "pol_crm.rfm.rfm_calculator.sync_deal_rfm_on_save",
    },
}

override_doctype_dashboards = {
    "Customer": "pol_crm.rfm.customer_dashboard.get_dashboard_for_customer",
}

doctype_list_js = {
    "Customer": "public/js/customer_list.js",
}

doctype_js = {
    "Customer": "public/js/customer_form.js",
}

# Scheduled Tasks
# ---------------
scheduler_events = {
    "daily": [
        "pol_crm.rfm.rfm_calculator.nightly_recalculate_all_customers_rfm",
        "pol_crm.rfm.offer_engine.daily_offer_decision_pass",
        "pol_crm.marketing_automation.runner.daily_automation_scan",
    ],
    "hourly": [
        "pol_crm.messaging.policy.process_postponed_messages",
    ],
}

# Fixtures
# --------
fixtures = [
    {
        "dt": "Custom Field",
        "filters": [
            [
                "name",
                "in",
                [
                    "Customer-custom_loyalty_rfm_tab",
                    "Customer-custom_rfm_section",
                    "Customer-custom_rfm_recency_score",
                    "Customer-custom_rfm_frequency_score",
                    "Customer-custom_rfm_monetary_score",
                    "Customer-custom_rfm_composite_score",
                    "Customer-custom_rfm_segment",
                    "Customer-custom_last_purchase_date",
                    "Customer-custom_days_since_last_purchase",
                    "Customer-custom_total_spent",
                    "Customer-custom_paid_invoices_count",
                    "Customer-custom_communications_tab",
                    "Customer-custom_marketing_section",
                    "Customer-custom_mkt_opted_out_all",
                    "Customer-custom_mkt_sms_opted_out",
                    "Customer-custom_mkt_preferred_channel",
                    "Customer-custom_telegram_chat_id",
                    "Contact-custom_rfm_segment",
                    "Contact-custom_telegram_chat_id",
                    "CRM Deal-custom_rfm_segment",
                ],
            ]
        ],
    }
]

after_migrate = [
    "pol_crm.rfm.crm_views.setup_standard_crm_views",
]
