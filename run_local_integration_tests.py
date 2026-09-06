"""Runs the per-service integration tests that physically live in this repo, under
tests/service_integration/<service>/ -- copies of each service's own
server/services/<n>/tests/integration/ (the originals are untouched and keep working exactly as
before via run_service_integration_tests.py).

Unlike that script, these copies are dual-mode, chosen with --gateway-mode:
  real    (default) -- every test runs against a real Data Gateway Service subprocess, which
                        itself writes to real Google Sheets.
  memory            -- fast, in-memory Gateway stand-in, no external dependency (this is the
                        *only* way run_service_integration_tests.py has ever run these tests).

Real mode starts ONE real Gateway subprocess for the whole run (reusing conftest.py's own
start_service/SERVICE_DIRS/PORTS/quota-pacing -- the same machinery the cross-service suite
already relies on) and shares it across every service below, instead of paying its ~30-90s
real-Sheets startup cost once per service.

Each service still runs in its own subprocess using ITS OWN .venv (same convention as
run_service_integration_tests.py) -- only its Gateway dependency becomes real; the service
itself is still exercised in-process via TestClient inside that subprocess.

Usage:
    python run_local_integration_tests.py                       # all services, real Gateway
    python run_local_integration_tests.py --gateway-mode memory # all services, in-memory
    python run_local_integration_tests.py --service support     # just one service
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

import conftest as root_conftest

REPO_ROOT = Path(__file__).resolve().parent
SERVER_ROOT = REPO_ROOT.parent / "server" / "services"
LOCAL_TESTS_ROOT = REPO_ROOT / "tests" / "service_integration"
LOG_DIR = REPO_ROOT / "logs" / "local_integration_test_runs"

# service key -> its original server/services/<n> folder (for cwd + venv resolution, so
# `from app.main import app` in the copied tests/conftest still resolves against that service's
# own code and dependencies).
SERVICE_DIRS = {
    "user": SERVER_ROOT / "01_user_service",
    "application": SERVER_ROOT / "02_application_service",
    "task": SERVER_ROOT / "03_task_service",
    "reminder": SERVER_ROOT / "04_reminder_service",
    "email_draft": SERVER_ROOT / "05_email_draft_service",
    "graphics": SERVER_ROOT / "07_graphics_service",
    "support": SERVER_ROOT / "09_support_service",
    "data_import": SERVER_ROOT / "11_data_import_service",
    "gateway": SERVER_ROOT / "12_data_gateway_service",
    "auth": SERVER_ROOT / "13_auth_service",
    "admin": SERVER_ROOT / "14_admin_module",
    "backup": SERVER_ROOT / "16_backup_restore_service",
    "audit": SERVER_ROOT / "17_audit_service",
    "cleanup": SERVER_ROOT / "18_cleanup_service",
    "notes": SERVER_ROOT / "19_notes_service",
}


def _python_executable_for(service_dir: Path) -> str:
    venv_python = service_dir / ".venv" / "Scripts" / "python.exe"
    return str(venv_python) if venv_python.exists() else sys.executable


def _run_one(name: str, service_dir: Path, env_overrides: dict[str, str], extra_pytest_args: list[str]) -> tuple[bool, str]:
    local_dir = LOCAL_TESTS_ROOT / name
    python = _python_executable_for(service_dir)
    process_env = {**os.environ, **env_overrides}
    result = subprocess.run(
        [python, "-m", "pytest", str(local_dir), "-v", *extra_pytest_args],
        cwd=service_dir,
        env=process_env,
        capture_output=True,
        text=True,
    )
    output = result.stdout + result.stderr
    return result.returncode == 0, output


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the local, dual-mode copies of per-service integration tests."
    )
    parser.add_argument(
        "--service",
        choices=sorted(SERVICE_DIRS),
        help="Run only this one service (default: every service that has a copied test folder).",
    )
    parser.add_argument(
        "--gateway-mode",
        choices=("real", "memory"),
        default="real",
        help="'real' (default): against a real Data Gateway Service / real Sheets. "
        "'memory': fast, in-memory Gateway stand-in, no external dependency.",
    )
    args, extra_pytest_args = parser.parse_known_args()

    targets = (
        {args.service: SERVICE_DIRS[args.service]} if args.service else SERVICE_DIRS
    )
    targets = {
        name: service_dir
        for name, service_dir in targets.items()
        if (LOCAL_TESTS_ROOT / name).exists()
    }
    if not targets:
        print("No copied test folders found under tests/service_integration/ for the requested service(s).")
        return 1

    gateway_gen = None
    env_overrides = {"TEST_GATEWAY_MODE": args.gateway_mode}
    # The Gateway service's own copied tests build their own in-process app directly via
    # load_settings() (see tests/service_integration/gateway/conftest.py) -- they never read
    # TEST_GATEWAY_URL, since this service IS the Gateway, not a caller of one. Starting the
    # shared subprocess here too would mean paying its ~30-90s real-Sheets row-index rebuild
    # burst (~37 tabs) twice in a row for no reason -- confirmed live to blow the account's
    # 60-requests/minute ceiling by itself. Skip it when gateway is the only thing being run.
    needs_shared_gateway = set(targets) != {"gateway"}
    if args.gateway_mode == "real" and needs_shared_gateway:
        print("Starting the real Data Gateway Service (shared across every service below)...")
        gateway_gen = root_conftest.start_service(
            "gateway",
            root_conftest.PORTS["gateway"],
            {},
            timeout_seconds=root_conftest.HEALTH_TIMEOUT_REAL_GATEWAY_SECONDS,
        )
        gateway_url = next(gateway_gen)
        time.sleep(root_conftest.GATEWAY_STARTUP_QUOTA_PACING_SECONDS)
        print(f"Real Gateway up at {gateway_url}")
        env_overrides["TEST_GATEWAY_URL"] = gateway_url

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"{time.strftime('%Y%m%d_%H%M%S')}_{args.gateway_mode}.log"

    results: list[tuple[str, bool]] = []
    try:
        with open(log_path, "w", encoding="utf-8") as log_file:
            for name, service_dir in targets.items():
                started = time.monotonic()
                ok, output = _run_one(name, service_dir, env_overrides, extra_pytest_args)
                elapsed = time.monotonic() - started
                status = "PASS" if ok else "FAIL"
                summary_line = next(
                    (
                        line
                        for line in reversed(output.splitlines())
                        if " in " in line and any(word in line for word in ("passed", "failed", "error"))
                    ),
                    f"exit code {'0' if ok else 'nonzero'}",
                )
                print(f"  [{status}] {name:<12} -- {summary_line}  ({elapsed:.1f}s)")
                log_file.write(f"\n{'-' * 70}\n{name} -- full output\n{'-' * 70}\n{output}\n")
                if not ok:
                    print(output)
                if args.gateway_mode == "real":
                    # A handful of services in a row each making real Sheets calls can add up
                    # to more than 60 requests in under a minute even though no single service
                    # does -- a short gap between services lets the rolling quota window recover,
                    # same reasoning as GATEWAY_STARTUP_QUOTA_PACING_SECONDS above.
                    time.sleep(3)
                results.append((name, ok))
    finally:
        if gateway_gen is not None:
            next(gateway_gen, None)

    failed = [name for name, ok in results if not ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} service suites passed (--gateway-mode={args.gateway_mode}).")
    if failed:
        print("Failed: " + ", ".join(failed))
    print(f"Full log: {log_path}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
