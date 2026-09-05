# Integration Tests — Demo/Run Guide

Step-by-step guide for running **every** kind of testing in this project yourself, start to
finish — this one file covers all three commands below, not just the cross-service suite its
title leads with. If you just want the narrative of what each test proves rather than how to run
it, `README.md` in this same folder has that; this file is the "what do I actually type" version.

**What's covered, and where in this guide:**

| Command | What it runs | Section |
|---|---|---|
| `pytest tests/ -v` | 11 real cross-service tests — real subprocesses, real Kafka, real Google Sheets/Drive | 1-7 |
| `python run_unit_tests.py` | 607 pure unit tests, in-memory, fast | 8 |
| `python run_service_integration_tests.py` | 210 per-service tests (real HTTP routes, in-memory Gateway) | 8 |

The cross-service suite (sections 1-7) is the one that needs Docker/Kafka/real credentials and
takes ~7 minutes; the other two (section 8) need none of that and take under a minute combined.
Section 9 covers what's planned but not built yet.

---

## 0. Scope — which services this actually covers

The backend has 19 service folders under `server/services/`. **14 have real business logic
built** and are covered by the true cross-service suite (section 3). One more,
`05_email_draft_service`, is a step behind those 14 — it exists only as a bare health-check
endpoint with no drafting logic yet — but it does have that one real integration test, so it's
still included in `run_service_integration_tests.py` (section 8) for completeness, just not in
`run_unit_tests.py` (it has no unit tests at all). The remaining 4 are empty scaffolds with no
tests at all.

**Covered by the cross-service suite, section 3 (14):** `01_user_service`,
`02_application_service`, `03_task_service`, `04_reminder_service`, `07_graphics_service`,
`09_support_service`, `11_data_import_service`, `12_data_gateway_service`, `13_auth_service`,
`14_admin_module`, `16_backup_restore_service`, `17_audit_service`, `18_cleanup_service`,
`19_notes_service`.

**Covered only by section 8's per-service runners, not the cross-service suite (1):**
`05_email_draft_service` — health check only, no drafting/templating/approval logic built yet.

**Not built at all — no tests to run either way (4):**

| Service folder | Meant to be |
|---|---|
| `06_reports_service` | Reports |
| `08_client_portal_service` | Client Portal |
| `10_regional_office_service` | Regional/Office Management |
| `15_otp_forwarding_module` | OTP Forwarding |

