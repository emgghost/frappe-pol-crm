"""
POL CRM QA Test Suite Initialization.
Registers the standalone Frappe mock environment before running test cases.

Only when Frappe itself is not loaded yet. Under bench it already is, and replacing it
here would turn frappe into a mock for every other app in the same test run.
"""

import sys

if "frappe" not in sys.modules:
    from pol_crm.tests.frappe_mock import setup_mock_frappe

    setup_mock_frappe()
