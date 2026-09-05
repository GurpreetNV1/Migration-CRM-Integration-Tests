"""Shared plumbing for run_unit_tests.py and run_service_integration_tests.py -- both are thin
orchestrators over each built service's own already-existing pytest suite, differing only in
which subfolder (tests/unit/ vs tests/integration/) they point at. Not a test itself; nothing here
is collected by pytest.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

SERVER_ROOT = Path(__file__).resolve().parent.parent / "server" / "services"
LOG_ROOT = Path(__file__).resolve().parent / "logs"

# Every service with at least one real test in either tests/unit/ or tests/integration/.
# 05_email_draft_service has no real business logic yet (just a bare health check) and no
# tests/unit/ content at all -- callers building the unit-only runner should exclude it.
ALL_SERVICE_DIRS = {
    "gateway": SERVER_ROOT / "12_data_gateway_service",
    "email_draft": SERVER_ROOT / "05_email_draft_service",
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


def _python_executable_for(service_dir: Path) -> str:
    # Prefer that service's isolated .venv, fall back to whatever interpreter is running this
    # script -- same rule this repo's own conftest.py uses for the cross-service suite.
    venv_python = service_dir / ".venv" / "Scripts" / "python.exe"
    return str(venv_python) if venv_python.exists() else sys.executable


class _Tee:
    """Prints to stdout and appends to an open log file at the same time, flushing immediately
    so a run that's interrupted partway still leaves a complete log up to that point -- not
    buffered in memory and lost if the process is killed mid-run.
    """

    def __init__(self, log_file) -> None:  # noqa: ANN001
        self._log_file = log_file

    def __call__(self, message: str = "") -> None:
        print(message)
        self._log_file.write(message + "\n")
        self._log_file.flush()

    def log_only(self, message: str = "") -> None:
        # File only, no console print -- for the full per-test detail we always want saved but
        # don't want flooding the terminal on a routine passing run.
        self._log_file.write(message + "\n")
        self._log_file.flush()


def _run_one(
    name: str, service_dir: Path, test_subpath: str, extra_args: list[str], log: _Tee
) -> tuple[bool, str, float]:
    python = _python_executable_for(service_dir)
    started = time.monotonic()
    result = subprocess.run(
        # -v so every individual test's PASSED/FAILED line (not just the aggregate count) is in
        # the captured output -- always saved to the log file below, regardless of outcome.
        [python, "-m", "pytest", test_subpath, "-v", *extra_args],
        cwd=service_dir,
        capture_output=True,
        text=True,
    )
    elapsed = time.monotonic() - started
    output = result.stdout + result.stderr
    summary_line = next(
        (
            line
            for line in reversed(output.splitlines())
            if " in " in line and ("passed" in line or "failed" in line or "error" in line)
        ),
        f"exit code {result.returncode}",
    )

    header = f"\n{'-' * 70}\n{name} ({service_dir.name}) -- full pytest output\n{'-' * 70}"
    log.log_only(header)
    log.log_only(output)
    if result.returncode != 0:
        # Also surface it on-screen immediately -- a failure's detail shouldn't require opening
        # the log file, only a passing run's per-test detail is file-only.
        print(header)
        print(output)

    return result.returncode == 0, summary_line.strip(), elapsed


def run(service_dirs: dict[str, Path], test_subpath: str, label: str, log_subdir: str) -> int:
    parser = argparse.ArgumentParser(description=f"Run every built service's {label}.")
    parser.add_argument(
        "--service",
        choices=sorted(service_dirs),
        help="Run only this one service instead of all of them.",
    )
    args, extra_args = parser.parse_known_args()

    targets = {args.service: service_dirs[args.service]} if args.service else service_dirs

    log_dir = LOG_ROOT / log_subdir
    log_dir.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    log_path = log_dir / f"{timestamp}.log"

    with open(log_path, "w", encoding="utf-8") as log_file:
        log = _Tee(log_file)
        log(f"Run started {time.strftime('%Y-%m-%d %H:%M:%S')} -- {label}, {len(targets)} service(s)")
        log("")

        results: list[tuple[str, bool, str, float]] = []
        for name, service_dir in targets.items():
            ok, summary, elapsed = _run_one(name, service_dir, test_subpath, extra_args, log)
            results.append((name, ok, summary, elapsed))
            status = "PASS" if ok else "FAIL"
            log(f"  [{status}] {name:<12} ({service_dir.name}) -- {summary}  ({elapsed:.1f}s)")

        total_elapsed = sum(r[3] for r in results)
        failed = [r for r in results if not r[1]]

        log(f"\n{'=' * 70}")
        log(
            f"{len(targets) - len(failed)}/{len(targets)} service suites passed in "
            f"{total_elapsed:.1f}s total"
        )
        if failed:
            log("Failed: " + ", ".join(r[0] for r in failed))
        log(f"{'=' * 70}")

    print(f"\nFull log saved to: {log_path}")
    return 1 if failed else 0
