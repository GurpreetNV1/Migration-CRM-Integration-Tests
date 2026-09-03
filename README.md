# Integration Tests — Cross-Service

Real, separate service processes talking to each other for real — the real Data Gateway Service,
real local Kafka, and real business services, each its own OS process, communicating over real
HTTP/Kafka. This is **not** the same thing as each service's own `tests/integration/` (those use
`TestClient` against an in-memory Gateway, fully isolated). This repo proves the *system*, not
one service in isolation.

## Setup (one-time)

This repo has no virtual environment of its own — **do not create one**. Every service under
`server/services/` is installed into the single global Python interpreter on this machine
(confirmed: no `.venv` exists anywhere in the project; `fastapi`/`uvicorn`/`kafka-python`/
`crm_shared` are all global). `conftest.py` launches each service via
`subprocess.Popen([sys.executable, ...])` — if `sys.executable` points at an isolated venv
instead of that global interpreter, every service subprocess fails immediately with
`ModuleNotFoundError`. Install this repo's own light dependencies into that same global
interpreter:

```
python -m pip install -r requirements.txt
```

## Prerequisites to run

1. **Local Kafka must already be running**: `docker start kafka` (KRaft mode, `localhost:9092`).
   The suite does not start Kafka itself.
2. **Ports 8500-8510 must be free** — this suite reserves that range for its own service
   processes (distinct from whatever ports you use for manual/dev testing). A pre-flight check
   fails fast with a clear message if one is already taken.
3. No other setup — the real Data Gateway Service is started per test module with
   `DATA_BACKEND=memory` (an in-memory Sheets/Drive stand-in), so no real Google credentials are
   needed for these tests.

## Running

```
pytest tests/ -v
```

Each test file starts its own fresh Gateway (+ Audit Service, where needed) as real subprocesses,
runs its scenario over real HTTP, and tears everything down afterward. Expect ~10-30s of startup
time per test file (Kafka-mode services do a real broker round-trip at startup).

Windows note: subprocess teardown uses `terminate()` (no graceful ASGI shutdown), so a stray
`ProactorEventLoop`/"unclosed transport" line in stderr after a test is expected noise, not a
failure.

## What each test proves

See `catalog/README.md` for the full index (every existing per-service test *and* these new
cross-service ones, each with a 50-60 word summary). Short version:

| Test | Proves |
|---|---|
| `test_application_kafka_to_audit.py` | Application Service → real Kafka → Audit Service: a real cross-process event lands and is queryable. |
| `test_support_kafka_to_audit.py` | Same pattern, Support Service — confirms it's a repeatable system property, not a fluke. |
| `test_admin_config_shared_via_gateway.py` | Two independent service processes share live data through the real Gateway (not just Kafka plumbing) — Admin Module writes a config row, Application Service reads it. |
| `test_graphics_full_lifecycle_over_http.py` | A complete real business flow (create → accept → upload → review → approve → publish) over real HTTP against the real Gateway. |

If short on time, `test_graphics_full_lifecycle_over_http.py` and
`test_admin_config_shared_via_gateway.py` are the first two to skip for the demo — the two
Kafka-to-Audit tests alone are still a true, working cross-service demonstration.
