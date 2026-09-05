"""Runs ONLY the true unit tests (`tests/unit/`) for every built service -- one class/function at
a time, everything else mocked or faked. The fastest, cheapest tier: no Kafka, no Gateway (real or
in-memory), no HTTP at all.

For that same service's own `tests/integration/` suite (still in-memory, but exercises the real
HTTP routes via FastAPI's TestClient), use `run_service_integration_tests.py` instead. For the
real cross-service suite (real subprocesses, real Kafka, real Google Sheets/Drive), use
`pytest tests/ -v` in this same folder. See TESTING_GUIDE.md for the full picture of all three.

Usage:
    python run_unit_tests.py                  # every built service with unit tests
    python run_unit_tests.py --service task    # just one (see ALL_SERVICE_DIRS in
                                                # _test_runner_common.py for every valid name)
    python run_unit_tests.py -v                # any extra args are passed through to pytest
"""

from __future__ import annotations

from _test_runner_common import ALL_SERVICE_DIRS, run

# 05_email_draft_service has no tests/unit/ content at all (just a bare health check, covered
# under tests/integration/) -- excluded here, included in run_service_integration_tests.py.
SERVICE_DIRS = {name: path for name, path in ALL_SERVICE_DIRS.items() if name != "email_draft"}

if __name__ == "__main__":
    raise SystemExit(run(SERVICE_DIRS, "tests/unit/", "unit tests"))
