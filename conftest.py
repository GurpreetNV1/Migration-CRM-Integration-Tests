"""Real, multi-process service orchestration for cross-service integration tests.

Deliberately not TestClient/in-memory: each fixture here starts a real `uvicorn` subprocess
serving a real service from `server/services/`, over a real port, so tests exercise genuine
inter-process HTTP/Kafka -- the thing none of the per-service `tests/integration/` suites can
prove on their own.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest

SERVER_ROOT = Path(__file__).resolve().parent.parent / "server" / "services"
LOG_DIR = Path(__file__).resolve().parent / "logs"

SERVICE_DIRS = {
    "gateway": SERVER_ROOT / "12_data_gateway_service",
    "audit": SERVER_ROOT / "17_audit_service",
    "application": SERVER_ROOT / "02_application_service",
    "support": SERVER_ROOT / "09_support_service",
    "admin": SERVER_ROOT / "14_admin_module",
    "graphics": SERVER_ROOT / "07_graphics_service",
    "task": SERVER_ROOT / "03_task_service",
    "reminder": SERVER_ROOT / "04_reminder_service",
    "user": SERVER_ROOT / "01_user_service",
    "auth": SERVER_ROOT / "13_auth_service",
    "data_import": SERVER_ROOT / "11_data_import_service",
    "backup": SERVER_ROOT / "16_backup_restore_service",
    "cleanup": SERVER_ROOT / "18_cleanup_service",
    "notes": SERVER_ROOT / "19_notes_service",
}

# Reserved to this repo only -- see README.md "Prerequisites". Never reuse ports from a manual
# dev session running alongside this suite.
PORTS = {
    "gateway": 8500,
    "audit": 8501,
    "application": 8502,
    "support": 8503,
    "admin": 8504,
    "graphics": 8505,
    "task": 8506,
    "reminder": 8507,
    "user": 8508,
    "auth": 8509,
    "data_import": 8510,
    "backup": 8511,
    "cleanup": 8512,
    "notes": 8513,
}

KAFKA_BOOTSTRAP_SERVERS = "localhost:9092"

# Kafka-mode services do a synchronous broker round-trip (KafkaProducer/KafkaConsumer
# construction) at startup, which dominates their startup time -- see
# server/services/02_application_service/app/services/event_publisher.py. Memory-only,
# non-Gateway services never touch Kafka or real Sheets, so they come up in a couple seconds.
HEALTH_TIMEOUT_KAFKA_SECONDS = 30
HEALTH_TIMEOUT_MEMORY_SECONDS = 15
# The Gateway itself is the slow one now that it's real-Sheets-backed (DATA_BACKEND=google):
# startup rebuilds its row index with one read per Sheets tab (~37 tabs), confirmed live to take
# 30-60+ seconds depending on Google API latency -- notably slower than either of the above.
HEALTH_TIMEOUT_REAL_GATEWAY_SECONDS = 90
HEALTH_POLL_INTERVAL_SECONDS = 0.3


def _port_is_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        return sock.connect_ex(("localhost", port)) != 0


def _python_executable_for(name: str) -> str:
    # Most services now have their own isolated .venv (created directly inside their service
    # folder, same convention as STARTUP_GUIDE.md's manual-run steps) so each subprocess gets
    # that service's own installed dependencies instead of whatever happens to be on the global
    # interpreter. Falls back to the global interpreter (this repo's original design) for any
    # service that doesn't have one yet -- both are valid as long as the global interpreter
    # actually has that service's requirements.txt installed, per README.md "Setup".
    venv_python = SERVICE_DIRS[name] / ".venv" / "Scripts" / "python.exe"
    return str(venv_python) if venv_python.exists() else sys.executable


def _wait_for_health(base_url: str, timeout_seconds: float) -> None:
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            response = httpx.get(f"{base_url}/health", timeout=2)
            if response.status_code == 200:
                return
        except httpx.HTTPError as exc:
            last_error = exc
        time.sleep(HEALTH_POLL_INTERVAL_SECONDS)
    raise RuntimeError(
        f"{base_url}/health never returned 200 within {timeout_seconds}s "
        f"(last error: {last_error})"
    )


def start_service(
    name: str,
    port: int,
    env: dict[str, str],
    uses_kafka: bool = False,
    timeout_seconds: float | None = None,
) -> Iterator[str]:
    """Starts one real service subprocess, yields its base_url, tears it down afterward.

    `name` must be a key in SERVICE_DIRS. Fails fast if `port` is already occupied -- most
    likely cause is a service left running from an earlier manual/dev session. `timeout_seconds`
    overrides the uses_kafka-based default health-check timeout when a service's own startup
    cost doesn't fit either bucket (see HEALTH_TIMEOUT_REAL_GATEWAY_SECONDS).
    """
    service_dir = SERVICE_DIRS[name]
    if not _port_is_free(port):
        raise RuntimeError(
            f"Port {port} for '{name}' is already in use -- is another service (from a manual "
            f"dev session, or a previous test run that didn't tear down cleanly) still running "
            f"on it? This suite reserves ports {min(PORTS.values())}-{max(PORTS.values())} for "
            f"itself; free the port and re-run."
        )

    # Written to a real file, not subprocess.PIPE -- a PIPE's buffer is only ever read in the
    # startup-failure branch below; if a service crashes *after* startup succeeds (mid-test,
    # e.g. hitting a real Google API error its own retry logic doesn't cover), that output was
    # previously lost the moment this generator's teardown ran, leaving nothing but a generic
    # "connection refused" at the calling test. A file survives regardless of when/how the
    # subprocess dies.
    LOG_DIR.mkdir(exist_ok=True)
    log_path = LOG_DIR / f"{name}.log"
    log_file = open(log_path, "w", encoding="utf-8")  # noqa: SIM115
    process_env = {**os.environ, **env}
    proc = subprocess.Popen(
        [_python_executable_for(name), "-m", "uvicorn", "app.main:app", "--port", str(port)],
        cwd=service_dir,
        env=process_env,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        text=True,
    )
    base_url = f"http://localhost:{port}"
    if timeout_seconds is not None:
        timeout = timeout_seconds
    else:
        timeout = HEALTH_TIMEOUT_KAFKA_SECONDS if uses_kafka else HEALTH_TIMEOUT_MEMORY_SECONDS
    try:
        _wait_for_health(base_url, timeout)
    except RuntimeError:
        proc.terminate()
        proc.wait(timeout=20)
        log_file.close()
        output = log_path.read_text(encoding="utf-8", errors="replace")
        raise RuntimeError(f"'{name}' failed to become healthy. Output:\n{output}") from None

    try:
        yield base_url
    finally:
        crashed = proc.poll() is not None
        proc.terminate()
        try:
            proc.wait(timeout=20)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=20)
        log_file.close()
        if crashed:
            output = log_path.read_text(encoding="utf-8", errors="replace")
            print(f"\n'{name}' (port {port}) exited on its own before teardown. Output:\n{output}")


GATEWAY_STARTUP_QUOTA_PACING_SECONDS = 8

# This project's single Google service account has a *permanent* free-tier ceiling of 60
# Sheets API requests/minute, shared across every real spreadsheet it touches -- see
# server/gaps-in-services/Pending_Items.md. The Gateway's own startup rebuilds its row index
# with one read per Sheets tab (~37 tabs today), all in a tight burst -- session-scoping this
# fixture means that cost is paid ONCE for the whole test run, not once per test file (which
# would be ~37 calls x however many files, blowing the ceiling before a single test assertion
# runs). See README.md "Real Google Sheets" for the full accounting.


@pytest.fixture(scope="session")
def gateway_url() -> Iterator[str]:
    # No DATA_BACKEND override -- the Gateway's own .env (DATA_BACKEND=google, real spreadsheet
    # IDs/credentials, set up this session) takes over via its own load_dotenv(). Every test in
    # this suite now writes to and reads from the real Google Sheets, not the in-memory
    # stand-in this fixture used to force.
    gen = start_service(
        "gateway", PORTS["gateway"], {}, timeout_seconds=HEALTH_TIMEOUT_REAL_GATEWAY_SECONDS
    )
    base_url = next(gen)
    # Let the startup burst above clear the rolling 60s quota window before any test's own
    # operations add to it.
    time.sleep(GATEWAY_STARTUP_QUOTA_PACING_SECONDS)
    yield base_url
    next(gen, None)


@pytest.fixture(scope="session")
def audit_service_url() -> Iterator[str]:
    yield from start_service(
        "audit",
        PORTS["audit"],
        {
            "EVENT_CONSUMER_MODE": "kafka",
            "KAFKA_BOOTSTRAP_SERVERS": KAFKA_BOOTSTRAP_SERVERS,
        },
        uses_kafka=True,
    )


@pytest.fixture
def business_service(gateway_url: str) -> Any:
    """Factory fixture: business_service("application") starts that service pointed at the
    shared real Gateway and real Kafka, on its reserved port. Function-scoped -- each test gets
    a fresh process even when it shares a module-scoped gateway_url with other tests.
    """

    started: list[Iterator[str]] = []

    def _start(name: str, extra_env: dict[str, str] | None = None) -> str:
        env = {
            "DATA_GATEWAY_MODE": "http",
            "DATA_GATEWAY_URL": gateway_url,
            "EVENT_PUBLISHER_MODE": "kafka",
            "KAFKA_BOOTSTRAP_SERVERS": KAFKA_BOOTSTRAP_SERVERS,
            **(extra_env or {}),
        }
        gen = start_service(name, PORTS[name], env, uses_kafka=True)
        started.append(gen)
        return next(gen)

    yield _start

    for gen in started:
        next(gen, None)  # drives the generator's finally-block teardown


def seed_gateway_record(gateway_url: str, tab: str, fields: dict[str, Any], caller: str) -> None:
    """Writes directly into the real Gateway as the given owning service would -- used to set up
    test preconditions (e.g. a config row) without needing that owning service's own process
    running for tests that aren't specifically exercising it.
    """
    response = httpx.post(
        f"{gateway_url}/records/{tab}",
        json={"fields": fields},
        headers={"X-Caller-Service": caller},
        timeout=20,
    )
    response.raise_for_status()


def seed_gateway_record_if_missing(
    gateway_url: str, tab: str, record_id: str, fields: dict[str, Any], caller: str
) -> None:
    """Same as seed_gateway_record, but for rows addressed by a fixed, literal key (e.g.
    System_Config's "rating_ladder"/"note_types") rather than a fresh UUID per test run.

    Those rows can't be scoped uniquely per test the way seed_gateway_record's UUID-suffixed
    callers are, and against the real, shared Sheet this suite now runs against, re-running the
    suite without this check would accumulate duplicate/ambiguous rows under the same key.

    `record_id` must equal whatever value `fields` puts in that tab's own key column (e.g.
    System_Config's schema is [config_key, config_value, description] -- there's no generic "id"
    column to inject here, every tab's real key column has its own name; the caller's `fields`
    must already set it to `record_id`).
    """
    existing = httpx.get(
        f"{gateway_url}/records/{tab}/{record_id}",
        headers={"X-Caller-Service": caller},
        timeout=20,
    )
    if existing.status_code == 200:
        return
    seed_gateway_record(gateway_url, tab, fields, caller)
