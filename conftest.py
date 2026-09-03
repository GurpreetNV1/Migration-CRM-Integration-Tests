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

SERVICE_DIRS = {
    "gateway": SERVER_ROOT / "12_data_gateway_service",
    "audit": SERVER_ROOT / "17_audit_service",
    "application": SERVER_ROOT / "02_application_service",
    "support": SERVER_ROOT / "09_support_service",
    "admin": SERVER_ROOT / "14_admin_module",
    "graphics": SERVER_ROOT / "07_graphics_service",
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
}

KAFKA_BOOTSTRAP_SERVERS = "localhost:9092"

# Kafka-mode services do a synchronous broker round-trip (KafkaProducer/KafkaConsumer
# construction) at startup, which dominates their startup time -- see
# server/services/02_application_service/app/services/event_publisher.py. Memory-only services
# (the Gateway) never touch Kafka, so they come up in a couple seconds.
HEALTH_TIMEOUT_KAFKA_SECONDS = 30
HEALTH_TIMEOUT_MEMORY_SECONDS = 15
HEALTH_POLL_INTERVAL_SECONDS = 0.3


def _port_is_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        return sock.connect_ex(("localhost", port)) != 0


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
    name: str, port: int, env: dict[str, str], uses_kafka: bool = False
) -> Iterator[str]:
    """Starts one real service subprocess, yields its base_url, tears it down afterward.

    `name` must be a key in SERVICE_DIRS. Fails fast if `port` is already occupied -- most
    likely cause is a service left running from an earlier manual/dev session.
    """
    service_dir = SERVICE_DIRS[name]
    if not _port_is_free(port):
        raise RuntimeError(
            f"Port {port} for '{name}' is already in use -- is another service (from a manual "
            f"dev session, or a previous test run that didn't tear down cleanly) still running "
            f"on it? This suite reserves ports {min(PORTS.values())}-{max(PORTS.values())} for "
            f"itself; free the port and re-run."
        )

    process_env = {**os.environ, **env}
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(port)],
        cwd=service_dir,
        env=process_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    base_url = f"http://localhost:{port}"
    timeout = HEALTH_TIMEOUT_KAFKA_SECONDS if uses_kafka else HEALTH_TIMEOUT_MEMORY_SECONDS
    try:
        _wait_for_health(base_url, timeout)
    except RuntimeError:
        proc.terminate()
        output = proc.communicate(timeout=5)[0] if proc.stdout else ""
        raise RuntimeError(f"'{name}' failed to become healthy. Output:\n{output}") from None

    try:
        yield base_url
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)


@pytest.fixture(scope="module")
def gateway_url() -> Iterator[str]:
    # Explicit DATA_BACKEND=memory: the Gateway's own .env (left over from earlier real-Sheets
    # testing) sets DATA_BACKEND=google, but load_dotenv() never overrides an already-set env
    # var, so setting it here before the process starts keeps it off real Google APIs.
    yield from start_service("gateway", PORTS["gateway"], {"DATA_BACKEND": "memory"})


@pytest.fixture(scope="module")
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
        timeout=5,
    )
    response.raise_for_status()
