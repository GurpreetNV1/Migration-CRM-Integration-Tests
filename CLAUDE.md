# CLAUDE.md — Migration-CRM-Integration-Tests

Read **`NEW_DEVELOPER_SETUP.md`** first if this is a fresh environment (nothing installed,
sibling repos not yet cloned) — it's a linear guide to a first passing test run. Once set up, use
**`README.md`** for the narrative (what's actually being tested and why — real separate service
processes over real HTTP/Kafka, not one service's own isolated `tests/integration/`) and
**`TESTING_GUIDE.md`** for the exact commands (`run_unit_tests.py`, `run_service_integration_tests.py`,
the real cross-service suite, the real-Sheets mode, flags).

This repo tests the other two: **`server/`** (`Migration-CRM-Backend`) and **`client/`**
(`Migration-CRM-Frontend`), expected to sit alongside it in the same parent folder. It does not
test `renders-react/` (a separate, localStorage-only UI demo with no real backend calls).

For which backend service does what (to know what a failing cross-service test is actually
asserting), check that service's LLD in `server/docs/lld/`. For cross-project business context,
see the sibling **`Migration-CRM-Planning`** repo's own `CLAUDE.md`.
