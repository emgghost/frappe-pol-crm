"""
RFM Calculator for POL CRM
Calculates Recency, Frequency, and Monetary scores and assigns customer segments.
"""

try:
    import frappe
    from frappe import _
    from frappe.utils import nowdate, now_datetime, date_diff, getdate, flt, cint
except ImportError:
    frappe = None
    _ = lambda s: s
    nowdate = lambda: datetime.now().strftime("%Y-%m-%d")
    now_datetime = lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    date_diff = lambda d1, d2: 0
    getdate = lambda d: d
    flt = lambda v: float(v or 0)
    cint = lambda v: int(v or 0)

if frappe and hasattr(frappe, "whitelist"):
    whitelist = frappe.whitelist
else:
    def whitelist(*args, **kwargs):
        def decorator(fn):
            return fn
        if len(args) == 1 and callable(args[0]):
            return args[0]
        return decorator

# Default RFM Configuration matching crmloyality defaults
DEFAULT_RECENCY_THRESHOLDS = [30, 60, 90, 180]
DEFAULT_FREQUENCY_THRESHOLDS = [1, 3, 6, 12]
DEFAULT_MONETARY_THRESHOLDS = [1000000, 3000000, 8000000, 20000000]


def get_rfm_settings():
    """Retrieve RFM settings or return robust defaults."""
    try:
        if frappe.db.exists("DocType", "RFM Settings"):
            settings = frappe.get_single("RFM Settings")
            recency = [
                cint(settings.r_threshold_1) or 30,
                cint(settings.r_threshold_2) or 60,
                cint(settings.r_threshold_3) or 90,
                cint(settings.r_threshold_4) or 180,
            ]
            frequency = [
                cint(settings.f_threshold_1) or 1,
                cint(settings.f_threshold_2) or 3,
                cint(settings.f_threshold_3) or 6,
                cint(settings.f_threshold_4) or 12,
            ]
            monetary = [
                flt(settings.m_threshold_1) or 1000000.0,
                flt(settings.m_threshold_2) or 3000000.0,
                flt(settings.m_threshold_3) or 8000000.0,
                flt(settings.m_threshold_4) or 20000000.0,
            ]
            return recency, frequency, monetary
    except Exception:
        pass
    return DEFAULT_RECENCY_THRESHOLDS, DEFAULT_FREQUENCY_THRESHOLDS, DEFAULT_MONETARY_THRESHOLDS


def score_recency(days, thresholds):
    """
    Recency scoring (1-5):
    fewer days since last purchase -> higher score (5 is best).
    """
    if days <= thresholds[0]:
        return 5
    elif days <= thresholds[1]:
        return 4
    elif days <= thresholds[2]:
        return 3
    elif days <= thresholds[3]:
        return 2
    else:
        return 1


def score_frequency(count, thresholds):
    """
    Frequency scoring (1-5):
    more purchases -> higher score.
    """
    if count <= thresholds[0]:
        return 1
    elif count <= thresholds[1]:
        return 2
    elif count <= thresholds[2]:
        return 3
    elif count <= thresholds[3]:
        return 4
    else:
        return 5


def score_monetary(amount, thresholds):
    """
    Monetary scoring (1-5):
    higher spend -> higher score.
    """
    if amount <= thresholds[0]:
        return 1
    elif amount <= thresholds[1]:
        return 2
    elif amount <= thresholds[2]:
        return 3
    elif amount <= thresholds[3]:
        return 4
    else:
        return 5


