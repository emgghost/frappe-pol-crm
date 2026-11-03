"""
POL CRM - RFM Job Tracker
Provides persistent, recoverable state tracking for background RFM recalculation jobs.
Uses tabSingles and frappe.publish_realtime for resilient UI recovery after page refresh.
"""

from datetime import datetime
import json

try:
    import frappe
    from frappe.utils import now_datetime, cint
except ImportError:
    frappe = None
    now_datetime = lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cint = lambda v: int(v or 0)

JOB_DOCTYPE = "POL RFM Job Status"
STALE_JOB_TIMEOUT_SECONDS = 1800  # 30 minutes


def _get_singles_dict():
    """Retrieve all fields stored under POL RFM Job Status in tabSingles."""
    if not frappe or not hasattr(frappe, "db") or not hasattr(frappe.db, "sql"):
        return {}
    try:
        rows = frappe.db.sql(
            """
            SELECT field, value 
            FROM `tabSingles` 
            WHERE doctype = %s
            """,
            (JOB_DOCTYPE,),
            as_dict=True,
        )
        return {r["field"]: r["value"] for r in rows}
    except Exception:
        return {}


def _set_singles_value(field, value):
    """Atomically set a single field under POL RFM Job Status."""
    if not frappe or not hasattr(frappe, "db"):
        return
    try:
        str_val = "" if value is None else str(value)
        # Check if row exists
        existing = frappe.db.sql(
            """
            SELECT 1 FROM `tabSingles` 
            WHERE doctype = %s AND field = %s
            """,
            (JOB_DOCTYPE, field),
        )
        if existing:
            frappe.db.sql(
                """
                UPDATE `tabSingles`
                SET value = %s
                WHERE doctype = %s AND field = %s
                """,
                (str_val, JOB_DOCTYPE, field),
            )
        else:
            frappe.db.sql(
                """
                INSERT INTO `tabSingles` (doctype, field, value)
                VALUES (%s, %s, %s)
                """,
                (JOB_DOCTYPE, field, str_val),
            )
        frappe.db.commit()
    except Exception as e:
        if hasattr(frappe, "logger"):
            frappe.logger("pol_crm").warning(f"Could not persist job field {field}: {e}")


def get_job_status():
    """Get the persistent state of the latest RFM calculation job."""
    data = _get_singles_dict()
    status = data.get("status") or "IDLE"

    # Stale check
    if status in ["QUEUED", "IN_PROGRESS"]:
        started = data.get("started_at")
        if started:
            try:
                start_dt = datetime.strptime(str(started)[:19], "%Y-%m-%d %H:%M:%S")
                if (datetime.now() - start_dt).total_seconds() > STALE_JOB_TIMEOUT_SECONDS:
                    status = "FAILED"
                    data["error_message"] = "عملیات به دلیل طولانی شدن زمان اجرا منقضی شد (Time-out)"
                    _set_singles_value("status", "FAILED")
                    _set_singles_value("error_message", data["error_message"])
            except Exception:
                pass

    return {
        "job_id": data.get("job_id"),
        "status": status,
        "scope": data.get("scope") or "ALL",
        "progress_percent": cint(data.get("progress_percent") or 0),
        "total_records": cint(data.get("total_records") or 0),
        "processed_records": cint(data.get("processed_records") or 0),
        "scored_customers": cint(data.get("scored_customers") or 0),
        "error_message": data.get("error_message") or None,
        "started_at": data.get("started_at"),
        "completed_at": data.get("completed_at"),
        "initiated_by": data.get("initiated_by"),
    }


def acquire_job_lock(job_id, scope, initiated_by, total_records=0):
    """
    Attempt to acquire the execution lock.
    Returns (acquired: bool, status_dict: dict).
    Prevents accidental duplicate executions.
    """
    current = get_job_status()
    if current["status"] in ["QUEUED", "IN_PROGRESS"]:
        return False, current

    now = str(now_datetime())
    _set_singles_value("job_id", job_id)
    _set_singles_value("status", "IN_PROGRESS")
    _set_singles_value("scope", scope)
    _set_singles_value("progress_percent", 0)
    _set_singles_value("total_records", total_records)
    _set_singles_value("processed_records", 0)
    _set_singles_value("scored_customers", 0)
    _set_singles_value("error_message", "")
    _set_singles_value("started_at", now)
    _set_singles_value("completed_at", "")
    _set_singles_value("initiated_by", initiated_by)

    status_dict = get_job_status()
    _publish_event("pol_rfm_job_status", status_dict)
    return True, status_dict


def update_job_progress(job_id, progress_percent, processed_records, scored_customers=None):
    """Update ongoing progress for the active job."""
    _set_singles_value("progress_percent", progress_percent)
    _set_singles_value("processed_records", processed_records)
    if scored_customers is not None:
        _set_singles_value("scored_customers", scored_customers)

    status_dict = get_job_status()
    _publish_event("pol_rfm_job_status", status_dict)
    return status_dict


def complete_job(job_id, status="SUCCESS", scored_customers=0, total_customers=0, error_message=None):
    """Mark the job as completed or failed."""
    now = str(now_datetime())
    _set_singles_value("status", status)
    _set_singles_value("progress_percent", 100 if status == "SUCCESS" else cint(_get_singles_dict().get("progress_percent") or 0))
    _set_singles_value("completed_at", now)
    _set_singles_value("scored_customers", scored_customers)
    if total_customers:
        _set_singles_value("total_records", total_customers)
    if error_message:
        _set_singles_value("error_message", str(error_message))

    status_dict = get_job_status()
    _publish_event("pol_rfm_job_status", status_dict)
    return status_dict


def clear_job_lock():
    """Reset the lock to IDLE (for testing or emergency administrative reset)."""
    _set_singles_value("status", "IDLE")
    _set_singles_value("error_message", "")
    return get_job_status()


def _publish_event(event_name, data):
    """Broadcast realtime status update over websocket if frappe is available."""
    if frappe and hasattr(frappe, "publish_realtime"):
        try:
            frappe.publish_realtime(
                event=event_name,
                message=data,
                user=data.get("initiated_by"),
            )
        except Exception:
            pass
