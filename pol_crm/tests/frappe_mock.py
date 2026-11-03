"""
Frappe Mock Framework for POL CRM Unit and Integration Tests.
Provides standalone in-memory mocking for all Frappe API calls (db, get_doc, get_all, logger, etc.)
allowing tests to run in any standard Python environment without bench or MariaDB.
"""

import sys
from datetime import datetime, date, timedelta
from unittest.mock import MagicMock


def create_frappe_utils_mock():
    """Create mock frappe.utils helper functions."""
    utils = MagicMock()

    def _nowdate():
        return datetime.now().strftime("%Y-%m-%d")

    def _now_datetime():
        return datetime.now()

    def _add_days(d, days):
        is_str = isinstance(d, str)
        if is_str:
            dt = datetime.strptime(str(d)[:10], "%Y-%m-%d")
        elif isinstance(d, datetime):
            dt = d
        elif isinstance(d, date):
            dt = datetime.combine(d, datetime.min.time())
        else:
            dt = datetime.now()
        res = dt + timedelta(days=days)
        if is_str:
            return res.strftime("%Y-%m-%d")
        return res

    def _date_diff(d1, d2):
        if isinstance(d1, str):
            d1 = datetime.strptime(str(d1)[:10], "%Y-%m-%d").date()
        elif isinstance(d1, datetime):
            d1 = d1.date()
        if isinstance(d2, str):
            d2 = datetime.strptime(str(d2)[:10], "%Y-%m-%d").date()
        elif isinstance(d2, datetime):
            d2 = d2.date()
        return (d1 - d2).days

    def _getdate(d):
        if isinstance(d, str):
            return datetime.strptime(str(d)[:10], "%Y-%m-%d").date()
        elif isinstance(d, datetime):
            return d.date()
        return d

    def _flt(v, precision=None):
        try:
            return float(v or 0)
        except (ValueError, TypeError):
            return 0.0

    def _cint(v):
        try:
            return int(v or 0)
        except (ValueError, TypeError):
            return 0

    utils.nowdate = _nowdate
    utils.now_datetime = _now_datetime
    utils.add_days = _add_days
    utils.date_diff = _date_diff
    utils.getdate = _getdate
    utils.flt = _flt
    utils.cint = _cint

    return utils


def setup_mock_frappe():
    """Ensure mock frappe and frappe.utils are registered in sys.modules."""
    if "frappe" in sys.modules and isinstance(sys.modules["frappe"], MagicMock):
        return sys.modules["frappe"]

    mock_frappe = MagicMock()
    mock_utils = create_frappe_utils_mock()

    def _whitelist(*args, **kwargs):
        def decorator(fn):
            return fn
        if len(args) == 1 and callable(args[0]):
            return args[0]
        return decorator

    mock_frappe.whitelist = _whitelist
    mock_frappe.utils = mock_utils
    mock_frappe.conf = {}
    mock_frappe.flags = MagicMock()
    mock_frappe.flags.in_test = True
    mock_frappe.enqueue = MagicMock()
    mock_frappe.db = MagicMock()
    mock_frappe.db.exists.side_effect = default_exists

    # Logger mock
    mock_logger = MagicMock()
    mock_frappe.logger.return_value = mock_logger

    sys.modules["frappe"] = mock_frappe
    sys.modules["frappe.utils"] = mock_utils

    if "pol_crm.rfm.rfm_calculator" in sys.modules:
        sys.modules["pol_crm.rfm.rfm_calculator"].frappe = mock_frappe

    return mock_frappe



def default_exists(doctype, name=None):
    if doctype == "DocType":
        return False
    return True


def reset_mock_frappe():
    """Reset all frappe mock calls, return values, and side effects."""
    mock_frappe.reset_mock()
    mock_frappe.db.reset_mock()
    mock_frappe.db.exists.side_effect = default_exists
    mock_frappe.db.get_value.side_effect = None
    mock_frappe.db.get_value.return_value = None
    mock_frappe.db.set_value.side_effect = None
    mock_frappe.db.sql.side_effect = None
    mock_frappe.db.sql.return_value = []
    mock_frappe.db.count.side_effect = None
    mock_frappe.db.count.return_value = 0
    mock_frappe.db.delete.side_effect = None
    mock_frappe.get_doc.side_effect = None
    mock_frappe.get_all.side_effect = None
    mock_frappe.get_all.return_value = []
    mock_frappe.get_single.side_effect = None
    mock_frappe.conf = {}
    mock_frappe.flags = MagicMock()
    mock_frappe.flags.in_test = True
    mock_frappe.enqueue.reset_mock()
    mock_frappe.logger.reset_mock()
    mock_frappe.logger.return_value = MagicMock()



# Initialize automatically on module import
mock_frappe = setup_mock_frappe()