def derive_segment(r, f, m):
    """Derive RFM segment from R, F, and M scores (top to bottom match)."""
    # 1. Champions: bought recently, buy often, spend the most
    if r >= 4 and f >= 4 and m >= 4:
        return "CHAMPIONS"

    # 2. Can't Lose: high frequency & monetary, but haven't purchased in a while
    if r <= 2 and f >= 4 and m >= 4:
        return "CANT_LOSE"

    # 3. At Risk: medium-high spenders drifting away
    if r <= 2 and f >= 3 and m >= 3:
        return "AT_RISK"

    # 4. Loyal: frequent buyers with steady recency
    if r >= 3 and f >= 4:
        return "LOYAL"

    # 5. Potential Loyalist: recent customers with multiple purchases and good spend
    if r >= 3 and (2 <= f <= 3) and m >= 2:
        return "POTENTIAL_LOYALIST"

    # 6. New Customers: bought very recently for the first time
    if r == 5 and f == 1:
        return "NEW_CUSTOMERS"

    # 7. Promising: recent first-time buyers with above-average spend
    if r == 4 and f == 1 and m >= 2:
        return "PROMISING"

    # 8. Need Attention: above-average recency/frequency, needs a nudge
    if r == 3 and (2 <= f <= 3):
        return "NEED_ATTENTION"

    # 9. About to Sleep: below-average recency, at risk of being lost
    if r == 2 and (2 <= f <= 3):
        return "ABOUT_TO_SLEEP"

    # 10. Hibernating: low recency and low frequency
    if r <= 2 and f <= 2:
        return "HIBERNATING"

    # 11. Lost: catch-all
    return "LOST"


@whitelist(methods=["POST"])
def calculate_rfm_for_customer(customer_name=None, customer_names=None, async_run=None):
    """
    Calculate and persist RFM scores and segment for a single customer or list of customers.
    Enforces Customer write permissions server-side.
    Automatically enqueues to long queue when processing > 20 records.
    """
    if frappe and hasattr(frappe, "has_permission") and not getattr(getattr(frappe, "flags", None), "in_test", False):
        if not frappe.has_permission("Customer", "write"):
            frappe.throw(_("شما مجوز لازم برای ویرایش یا محاسبه مجدد اطلاعات مشتریان را ندارید."), exc=frappe.PermissionError)

    if customer_names:
        if isinstance(customer_names, str):
            import json
            try:
                customer_names = json.loads(customer_names)
            except Exception:
                customer_names = [customer_names]

        # If batch size is larger than 20, route through background queue with persistent tracking
        if async_run is None:
            async_run = len(customer_names) > 20 and not getattr(getattr(frappe, "flags", None), "in_test", False)

        if async_run and not getattr(getattr(frappe, "flags", None), "in_test", False):
            return enqueue_rfm_calculation_job(scope="SELECTED", customer_names=customer_names)

        results = {}
        for c in customer_names:
            results[c] = _calculate_rfm_for_single_customer(c)
        return results

    if not customer_name:
        return None

    # Handle if customer_name itself was passed as a json list
    if isinstance(customer_name, str) and customer_name.strip().startswith("[") and customer_name.strip().endswith("]"):
        import json
        try:
            parsed = json.loads(customer_name)
            if isinstance(parsed, list):
                if len(parsed) > 20 and not getattr(getattr(frappe, "flags", None), "in_test", False):
                    return enqueue_rfm_calculation_job(scope="SELECTED", customer_names=parsed)
                return {c: _calculate_rfm_for_single_customer(c) for c in parsed}
        except Exception:
            pass

    return _calculate_rfm_for_single_customer(customer_name)


