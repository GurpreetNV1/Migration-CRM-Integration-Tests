# Integration Tests — Cross-Service

Real, separate service processes talking to each other for real — the real Data Gateway Service,
real local Kafka, and real business services, each its own OS process, communicating over real
HTTP/Kafka. This is **not** the same thing as each service's own `tests/integration/` (those use
`TestClient` against an in-memory Gateway, fully isolated). This repo proves the *system*, not
one service in isolation.

This repo is also now the **single centralized place to run all testing** for the project, not
just the cross-service suite — see "Three kinds of testing" below. Step-by-step run instructions
(commands, prerequisites, troubleshooting) are in `TESTING_GUIDE.md`; this file is the narrative
of what's here and why.

## Three kinds of testing here

| | Unit tests (607) | Per-service integration tests (210) | Cross-service tests (11, growing) |
|---|---|---|---|
| Command | `python run_unit_tests.py` | `python run_service_integration_tests.py` | `pytest tests/ -v` |
| What it starts | Nothing — one class/function at a time, everything else mocked | Nothing — FastAPI's `TestClient`, in-process, against that service's in-memory Gateway stand-in | Real `uvicorn` subprocesses, real Kafka, real Google Sheets/Drive |
| Proves | One unit of business logic in isolation | One service's own HTTP layer + business logic + repository wired together correctly | Multiple independently-running real services actually work together over a real network |
| Runtime | seconds | under a minute (all 15 services) | ~7 minutes |
| Lives in | `server/services/<service>/tests/unit/` | `server/services/<service>/tests/integration/` | this repo's own `tests/` |
| Full index | `catalog/README.md` | `catalog/README.md` | `catalog/README.md`'s "True cross-service tests" section |

**These 210 per-service integration tests also physically live in this repo now**, under
`tests/service_integration/<service>/` — verbatim copies of the files in
`server/services/<n>/tests/integration/` (the originals there are untouched and
`run_service_integration_tests.py` above keeps working exactly as it always has, always in-memory).
The copies are **dual-mode**, run with `python run_local_integration_tests.py`:

```
python run_local_integration_tests.py                        # default: real Data Gateway, real Google Sheets
python run_local_integration_tests.py --gateway-mode memory   # fast, in-memory, no external dependency
python run_local_integration_tests.py --service support       # just one service, either mode
```

**Real mode is the default, not memory** — every copied test writes to the real, shared Google
Sheets unless you explicitly pass `--gateway-mode=memory`. One real Gateway subprocess is started
once and shared across all 14 services (same `start_service`/quota-pacing machinery as the
cross-service suite's own `gateway_url` fixture below), and each per-service copy's
`HttpDataGatewayClient` retry budget is widened to the same quota-safe values `gateway_retry.py`
uses, so a rolling-quota 503 mid-run is retried rather than failing the test. See
`TESTING_GUIDE.md` section on this command for full details, and each `catalog/<service>.md` —
the same test definitions apply unchanged to both the original in-memory-only location and this
dual-mode copy, since every test only ever talks to `TestClient(app)` and has no idea which
Gateway backend is behind it.

**Why the first two tiers use an in-memory Gateway stand-in instead of real Google Sheets:** the
Google account backing this project has a *permanent* ceiling of 60 Sheets/Drive API requests per
minute (see `server/gaps-in-services/Pending_Items.md`) — a hard cap, not a temporary block. 817
tests running against a real Gateway would mean hundreds to thousands of real API calls just for
that tier, blowing well past that ceiling before even reaching the 11 cross-service tests, and
turning a sub-minute run into one measured in tens of minutes, gated on quota backoff. The
in-memory stand-in has correct read/write/query semantics (it's what most of these 817 tests
actually exercise), so it's the right tool for proving business logic; it's specifically real
Gateway *behavior* (merge semantics, boolean coercion, schema/column drift, concurrent-access
thread-safety) that it can't catch — which is exactly what the 11 cross-service tests, plus a
small number of new targeted real-Sheets tests (see "Planned additions" below), exist to cover
instead, deliberately kept small so the quota ceiling stays a non-issue.

Neither `run_unit_tests.py` nor `run_service_integration_tests.py` contains or duplicates any
test — both are thin orchestrators that `cd` into each built service under `server/services/` and
run that service's own already-existing `pytest tests/unit/` or `tests/integration/`, using that
service's own `.venv` if it has one. Run one service only with `--service task` (see
`_test_runner_common.py`'s `ALL_SERVICE_DIRS` for every valid name). Any extra flags (`-v`,
`-k <expr>`, etc.) pass straight through to pytest.

## Planned additions

Two deliberately small, targeted additions to close the specific gap the in-memory tiers can't
cover, without touching the 210/607 split above or the quota budget it depends on:
- **~1 real-Sheets schema/coercion test per service (~15 new)** — checks that service's actual
  assumed tab schema and field types still match the live sheet, the exact class of bug (header
  drift, boolean-as-string coercion) that's bitten this project before.
- **2-3 new flagship cross-service flows** — same shape as the existing 11, covering real
  business flows not yet exercised end-to-end (candidates: an RFI-request flow, a
  compliance-status-change flow, an escalation flow).

## Setup (one-time)

Most services under `server/services/` now have their own isolated `.venv` (created inside that
service's own folder, same convention as the project root's `STARTUP_GUIDE.md`). `conftest.py`
resolves each service's own `.venv/Scripts/python.exe` and falls back to the global interpreter
only if that service doesn't have one yet — so either set up works, as long as whichever
interpreter actually runs a given service has that service's `requirements.txt` installed.

