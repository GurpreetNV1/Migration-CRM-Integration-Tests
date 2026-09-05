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


def _run_one(
    name: str, service_dir: Path, test_subpath: str, extra_args: list[str]
) -> tuple[bool, str, float]:
    python = _python_executable_for(service_dir)
    started = time.monotonic()
    result = subprocess.run(
        [python, "-m", "pytest", test_subpath, *extra_args],
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
    if result.returncode != 0:
        print(f"\n{'=' * 70}\nFAILURE DETAIL: {name} ({service_dir.name})\n{'=' * 70}")
        print(output)
    return result.returncode == 0, summary_line.strip(), elapsed


def run(service_dirs: dict[str, Path], test_subpath: str, label: str) -> int:
    parser = argparse.ArgumentParser(description=f"Run every built service's {label}.")
    parser.add_argument(
        "--service",
        choices=sorted(service_dirs),
        help="Run only this one service instead of all of them.",
    )
    args, extra_args = parser.parse_known_args()

    targets = {args.service: service_dirs[args.service]} if args.service else service_dirs

    print(f"Running {label} for {len(targets)} service(s)...\n")
    results: list[tuple[str, bool, str, float]] = []
    for name, service_dir in targets.items():
        ok, summary, elapsed = _run_one(name, service_dir, test_subpath, extra_args)
        results.append((name, ok, summary, elapsed))
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {name:<12} ({service_dir.name}) -- {summary}  ({elapsed:.1f}s)")

    total_elapsed = sum(r[3] for r in results)
    failed = [r for r in results if not r[1]]

    print(f"\n{'=' * 70}")
    print(
        f"{len(targets) - len(failed)}/{len(targets)} service suites passed in "
        f"{total_elapsed:.1f}s total"
    )
    if failed:
        print("Failed: " + ", ".join(r[0] for r in failed))
    print(f"{'=' * 70}")

    return 1 if failed else 0