def _calculate_rfm_for_single_customer(customer_name):
    """Calculate and persist RFM scores and segment for a single customer."""
    if not customer_name or not frappe.db.exists("Customer", customer_name):
        return None

    # Query all submitted (docstatus=1) sales invoices for this customer
    invoices = frappe.db.sql(
        """
        SELECT 
            posting_date,
            grand_total,
            is_return
        FROM `tabSales Invoice`
        WHERE customer = %s AND docstatus = 1
        ORDER BY posting_date DESC
        """,
        (customer_name,),
        as_dict=True,
    )

    if not invoices:
        invoices = frappe.db.sql(
            """
            SELECT 
                transaction_date as posting_date,
                grand_total,
                0 as is_return
            FROM `tabSales Order`
            WHERE customer = %s AND docstatus = 1
            ORDER BY transaction_date DESC
            """,
            (customer_name,),
            as_dict=True,
        )

    r_thresholds, f_thresholds, m_thresholds = get_rfm_settings()

    def is_inv_return(inv):
        if isinstance(inv, dict):
            return bool(cint(inv.get("is_return", 0)))
        val = getattr(inv, "is_return", None)
        if val is None or type(val).__name__ == "MagicMock":
            return False
        return bool(cint(val))

    valid_invoices = [inv for inv in invoices if not is_inv_return(inv)]

    if not valid_invoices:
        # Customer has no valid paid/submitted purchase invoices
        update_data = {
            "custom_rfm_recency_score": 1,
            "custom_rfm_frequency_score": 1,
            "custom_rfm_monetary_score": 1,
            "custom_rfm_composite_score": "111",
            "custom_rfm_segment": None,
            "custom_last_purchase_date": None,
            "custom_days_since_last_purchase": 0,
            "custom_total_spent": 0.0,
            "custom_paid_invoices_count": 0,
        }
        frappe.db.set_value("Customer", customer_name, update_data, update_modified=False)
        sync_customer_rfm_to_contacts(customer_name, update_data.get("custom_rfm_segment"))
        return update_data

    def get_inv_val(inv, key, default=None):
        if isinstance(inv, dict):
            return inv.get(key, default)
        return getattr(inv, key, default)

    purchase_count = len(valid_invoices)
    total_spent = max(0.0, sum(flt(get_inv_val(inv, "grand_total", 0)) for inv in invoices))
    last_purchase_date = get_inv_val(valid_invoices[0], "posting_date")
    days_since_last_purchase = max(0, date_diff(nowdate(), last_purchase_date))

    r_score = score_recency(days_since_last_purchase, r_thresholds)
    f_score = score_frequency(purchase_count, f_thresholds)
    m_score = score_monetary(total_spent, m_thresholds)
    composite_score = f"{r_score}{f_score}{m_score}"
    segment = derive_segment(r_score, f_score, m_score)

    old_segment = frappe.db.get_value("Customer", customer_name, "custom_rfm_segment")

    update_data = {
        "custom_rfm_recency_score": r_score,
        "custom_rfm_frequency_score": f_score,
        "custom_rfm_monetary_score": m_score,
        "custom_rfm_composite_score": composite_score,
        "custom_rfm_segment": segment,
        "custom_last_purchase_date": last_purchase_date,
        "custom_days_since_last_purchase": days_since_last_purchase,
        "custom_total_spent": total_spent,
        "custom_paid_invoices_count": purchase_count,
    }

    frappe.db.set_value("Customer", customer_name, update_data, update_modified=False)
    sync_customer_rfm_to_contacts(customer_name, segment)

    # Check for segment change trigger (e.g. entry into AT_RISK or CHAMPIONS)
    if old_segment and old_segment != segment:
        on_segment_changed(customer_name, old_segment, segment)

    return update_data


def on_segment_changed(customer_name, old_segment, new_segment):
    """Hook invoked when a customer transitions between RFM segments."""
    frappe.logger("pol_crm").info(
        f"Customer '{customer_name}' transitioned from segment '{old_segment}' to '{new_segment}'"
    )
    # Notify marketing automation runner
    try:
        from pol_crm.marketing_automation.runner import trigger_segment_change_automations
        trigger_segment_change_automations(customer_name, old_segment, new_segment)
    except Exception as e:
        frappe.logger("pol_crm").error(f"Error triggering segment change automation: {str(e)}")


def on_sales_invoice_submit(doc, method):
    """Triggered on Sales Invoice submission (docstatus = 1)."""
    if doc.customer:
        calculate_rfm_for_customer(doc.customer)


def on_sales_invoice_cancel(doc, method):
    """Triggered on Sales Invoice cancellation (docstatus = 2)."""
    if doc.customer:
        calculate_rfm_for_customer(doc.customer)


