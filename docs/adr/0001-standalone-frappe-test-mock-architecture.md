# ADR 0001: Standalone Lightweight In-Memory Mocking for Frappe App Tests

- **Status:** Accepted
- **Decider:** Tech Lead Department
- **Date:** 2026-10-18
- **Context / Problem Statement:**
  POL CRM requires comprehensive automated unit and integration testing across its domain logic (Stories 1–5: RFM scoring, messaging policy, offer engine, gateway adapters, and marketing automation). Running tests through the traditional Frappe Bench suite (`bench run-tests`) requires a fully provisioned MariaDB database, Redis servers, site configurations, and network dependencies. This creates high friction for developer feedback loops and complex CI/CD environments.

## Decision

We have approved and adopted the standalone in-memory mocking architecture implemented in `pol_crm/tests/frappe_mock.py`.

The test architecture provides:
1. **In-Memory Frappe Module Injection:** A complete mock of the `frappe` and `frappe.utils` packages injected into `sys.modules` prior to domain module imports.
2. **Deterministic State Management:** A centralized `reset_mock_frappe()` lifecycle hook invoked during `setUp()` of every test case, eliminating cross-test state leakage.
3. **External Service Isolation:** Complete isolation of HTTP web services (Kavenegar SMS, Telegram Bot) via `unittest.mock.patch` over `requests.post`.
4. **Dual Runner Support:** 100% interoperability with both `pytest` and native `python3 -m unittest discover`.

## Why This Was Decided

1. **Velocity and Feedback:** The entire suite of 114 tests executes in under 0.20 seconds, enabling continuous test-driven development and instant pre-commit validation.
2. **Zero External Infrastructure Dependency:** Developers and CI runners do not require a running Bench instance, MariaDB credentials, or network access to validate business rules.
3. **Flake-Free Test Determinism:** System timezones (`Asia/Tehran`), network failures, and database transactions are mock-controlled, preventing intermittent CI flakes.
4. **Boundary Verification:** Testing through Python mocks strictly verifies module boundaries between RFM scoring, offer provisioning, messaging policies, and delivery adapters.

## Alternatives Ruled Out

1. **Full Frappe Bench Test Environment (`bench --site test.local run-tests`):**
   - *Ruled out* as the primary test runner due to multi-minute setup overhead, database migration latency, and site provisioning complexity in ephemeral CI runners.
   - *Note:* Bench tests may still be utilized for end-to-end integration or DocType schema validation in staging, but business logic testing remains standalone.
2. **In-Memory SQLite Database Translation:**
   - *Ruled out* due to syntax dialect incompatibilities between MariaDB (used by Frappe) and SQLite, which lead to subtle query discrepancies and false test failures.

## Architectural Guidelines for Future Tests

1. Any new Frappe API calls introduced in production code must be reflected in `pol_crm/tests/frappe_mock.py` if not already present.
2. Every test class must define `setUp(self)` and call `reset_mock_frappe()`.
3. Outbound network calls or time-dependent logic must always be mocked explicitly.
