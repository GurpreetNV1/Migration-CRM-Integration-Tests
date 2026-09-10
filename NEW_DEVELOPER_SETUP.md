# New Developer Setup — From a Blank Machine to a Passing Test Run

This is a linear, do-it-in-order guide for someone with **nothing installed yet** who needs to
get this project's tests running for the first time. It ends with a passing test run and points
you at `TESTING_GUIDE.md` for everything beyond that (advanced flags, what each test proves, the
real-Sheets mode, troubleshooting). If you already have the three repos cloned and services set
up, skip to step 5 — that's the first step specific to this repo rather than general setup.

**What you'll actually be able to run at the end of this guide**: the fast tiers only —
`run_unit_tests.py` (827 tests) and `run_service_integration_tests.py` (245 tests), both
in-memory, no external account needed, done in well under a minute. The 11 real cross-service
tests (`pytest tests/ -v`) and the real-Sheets mode of `run_local_integration_tests.py` need a
real Google service account and spreadsheet IDs that only the project owner currently has — see
the note at the end of step 7 if you need those too.

---

## 1. Install the prerequisites (one-time, whole machine)

| Tool | Why | Confirm it's installed |
|---|---|---|
| **Git** | clone the three repos | `git --version` |
| **Python 3.11+** | every backend service, and this repo's own test runner | `python --version` (3.13 is confirmed working; anything 3.11+ should be fine) |
| **Docker Desktop** | runs the local Kafka broker (and optionally the whole stack via Docker Compose) | `docker --version`, and make sure the Docker Desktop app itself is running (its tray icon shows the engine is up) — the CLI installs separately from the running engine |
| **Node.js 18+** | only needed if you'll also run the `client` frontend, not for this repo's tests on their own | `node --version` |

If any of these are missing, install them normally for your OS first — nothing below is specific
to this project until step 2.

---

## 2. Clone the three repos as siblings

This project is split across three separate git repositories that are expected to sit next to
each other in the same parent folder — nothing hardcodes an absolute path, but every relative
reference (`server/services/...`, `../client`, etc.) assumes this exact layout:

```
CRM/
├── server/             <- backend: ~19 FastAPI microservices + the API Gateway
├── client/              <- frontend: the React app
└── integration-tests/   <- this repo: all testing, centralized
```

```
mkdir CRM && cd CRM
git clone <server repo's remote URL> server
git clone <client repo's remote URL> client
git clone <integration-tests repo's remote URL> integration-tests
```

(Ask the project owner for the three remote URLs if you don't have them — they're private repos.)

---

## 3. Start Kafka

A single-broker, no-persistence-needed local Kafka container, named `crm-kafka` — every service
that publishes/consumes events expects to find it at `localhost:9092`.

**Check if it already exists first** (if someone else set this machine up before you, skip
straight to starting it):

```
docker ps -a --filter name=crm-kafka
```