Install this repo's own light dependencies into your global interpreter (this repo itself has no
`.venv`):

```
python -m pip install -r requirements.txt
```

## Prerequisites to run

1. **Local Kafka must already be running**: container name `crm-kafka` (KRaft mode, `localhost:9092`)
   — see the project root's `STARTUP_GUIDE.md` for the full `docker run` command if it doesn't
   exist yet, or `docker start crm-kafka` if it does but is stopped. The suite does not start
   Kafka itself.
2. **Ports 8500-8513 must be free** — this suite reserves that range for its own service
   processes. A pre-flight check fails fast with a clear message if one is already taken.
3. **No manual dev services running.** If you've started services by hand per the project root's
   `STARTUP_GUIDE.md` (e.g. for manual UI testing), stop them first — that guide's ports overlap
   this suite's reserved range, and a service left running there will make this suite's own
   pre-flight port check fail.
4. **Real Google Sheets/Drive credentials, already configured.** Unlike this repo's earlier
   in-memory-only design, `gateway_url` no longer forces `DATA_BACKEND=memory` — the Gateway's own
   `.env` (real service-account credentials + spreadsheet IDs) takes over, so every test in this
   suite reads and writes the real, shared spreadsheets. This has two consequences:
   - **Quota.** The Google account backing this project has a *permanent* 60 requests/minute
     ceiling (see `server/gaps-in-services/Pending_Items.md`), shared across the whole suite. Every
     Gateway-touching call in these tests goes through `gateway_retry.call_with_quota_backoff` (a
     503 is treated as "wait ~70s for the rolling window to clear, then retry" — never a hard
     failure) — if you add a new test, wrap its Gateway calls the same way rather than calling
     `httpx` directly.
   - **Shared state.** Test data lands in the real spreadsheets other sessions/services also use.
     Tests use UUID-suffixed data to avoid collisions; a few (`rating_ladder`, `note_types` config
     rows) are seeded idempotently via `seed_gateway_record_if_missing` since they're addressed by
     a fixed key, not a UUID.

## Running the cross-service suite (this repo's 11 tests)

```
pytest tests/ -v
```

For the other 817 tests (every built service's own suite, fast, in-memory), use
`python run_unit_tests.py` / `python run_service_integration_tests.py` instead — see "Three kinds
of testing" above.

Each test file shares one session-scoped real Gateway (+ Audit Service, where needed) — real
Sheets-backed startup alone takes 30-90s (~1 read per tab across ~37 tabs), paid once for the
whole run, not once per file. Full suite runtime is ~7 minutes. Per-file business services
(Application, Task, User, etc.) are function-scoped subprocesses on top of that shared Gateway.

Every service's subprocess output is written to `logs/<service>.log` (fresh per test run, gitignored)
instead of being silently discarded — check there first if a service fails to start or a test sees
an unexpected connection error mid-run.

Windows note: subprocess teardown uses `terminate()` (no graceful ASGI shutdown), so a stray
`ProactorEventLoop`/"unclosed transport" line in stderr after a test is expected noise, not a
failure.

## What each test proves

See `catalog/README.md` for the full index (every existing per-service test *and* these
cross-service ones, each with a 50-60 word summary). Short version:

| Test | Proves |
|---|---|
| `test_application_kafka_to_audit.py` | Application Service → real Kafka → Audit Service: a real cross-process event lands and is queryable. |
| `test_support_kafka_to_audit.py` | Same pattern, Support Service — confirms it's a repeatable system property, not a fluke. |
| `test_admin_config_shared_via_gateway.py` | Two independent service processes share live data through the real Gateway (not just Kafka plumbing) — Admin Module writes a config row, Application Service reads it. |
| `test_graphics_full_lifecycle_over_http.py` | A complete real business flow (create → accept → upload → review → approve → publish) over real HTTP against the real Gateway. |
| `test_auth_login_against_real_gateway_credentials.py` | Auth Service validates a real bcrypt-hashed credential row through the real Gateway — correct/wrong password, token issuance. |
| `test_user_contact_rating_against_real_config.py` | User Service's rating strategy reads Admin Module's live `rating_ladder` config through the real Gateway, not a hardcoded default. |
| `test_task_stage_change_creates_task.py` | Flagship flow: the full real client-registration gate (signature + invoice + payment) advances an Application, publishes a real Kafka `application.stage_changed` event, and Task Service auto-creates a Task from it — also confirmed in Audit Service. |
| `test_reminder_sweep_fires_and_reaches_audit.py` | Reminder Service's own real background sweep picks up a due reminder, moves it to history in real Sheets, and publishes a correctly-attributed real Kafka event. |
| `test_data_import_reaches_a_terminal_status.py` | A submitted import job always reaches a real terminal status (never hangs at "processing"), including a real Gateway-ownership rejection recorded with its actual reason. |
| `test_cleanup_purges_only_after_backup_confirmed.py` | Cleanup Service only purges old Audit_Log rows once Backup & Restore has a confirmed successful run recorded — a recent row survives, an old one doesn't. |
| `test_notes_ownership_and_config_driven_type.py` | Notes Service validates note_type against live Admin Module config and enforces its ownership guard (author-only edits) against real persisted data. |

If short on time, `test_graphics_full_lifecycle_over_http.py` and
`test_task_stage_change_creates_task.py` are the most expensive (most real Sheets/Drive calls) —
first to skip if you're quota-constrained. The two Kafka-to-Audit tests remain the cheapest true
cross-service demonstration.