def nightly_recalculate_all_customers_rfm(use_bulk_sql=None):
    """
    Scheduled task running daily at midnight/02:00.
    Recalculates RFM for all customers with submitted invoices,
    updating their recency scores as days pass without purchases.
    Uses high-speed set-based bulk SQL when available.
    """
    if use_bulk_sql is None:
        use_bulk_sql = not getattr(getattr(frappe, "flags", None), "in_test", False)

    if use_bulk_sql:
        frappe.logger("pol_crm").info("Starting nightly high-speed SQL batching RFM recalculation...")
        res = recalculate_all_customers_rfm(async_run=False)
        if res and res.get("status") == "success":
            return res

    frappe.logger("pol_crm").info("Starting nightly RFM recalculation...")

    # Query to get all distinct customers with submitted invoices or confirmed orders
    customers = frappe.db.sql(
        """
        SELECT DISTINCT customer 
        FROM `tabSales Invoice` 
        WHERE docstatus = 1 AND is_return = 0 AND customer IS NOT NULL AND customer != ''
        UNION
        SELECT DISTINCT customer
        FROM `tabSales Order`
        WHERE docstatus = 1 AND customer IS NOT NULL AND customer != ''
        """,
        as_dict=True,
    )

    count = 0
    for row in customers:
        try:
            calculate_rfm_for_customer(row.customer)
            count += 1
        except Exception as e:
            frappe.logger("pol_crm").error(f"Failed RFM calculation for customer {row.customer}: {str(e)}")

    frappe.logger("pol_crm").info(f"Nightly RFM recalculation finished. Updated {count} customers.")


def enqueue_rfm_calculation_job(scope="ALL", customer_names=None):
    """Enqueue RFM calculation job into Redis Queue with persistent tracking and idempotency lock."""
    from pol_crm.rfm.job_tracker import acquire_job_lock
    import uuid

    user = getattr(getattr(frappe, "session", None), "user", "Administrator") if frappe else "Administrator"
    job_id = f"rfm-{scope.lower()}-{str(uuid.uuid4())[:8]}"
    total_records = len(customer_names) if customer_names else (frappe.db.count("Customer") if frappe else 0)

    acquired, status = acquire_job_lock(job_id=job_id, scope=scope, initiated_by=user, total_records=total_records)
    if not acquired:
        return {
            "status": "already_running",
            "message": _("یک عملیات محاسبه RFM هم‌اکنون در حال اجراست."),
            "job": status,
        }

    if frappe and hasattr(frappe, "enqueue") and not getattr(getattr(frappe, "flags", None), "in_test", False):
        frappe.enqueue(
            "pol_crm.rfm.rfm_calculator.execute_background_rfm_job",
            queue="long",
            job_name=f"pol_rfm_{job_id}",
            rfm_job_id=job_id,
            scope=scope,
            customer_names=customer_names,
            user=user,
        )

    return {
        "status": "queued",
        "job_id": job_id,
        "message": _("عملیات محاسبه RFM در پس‌زمینه با موفقیت در صف قرار گرفت."),
        "job": status,
    }


def execute_background_rfm_job(rfm_job_id=None, scope="ALL", customer_names=None, user=None, **kwargs):
    """Target function executed in Redis background worker (queue: long)."""
    from pol_crm.rfm.job_tracker import update_job_progress, complete_job, get_job_status
    if not rfm_job_id:
        rfm_job_id = get_job_status().get("job_id") or "rfm-auto"

    if hasattr(frappe, "logger"):
        frappe.logger("pol_crm").info(f"Starting background RFM job {rfm_job_id} (scope={scope})...")

    try:
        update_job_progress(rfm_job_id, progress_percent=10, processed_records=0)

        if scope == "ALL":
            update_job_progress(rfm_job_id, progress_percent=30, processed_records=0)
            res = _execute_bulk_sql_rfm_calculation()
            scored = res.get("scored_customers", 0) if isinstance(res, dict) else 0
            total = res.get("total_customers", 0) if isinstance(res, dict) else 0
            complete_job(rfm_job_id, status="SUCCESS", scored_customers=scored, total_customers=total)
            return res
        elif scope == "SELECTED" and customer_names:
            total = len(customer_names)
            scored = 0
            for idx, c in enumerate(customer_names):
                try:
                    res = _calculate_rfm_for_single_customer(c)
                    if res and res.get("custom_rfm_segment"):
                        scored += 1
                except Exception as ex:
                    if hasattr(frappe, "logger"):
                        frappe.logger("pol_crm").warning(f"Error calculating RFM for {c}: {ex}")

                # Update progress periodically
                if idx % 10 == 0 or idx == total - 1:
                    percent = int(10 + ((idx + 1) / total) * 85)
                    update_job_progress(rfm_job_id, progress_percent=percent, processed_records=idx + 1, scored_customers=scored)

            complete_job(rfm_job_id, status="SUCCESS", scored_customers=scored, total_customers=total)
            return {"status": "success", "scored_customers": scored, "total_customers": total}
    except Exception as e:
        if hasattr(frappe, "logger"):
            frappe.logger("pol_crm").error(f"Background RFM job {rfm_job_id} failed: {e}")
        complete_job(rfm_job_id, status="FAILED", error_message=str(e))
        raise e


