# Integration Tests — Demo/Run Guide

Step-by-step guide for running this whole suite yourself, start to finish. This is the
**cross-service** test suite — real `uvicorn` subprocesses talking to each other over real
HTTP/Kafka, against the real Google Sheets/Drive-backed Data Gateway. It's separate from (and
proves something different than) each service's own `tests/` folder, which use an in-memory
Gateway stand-in.

If you just want the narrative of what each test proves, `README.md` in this same folder has
that. This file is the "what do I actually type" version.

---

## 0. Scope — which services this actually covers

The backend has 19 service folders under `server/services/`, but only **14 are actually built**
(real logic inside) — the other 5 are empty scaffolds (folder structure + a bare `main.py`, no
controllers/models/routes, no tests of their own). This suite only tests the 14 that exist:

**Tested (14):** `01_user_service`, `02_application_service`, `03_task_service`,
`04_reminder_service`, `07_graphics_service`, `09_support_service`, `11_data_import_service`,
`12_data_gateway_service`, `13_auth_service`, `14_admin_module`, `16_backup_restore_service`,
`17_audit_service`, `18_cleanup_service`, `19_notes_service`.

**Not built yet — nothing to test (5):**

| Service folder | Meant to be |
|---|---|
| `05_email_draft_service` | Email Drafting |
| `06_reports_service` | Reports |
| `08_client_portal_service` | Client Portal |
| `10_regional_office_service` | Regional/Office Management |
| `15_otp_forwarding_module` | OTP Forwarding |

These 5 were deferred to Phase 2 in the sprint scoping decision — not accidentally skipped. If
you're asked "why isn't X covered" during a demo, this is why: there's no code there yet to run a
test against.

---

## 1. One-time setup (skip if you've already done this before)

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
(If a `.venv` is missing for one of these, `conftest.py` silently falls back to your global
interpreter instead — that's fine as long as that interpreter has the service's own
`requirements.txt` installed too. If it doesn't, that service's subprocess will fail to start and
you'll see why in its log file — see section 5.)

---

## 2. Before every run — 3 checks

**a. Kafka must be running** (container name `crm-kafka`, `localhost:9092`):

```
docker ps --filter name=crm-kafka
```

If it's not listed, start it: `docker start crm-kafka` if the container already exists, or see
the project root's `STARTUP_GUIDE.md` §"Kafka" for the full `docker run` command if it's never
been created on this machine.

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

## 3. Run the whole suite

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
