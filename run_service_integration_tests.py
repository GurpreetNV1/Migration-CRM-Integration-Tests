"""Runs ONLY each built service's own `tests/integration/` suite -- these hit the real FastAPI
HTTP routes via TestClient, but everything runs in one process against that service's in-memory
Data Gateway stand-in (a plain Python dict standing in for Google Sheets). No Kafka, no real
network socket, no real Google API calls.

This is a DIFFERENT thing from this repo's own true cross-service suite (`pytest tests/ -v`),
which starts real `uvicorn` subprocesses, a real local Kafka broker, and a real Google
Sheets/Drive-backed Gateway. See TESTING_GUIDE.md's "Three kinds of testing" section for the full
comparison and why the split exists.

Usage:
    python run_service_integration_tests.py                  # every built service, plus
                                                               # Email Draft's one health check
    python run_service_integration_tests.py --service task    # just one
    python run_service_integration_tests.py -v                # extra args pass through to pytest
"""

from __future__ import annotations

from _test_runner_common import ALL_SERVICE_DIRS, run

if __name__ == "__main__":
    raise SystemExit(run(ALL_SERVICE_DIRS, "tests/integration/", "in-memory integration tests"))