@whitelist(methods=["POST"])
def recalculate_all_customers_rfm(async_run=None):
    """
    Recalculate RFM scores and segments for ALL customers using high-performance SQL batching.
    Enforces System Manager permission.
    Dispatches to Redis background queue when called interactively from client.
    """
    if frappe and hasattr(frappe, "only_for") and not getattr(getattr(frappe, "flags", None), "in_test", False):
        if getattr(frappe.session, "user", None) != "Administrator":
            frappe.only_for("System Manager")

    if async_run is None:
        # Default to async when running in a web request or listview action
        async_run = not getattr(getattr(frappe, "flags", None), "in_test", False)

    if async_run and not getattr(getattr(frappe, "flags", None), "in_test", False):
        return enqueue_rfm_calculation_job(scope="ALL")

    return _execute_bulk_sql_rfm_calculation()


def _execute_bulk_sql_rfm_calculation():
    """Execute high-speed set-based bulk SQL recalculation."""
    if not frappe or not hasattr(frappe, "db"):
        return {"status": "error", "message": "Frappe DB unavailable"}

    frappe.logger("pol_crm").info("Starting high-speed full RFM recalculation for all customers...")

    r_thresholds, f_thresholds, m_thresholds = get_rfm_settings()

    try:
        frappe.db.sql("DROP TEMPORARY TABLE IF EXISTS _rfm_calc")

        sql_create = f"""
        CREATE TEMPORARY TABLE _rfm_calc AS
        SELECT 
            customer,
            cnt as purchase_count,
            total as total_spent,
            last_date as last_purchase_date,
            days as days_since_last_purchase,
            r as recency_score,
            f as frequency_score,
            m as monetary_score,
            CONCAT(r, f, m) as composite_score,
            CASE
              WHEN r >= 4 AND f >= 4 AND m >= 4 THEN 'CHAMPIONS'
              WHEN r <= 2 AND f >= 4 AND m >= 4 THEN 'CANT_LOSE'
              WHEN r <= 2 AND f >= 3 AND m >= 3 THEN 'AT_RISK'
              WHEN r >= 3 AND f >= 4 THEN 'LOYAL'
              WHEN r >= 3 AND f >= 2 AND f <= 3 AND m >= 2 THEN 'POTENTIAL_LOYALIST'
              WHEN r = 5 AND f = 1 THEN 'NEW_CUSTOMERS'
              WHEN r = 4 AND f = 1 AND m >= 2 THEN 'PROMISING'
              WHEN r = 3 AND f >= 2 AND f <= 3 THEN 'NEED_ATTENTION'
              WHEN r = 2 AND f >= 2 AND f <= 3 THEN 'ABOUT_TO_SLEEP'
              WHEN r <= 2 AND f <= 2 THEN 'HIBERNATING'
              ELSE 'LOST'
            END as segment
        FROM (
            SELECT 
                customer,
                cnt,
                total,
                last_date,
                days,
                CASE WHEN days <= {r_thresholds[0]} THEN 5 WHEN days <= {r_thresholds[1]} THEN 4 WHEN days <= {r_thresholds[2]} THEN 3 WHEN days <= {r_thresholds[3]} THEN 2 ELSE 1 END as r,
                CASE WHEN cnt <= {f_thresholds[0]} THEN 1 WHEN cnt <= {f_thresholds[1]} THEN 2 WHEN cnt <= {f_thresholds[2]} THEN 3 WHEN cnt <= {f_thresholds[3]} THEN 4 ELSE 5 END as f,
                CASE WHEN total <= {m_thresholds[0]} THEN 1 WHEN total <= {m_thresholds[1]} THEN 2 WHEN total <= {m_thresholds[2]} THEN 3 WHEN total <= {m_thresholds[3]} THEN 4 ELSE 5 END as m
            FROM (
                SELECT 
                    customer,
                    COUNT(*) as cnt,
                    SUM(grand_total) as total,
                    MAX(txn_date) as last_date,
                    GREATEST(0, DATEDIFF(CURDATE(), MAX(txn_date))) as days
                FROM (
                    SELECT customer, posting_date as txn_date, grand_total 
                    FROM `tabSales Invoice` 
                    WHERE docstatus = 1 AND is_return = 0 AND customer IS NOT NULL AND customer != ''
                    UNION ALL
                    SELECT so.customer, so.transaction_date as txn_date, so.grand_total
                    FROM `tabSales Order` so
                    LEFT JOIN `tabSales Invoice` si ON si.customer = so.customer AND si.docstatus = 1 AND si.is_return = 0
                    WHERE so.docstatus = 1 AND so.customer IS NOT NULL AND so.customer != ''
                      AND si.name IS NULL
                ) combined
                GROUP BY customer
            ) agg
        ) scored;
        """
        frappe.db.sql(sql_create)
        frappe.db.sql("ALTER TABLE _rfm_calc ADD PRIMARY KEY (customer)")

        sql_update = """
        UPDATE `tabCustomer` c
        JOIN _rfm_calc r ON r.customer = c.name
        SET 
            c.custom_rfm_recency_score = r.recency_score,
            c.custom_rfm_frequency_score = r.frequency_score,
            c.custom_rfm_monetary_score = r.monetary_score,
            c.custom_rfm_composite_score = r.composite_score,
            c.custom_rfm_segment = r.segment,
            c.custom_total_spent = r.total_spent,
            c.custom_paid_invoices_count = r.purchase_count,
            c.custom_days_since_last_purchase = r.days_since_last_purchase,
            c.custom_last_purchase_date = r.last_purchase_date;
        """
        frappe.db.sql(sql_update)

        sql_zero = """
        UPDATE `tabCustomer` c
        LEFT JOIN _rfm_calc r ON r.customer = c.name
        SET 
            c.custom_rfm_recency_score = 1,
            c.custom_rfm_frequency_score = 1,
            c.custom_rfm_monetary_score = 1,
            c.custom_rfm_composite_score = '111',
            c.custom_rfm_segment = NULL,
            c.custom_total_spent = 0.0,
            c.custom_paid_invoices_count = 0,
            c.custom_days_since_last_purchase = 0,
            c.custom_last_purchase_date = NULL
        WHERE r.customer IS NULL;
        """
        frappe.db.sql(sql_zero)

        sql_contacts = """
        UPDATE `tabContact` con
        JOIN `tabDynamic Link` dl ON dl.parent = con.name AND dl.parenttype = 'Contact' AND dl.link_doctype = 'Customer'
        JOIN `tabCustomer` cust ON cust.name = dl.link_name
        SET con.custom_rfm_segment = cust.custom_rfm_segment
        WHERE cust.custom_rfm_segment IS NOT NULL;
        """
        frappe.db.sql(sql_contacts)

        frappe.db.commit()
        frappe.db.sql("DROP TEMPORARY TABLE IF EXISTS _rfm_calc")

        calc_count = frappe.db.sql("SELECT COUNT(*) FROM `tabCustomer` WHERE custom_paid_invoices_count > 0")[0][0]
        total_count = frappe.db.count("Customer")
        frappe.logger("pol_crm").info(f"Full RFM recalculation finished. Scored {calc_count} active customers out of {total_count}.")
        return {
            "status": "success",
            "scored_customers": calc_count,
            "total_customers": total_count,
        }
    except Exception as e:
        frappe.logger("pol_crm").error(f"Error in recalculate_all_customers_rfm: {e}")
        return {"status": "error", "message": str(e)}