- **Not listed at all** → create it:
  ```
  docker run -d --name crm-kafka -p 9092:9092 ^
    -e KAFKA_NODE_ID=1 -e KAFKA_PROCESS_ROLES=broker,controller ^
    -e KAFKA_LISTENERS=PLAINTEXT://0.0.0.0:9092,CONTROLLER://0.0.0.0:9093 ^
    -e KAFKA_ADVERTISED_LISTENERS=PLAINTEXT://localhost:9092 ^
    -e KAFKA_LISTENER_SECURITY_PROTOCOL_MAP=CONTROLLER:PLAINTEXT,PLAINTEXT:PLAINTEXT ^
    -e KAFKA_CONTROLLER_LISTENER_NAMES=CONTROLLER ^
    -e KAFKA_CONTROLLER_QUORUM_VOTERS=1@localhost:9093 ^
    -e CLUSTER_ID=JwZgH3DhTvCEw2FPhWDC2Q ^
    -e KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR=1 ^
    confluentinc/cp-kafka:7.6.1
  ```
  (The `^` line-continuation is Windows `cmd`/PowerShell syntax — in Git Bash/macOS/Linux use
  `\` instead, on one physical command.) `CLUSTER_ID` here is just this stack's own cluster
  identity, not a secret — any valid base64-encoded 16-byte UUID works if you ever need a
  different one (`python -c "import uuid, base64; print(base64.urlsafe_b64encode(uuid.uuid4().bytes).rstrip(b'=').decode())"`).
- **Listed with a status like `Exited (...)`** → it exists, just stopped: `docker start crm-kafka`.
- **Listed as `Up ...`** → already running, nothing to do.

Confirm it worked either way:

```
docker ps --filter name=crm-kafka
```

should show `Up ...` and `0.0.0.0:9092->9092/tcp`.

**You only need this for the fast tiers this guide ends with if you actually run tests that touch
Kafka** — most of `run_unit_tests.py`/`run_service_integration_tests.py` mock event
publishing/consuming entirely and don't need a real broker at all. It's required for the 11 real
cross-service tests (step 7's note) and is set up here regardless since it's a five-minute,
one-time step and several of the "fast tier" tests do exercise real Kafka event flows.

---

## 4. Set up a Python virtual environment per backend service

Each service under `server/services/` has its own isolated `.venv` — this is because every
service's `requirements.txt` starts with `-e ../../shared` (this project's own shared package),
which resolves relative to whichever folder you're installing from, so one shared venv across
every service doesn't work cleanly.

Repeat this for every service folder listed below (swap `<service_folder>` each time):

```
cd server/services/<service_folder>
python -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt
cd ../../..
```

(In Git Bash/macOS/Linux: `.venv/Scripts/python.exe` becomes `.venv/bin/python`.)

**The services this repo's tests actually exercise** (do these 14 at minimum):
`01_user_service`, `02_application_service`, `03_task_service`, `04_reminder_service`,
`07_graphics_service`, `09_support_service`, `11_data_import_service`,
`12_data_gateway_service`, `13_auth_service`, `14_admin_module`, `16_backup_restore_service`,
`17_audit_service`, `18_cleanup_service`, `19_notes_service`.

If you skip a service's `.venv`, its tests fall back to your global Python interpreter — which
only works if that interpreter happens to already have that service's own `requirements.txt`
installed. Simplest to just do all 14 up front rather than debug a missing-package error later.
(`05_email_draft_service` has no `.venv` of its own by design — it runs fine on the global
interpreter, no per-service dependencies of note.)

This step is genuinely the slow part of a fresh setup (14 separate `pip install`s) — everything
after this is fast.

---

## 5. Install this repo's own test dependencies

`integration-tests` itself has no `.venv` — its own dependencies (`httpx`, `pytest`,
`python-dotenv`, `bcrypt`) install straight into your global interpreter, since its test runner
scripts just orchestrate the per-service venvs from step 4 rather than doing HTTP/business logic
of their own:

```
cd integration-tests
python -m pip install -r requirements.txt
```

---

## 6. Run the fast tests — no Kafka, no credentials, no Docker Compose needed

These two commands are the actual payoff of everything above. Both are pure orchestrators — they
`cd` into each service and run that service's own already-existing `pytest`, using the `.venv`
you just created for each:

```
python run_unit_tests.py
```

827 tests, one class/function at a time, everything else mocked — should finish in well under a
minute, ending with a per-service pass/fail line and a grand total.

```
python run_service_integration_tests.py
```

245 tests, hitting each service's real HTTP routes via FastAPI's `TestClient`, but against an
**in-memory** Data Gateway stand-in (no real Google Sheets, no external account) — also under a
minute.

**If either of these fails on a specific service**, it's almost always that service's `.venv`
from step 4 either wasn't created or didn't finish installing — re-run step 4 for that one
service and try again. Both commands print the full pytest output inline for any service that
fails, and also save a complete log to `logs/unit_test_runs/<timestamp>.log` /
`logs/service_integration_test_runs/<timestamp>.log`.

Run just one service while debugging:

```
python run_unit_tests.py --service task
python run_service_integration_tests.py --service task -v
```

**A clean run of both commands means your setup is genuinely working** — every backend service's
own business logic and HTTP layer, verified, with nothing more than what you just installed.

---

## 7. Where to go from here

- **`TESTING_GUIDE.md`** (this repo) — the full reference: what every individual test proves,
  the dual-mode `run_local_integration_tests.py` (same 245 tests, optionally against a real Data
  Gateway/real Sheets instead of in-memory), troubleshooting, and the 11 true cross-service tests.
- **`catalog/`** (this repo) — a plain-English, one-file-per-service index of what every single
  test actually proves, if `-v` output alone isn't enough context.
- **`server/docs/STARTUP_GUIDE.md`** (in the `server` repo) — how to actually run the full stack
  (Docker Compose or manual per-service) and click through the real UI, not just run its tests.

**If you need the real cross-service suite or real-Sheets mode** (`pytest tests/ -v`, or
`run_local_integration_tests.py` without `--gateway-mode=memory`): these write to real Google
Sheets/Drive under a real service account that only the project owner currently holds, and the
account has a hard 60-requests/minute ceiling shared across everyone using it — ask the project
owner for the credentials (`server/services/12_data_gateway_service/.env`) before attempting
either, rather than guessing at a service-account setup yourself. `TESTING_GUIDE.md` section 2
covers the exact prerequisites once you have them.
