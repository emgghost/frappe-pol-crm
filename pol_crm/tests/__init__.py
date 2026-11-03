"""
POL CRM QA Test Suite Initialization.
Registers the standalone Frappe mock environment before running test cases.
"""

from pol_crm.tests.frappe_mock import setup_mock_frappe

setup_mock_frappe()