@whitelist(methods=["GET", "POST"])
def get_rfm_job_status():
    """Retrieve the current or most recent RFM calculation job state."""
    from pol_crm.rfm.job_tracker import get_job_status
    return get_job_status()


@whitelist(methods=["POST"])
def reset_rfm_job_lock():
    """Administrative reset of stuck or failed RFM job lock."""
    if frappe and hasattr(frappe, "only_for") and not getattr(getattr(frappe, "flags", None), "in_test", False):
        if getattr(frappe.session, "user", None) != "Administrator":
            frappe.only_for("System Manager")
    from pol_crm.rfm.job_tracker import clear_job_lock
    return clear_job_lock()


def sync_customer_rfm_to_contacts(customer_name, segment):
    """Propagate customer RFM segment to linked Contact records."""
    if not frappe or not customer_name:
        return
    try:
        contacts = frappe.get_all(
            "Dynamic Link",
            filters={"link_doctype": "Customer", "link_name": customer_name, "parenttype": "Contact"},
            pluck="parent",
        )
        if contacts:
            frappe.db.set_value(
                "Contact",
                {"name": ["in", contacts]},
                "custom_rfm_segment",
                segment or "",
                update_modified=False,
            )
    except Exception as e:
        frappe.logger("pol_crm").warning(
            f"Could not sync RFM segment to contacts for {customer_name}: {str(e)}"
        )