These 5 (Email Draft's real logic plus the 4 fully-empty ones) were deferred to Phase 2 in the
sprint scoping decision — not accidentally skipped. If you're asked "why isn't X covered" during a
demo, this is why: there's no real code there yet to run a meaningful test against.

---

## 1. One-time setup (skip if you've already done this before)

This setup is shared by all three commands in this guide, not just the cross-service suite —
`run_unit_tests.py` and `run_service_integration_tests.py` (section 8) use these same per-service
`.venv`s.

**a. Install this repo's own light test dependencies** (httpx, pytest, python-dotenv, bcrypt)
into your global Python interpreter — this repo has no `.venv` of its own:

```
cd integration-tests
python -m pip install -r requirements.txt
```

**b. Make sure each service being tested has its own `.venv`.** Most already do (created earlier
this session). If a service folder under `server/services/` is missing its `.venv`, create one —
same steps as the project root's `STARTUP_GUIDE.md`:

```
cd server/services/<service_folder>
python -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Services this suite exercises: `12_data_gateway_service`, `17_audit_service`,
`01_user_service`, `13_auth_service`, `02_application_service`, `09_support_service`,
`14_admin_module`, `07_graphics_service`, `03_task_service`, `04_reminder_service`,
`11_data_import_service`, `16_backup_restore_service`, `18_cleanup_service`, `19_notes_service`.
(`05_email_draft_service`, used only by section 8's `run_service_integration_tests.py`, has no
`.venv` of its own and doesn't need one — it runs fine on the global interpreter.)

If a `.venv` is missing for one of these, `conftest.py` (and the section 8 runner scripts)
silently fall back to your global interpreter instead — that's fine as long as that interpreter
has the service's own `requirements.txt` installed too. If it doesn't, that service's subprocess
will fail to start and you'll see why in its log file — see section 5.

---

## 2. Before running the cross-service suite — 3 checks

(These only apply to section 3's `pytest tests/ -v`. Section 8's two commands need none of this —
no Kafka, no ports, no real credentials — skip straight there if that's all you're running.)

**a. Kafka must be running** (container name `crm-kafka`, `localhost:9092`):

```
docker ps --filter name=crm-kafka
```

If this errors with something like `failed to connect to the docker API` /
`dockerDesktopLinuxEngine: The system cannot find the file specified`, that means **Docker
Desktop itself isn't running yet** (separate from the Kafka container inside it) — open Docker
Desktop from the Start menu first and wait for its tray icon to show the engine is up, then
re-run the command above.

Once Docker responds but `crm-kafka` isn't listed, that just means it isn't currently *running* —
`docker ps` only shows running containers. Check whether it exists at all (running or stopped):

```
docker ps -a --filter name=crm-kafka
```

- **Listed with a status like `Exited (...)`** → it exists, just stopped. Start it:
  ```
  docker start crm-kafka
  ```
- **Not listed at all** → it's never been created on this machine. See the project root's
  `STARTUP_GUIDE.md` §"Kafka" for the full `docker run` command to create it.

Either way, re-run `docker ps --filter name=crm-kafka` afterward and confirm it shows `Up ...` in
`STATUS` and `0.0.0.0:9092->9092/tcp` in `PORTS` before moving on.

(If you also see a `crm-kafka-1` container listed, that's a stray leftover from an earlier setup
attempt — ignore it, it's not used by anything.)

**b. No manual dev services running.** If you (or anyone) started the client/server stack by hand
per `STARTUP_GUIDE.md` for UI testing, **stop those first** — that guide's services also start on
ports 8500+ and will collide with this suite's own reserved range. Check:

```
netstat -ano | findstr "LISTENING" | findstr ":85"
```

Anything listed in the `8500`-`8513` range must be stopped before continuing (the suite's own
pre-flight check will refuse to start and tell you which port if you skip this).

**c. Real Google Sheets credentials are in place.** This is already configured
(`server/services/12_data_gateway_service/.env` has real service-account credentials and
spreadsheet IDs) — nothing to do here normally, just know that **every test run writes real rows
into the real spreadsheets**. That's intentional (it's what makes this a real demo, not a mock),
but it does mean:
- The Google account has a **permanent 60 requests/minute ceiling**. The suite paces itself
  around this automatically (a client-side wait-and-retry, not a code change you need to make) —
  if you see the run pause for up to ~70 seconds partway through, that's expected, not a hang.
- Test data is UUID-suffixed so repeated runs don't collide with each other or with manual UI
  testing data.

---

## 3. Run the cross-service suite (this repo's 11 tests)

This is the one that proves the *system* wired together — real subprocesses, real Kafka, real
Sheets. If you instead want the 817 fast per-service tests (in-memory, ~1-1.5 minutes total), skip to
section 8.

From the `integration-tests` folder:

```
cd integration-tests
python -m pytest tests/ -v
```

**Expect this to take about 7 minutes.** Most of that is real subprocess startup (the Gateway
alone takes 30-90 seconds to rebuild its row index from real Sheets on its first request) and
real Kafka round-trips — not slow tests, slow infrastructure, which is unavoidable when everything
is a genuine separate process instead of an in-memory mock.

To run just one test file (useful for a quick re-check or a focused demo of one flow):

```
python -m pytest tests/test_task_stage_change_creates_task.py -v
```

---

## 4. Reading the result

A clean run ends with a line like:

```
======================= 11 passed in 420.13s (0:07:00) ========================
```

`-v` prints one line per test as it finishes, e.g.:

```
tests/test_auth_login_against_real_gateway_credentials.py::test_login_succeeds_with_correct_password_and_rejects_the_wrong_one PASSED
```

If something fails, pytest prints the full assertion/traceback for that test inline — that's
usually enough on its own. If a test fails with a **connection error** (not an assertion), that
means one of the real service subprocesses didn't come up or died mid-run — go straight to
section 5's log files rather than guessing from the pytest output.

---

## 5. Where things are

**Test definitions** — one file per scenario, all in `integration-tests/tests/`:

| File | What it proves |
|---|---|
| `test_admin_config_shared_via_gateway.py` | Admin Module writes config; Application Service reads it live through the shared real Gateway. |
| `test_application_kafka_to_audit.py` | Application Service → real Kafka → Audit Service: a real event lands and is queryable. |
| `test_support_kafka_to_audit.py` | Same pattern, Support Service. |
| `test_graphics_full_lifecycle_over_http.py` | Full poster lifecycle (create → accept → upload → review → approve → publish) over real HTTP. |
| `test_auth_login_against_real_gateway_credentials.py` | Real bcrypt-hashed credential row, correct/wrong password, token issuance. |
| `test_user_contact_rating_against_real_config.py` | Rating validation reads Admin Module's live config through the real Gateway. |
| `test_task_stage_change_creates_task.py` | **Flagship test.** Full real registration-gate flow (signature + invoice + payment) advances an Application, publishes a real Kafka event, Task Service auto-creates a Task, Audit Service records it. |
| `test_reminder_sweep_fires_and_reaches_audit.py` | Reminder Service's own real background sweep fires a due reminder and reaches Audit Service. |
| `test_data_import_reaches_a_terminal_status.py` | An import job always reaches a real terminal status (never hangs), including a genuine ownership-rejection recorded with its reason. |
| `test_cleanup_purges_only_after_backup_confirmed.py` | Cleanup Service only purges old audit rows once a successful backup is confirmed. |
| `test_notes_ownership_and_config_driven_type.py` | Note-type validation against live config, plus the author-only ownership guard. |

Every file's own docstring at the top has a longer explanation of exactly what real
process-boundary it's proving, if you want more detail than the table above while presenting.

**Test infrastructure** (not tests themselves, but what makes them work):
- `integration-tests/conftest.py` — starts/stops every real service subprocess, defines the
  shared `gateway_url`/`audit_service_url`/`business_service` fixtures every test file uses.
- `integration-tests/gateway_retry.py` — the quota-safe retry helper mentioned in section 2c.
- `integration-tests/run_unit_tests.py`, `run_service_integration_tests.py`, and the
  `_test_runner_common.py` they both share — the section 8 orchestrators. These don't contain
  tests either; they just `cd` into each service and run its own already-existing `pytest`.

**Outcomes / logs**:
- The pytest console output itself (pass/fail, assertion detail) — this is the primary result.
- `integration-tests/logs/<service_name>.log` — full stdout/stderr for every real service
  subprocess started during the run (gateway, audit, application, task, reminder, user, auth,
  data_import, backup, cleanup, notes, support, admin, graphics), overwritten fresh each run. If
  a test fails with a connection error or an unexpected 500, this is where the real cause is —
  e.g. `logs/gateway.log` will show the actual Python traceback if the Gateway hit an error
  talking to real Sheets.
- `integration-tests/catalog/` — one markdown file per service with a running index of every
  test that covers it (both this suite's and each service's own unit/integration tests), if you
  want the full inventory rather than just this suite's 11 files.

---

## 6. Common issues

- **"Port 85xx for 'x' is already in use"** — a manual dev service or a previous test run that
  didn't tear down cleanly is still holding that port. Re-check section 2b.
- **A test times out waiting for something to become "due"/"fired"/"created"** — usually a slow
  Kafka round-trip on a loaded machine, not a real failure. Re-run just that file on its own
  (section 3) before assuming something's broken.
- **`503 Service Unavailable` shows up in a log or a rare assertion failure** — that's the real
  60-requests/minute Sheets quota; the suite's own retry helper (section 2c) rides out a single
  hit automatically, but if you're running this suite AND manually poking the Gateway with curl
  at the same time, you can exhaust the shared quota faster than the suite expects. Wait a minute
  and re-run.
- **Everything fails immediately with connection-refused** — the Gateway itself never became
  healthy. Check `logs/gateway.log` first; the most common real cause is a stale/expired
  `server/services/12_data_gateway_service/.env` credential or a tab missing from
  `TAB_SPREADSHEET_IDS_JSON` (the startup error names the exact tab).

---

## 7. Optional — confirm it actually touched real Sheets

If you want to show the data really landed (not just that HTTP responses looked right), open any
of the real spreadsheets used by the tab a test just touched (e.g. the `Task` tab after running
`test_task_stage_change_creates_task.py`) and look for a freshly-added row — test data is always
UUID-suffixed (e.g. `VISA-b52c13f7`), so it's easy to spot as new.

---

## 8. Running every service's own tests (607 unit + 210 integration, fast)

Separate from the 11 real cross-service tests above, every built service already has its own
test suite split into two subfolders under `server/services/<service>/tests/`:

- **`tests/unit/`** (607 tests total) — one class/function at a time, everything else mocked. No
  HTTP, no Gateway of any kind.
- **`tests/integration/`** (210 tests total, across all 15 built-or-partial services including
  `05_email_draft_service`'s single health check) — hits the real FastAPI routes via `TestClient`,
  but in one process against an **in-memory** Data Gateway stand-in, not real Sheets.

**Why in-memory and not real Sheets for these two tiers:** the Google account behind this project
has a *permanent* ceiling of 60 Sheets/Drive requests per minute (see
`server/gaps-in-services/Pending_Items.md`) — not a temporary block, a hard cap. These 817 tests
running against a real Gateway would mean hundreds to thousands of real API calls for this tier
alone, blowing past that ceiling before even reaching the 11 cross-service tests below, and
turning a sub-minute run into tens of minutes gated on quota backoff. The in-memory stand-in has
correct read/write/query semantics, so it's the right tool for proving business logic — it's
specifically real Gateway *behavior* (schema drift, boolean coercion, concurrent-access
thread-safety) it can't catch, which is what the 11 cross-service tests exist for instead,
deliberately kept small so the quota ceiling stays a non-issue.

Neither tier needs Kafka, real Sheets, or any of the section 2 checks.

**Run all unit tests from one place** — no need to `cd` into 14 separate folders:

```
cd integration-tests
python run_unit_tests.py
```

**Run all per-service integration tests (still in-memory) from one place:**

```
python run_service_integration_tests.py
```

Each takes well under a minute (Auth Service's own bcrypt hashing is the slowest single
contributor in either, a handful of seconds on its own). Both print one line per service
(pass/fail + pytest's own summary line) and a grand total at the end; on any failure, that
service's full pytest output is printed inline so you don't have to go dig for it.

**Run just one service's suite**, with either command:

```
python run_unit_tests.py --service task
python run_service_integration_tests.py --service task
```

Valid names match this repo's own service keys (see `_test_runner_common.py`'s
`ALL_SERVICE_DIRS`): `gateway`, `email_draft`, `audit`, `application`, `support`, `admin`,
`graphics`, `task`, `reminder`, `user`, `auth`, `data_import`, `backup`, `cleanup`, `notes`
(`email_draft` has no unit tests, so it's only a valid choice for
`run_service_integration_tests.py`).

Any extra arguments (e.g. `-v` for full per-test output, `-k <expression>` to filter to specific
tests) are passed straight through to pytest:

```
python run_unit_tests.py --service auth -v
```

Neither script contains or duplicates any test itself — both are thin orchestrators that run each
service's own already-existing `pytest tests/unit/` or `tests/integration/`, using that service's
own `.venv` when one exists (falling back to the global interpreter otherwise, same rule
`conftest.py` uses for the cross-service suite).

**Where to find what each of these 817 tests actually does:**
- **The 210 integration tests** (this section's `run_service_integration_tests.py`) — one line
  per test, all in one place: `catalog/integration_tests_index.md`.
- **The 607 unit tests** (this section's `run_unit_tests.py`) — no single consolidated index for
  these (the largest, most narrow tier); full 50-60-word detail lives in each service's own
  `catalog/<n>.md` file, under its `## Unit tests` section.
- Every per-service `catalog/<n>.md` file also has the full 50-60-word detail for its own
  integration tests too, if the one-liner in `integration_tests_index.md` isn't enough.

---

## 9. Planned additions (not built yet)

Two small, deliberately narrow additions planned to close the one real gap the in-memory tiers
above can't cover, without touching their 817-test/quota-free budget:

- **~1 real-Sheets schema/coercion test per service (~15 new)** — checks that service's actual
  assumed tab schema and field types still match the live sheet. This is the exact class of bug
  that's bitten this project before (header drift, a real Sheets boolean cell coming back as the
  string `"FALSE"` instead of `False`), and an in-memory stand-in can never catch it by
  construction, since it never has a real header row or real cell types to drift from.
  These will run against the real Gateway, so they belong under the quota-aware pattern in
  section 2c, likely as new files or additions to this repo's own `tests/`.
- **2-3 new flagship cross-service flows**, same shape as the existing 11 — real business flows
  not yet exercised end-to-end (candidates: an RFI-request flow, a compliance-status-change flow,
  an escalation flow).

Not implemented yet — this section will move once they land.