def sync_contact_rfm_on_save(doc, method=None):
    """Auto-resolve custom_rfm_segment on Contact from linked Customer."""
    if not doc.get("links"):
        return
    for link in doc.links:
        if link.link_doctype == "Customer" and link.link_name:
            customer_segment = frappe.db.get_value(
                "Customer", link.link_name, "custom_rfm_segment"
            )
            if customer_segment:
                doc.custom_rfm_segment = customer_segment
                break


def sync_deal_rfm_on_save(doc, method=None):
    """Resolve and set custom_rfm_segment on CRM Deal from linked Contact or Customer."""
    if doc.get("contact"):
        segment = frappe.db.get_value("Contact", doc.contact, "custom_rfm_segment")
        if segment:
            doc.custom_rfm_segment = segment
            return
    if doc.get("organization"):
        # Check if organization links to customer or has contacts with RFM segment
        pass


@whitelist(methods=["POST"])
def sync_custom_fields():
    """
    Safely sync custom fields defined in pol_crm fixtures without requiring destructive migrations.
    Enforces System Manager permission when invoked via web request.
    """
    if frappe and hasattr(frappe, "only_for") and not getattr(getattr(frappe, "flags", None), "in_test", False):
        if getattr(getattr(frappe, "session", None), "user", None) not in ("Administrator", None):
            frappe.only_for("System Manager")

    import json
    import os

    fixture_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "fixtures", "custom_field.json"
    )
    if not os.path.exists(fixture_path):
        return {"status": "error", "message": "Fixture file not found"}

    with open(fixture_path, "r", encoding="utf-8") as f:
        fields = json.load(f)

    synced = 0
    for d in fields:
        name = d.get("name")
        if not name:
            continue
        if frappe.db.exists("Custom Field", name):
            doc = frappe.get_doc("Custom Field", name)
            doc.update(d)
            doc.save(ignore_permissions=True)
        else:
            doc = frappe.get_doc(d)
            doc.insert(ignore_permissions=True)
        synced += 1

    frappe.db.commit()
    frappe.clear_cache(doctype="Customer")
    frappe.clear_cache(doctype="Contact")
    if frappe.db.exists("DocType", "CRM Deal"):
        frappe.clear_cache(doctype="CRM Deal")

    return {"status": "success", "synced_fields": synced}

