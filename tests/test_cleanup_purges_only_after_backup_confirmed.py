"""Real cross-process safety net: Cleanup Service will only purge aged rows once Backup &
Restore Service confirms (over a real HTTP call) that a full backup covers them. Seeds one
successful Backup_Run_Log row directly (never calls the real, expensive /backup/trigger), plus
one genuinely old (past the 365-day Audit_Log retention window) and one recent Audit_Log row.
Cleanup Service has no REST surface at all (LLD: no inbound callers) -- it's started with a
short scheduler interval and terminated immediately after its own effect is observed directly
in the real Gateway, so its background thread never gets a second cycle to run.
"""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime, timedelta

import httpx

from conftest import PORTS, seed_gateway_record, start_service

# Same real-latency margin issue confirmed in test_task_stage_change_creates_task.py: a poll that
# reads through the real Gateway can alone cost 4-6s on a slow day, leaving too little room in a
# tight 20s budget.
POLL_INTERVAL_SECONDS = 1.0
POLL_TIMEOUT_SECONDS = 40


def _poll_until(predicate, timeout_seconds: float = POLL_TIMEOUT_SECONDS):
    deadline = time.monotonic() + timeout_seconds
    last = None
    while time.monotonic() < deadline:
        last = predicate()
        if last:
            return last
        time.sleep(POLL_INTERVAL_SECONDS)
    return last


def test_cleanup_purges_the_old_row_and_leaves_the_recent_one(gateway_url, business_service):
    now = datetime.now(UTC)
    old_audit_id = f"AUD-{uuid.uuid4().hex[:8]}"
    recent_audit_id = f"AUD-{uuid.uuid4().hex[:8]}"

    # A confirmed-successful full backup, completed just now -- covers everything up to today.
    seed_gateway_record(
        gateway_url,
        "Backup_Run_Log",
        {
            "id": f"BK-{uuid.uuid4().hex[:8]}",
            "run_type": "full_backup",
            "started_at": (now - timedelta(minutes=5)).isoformat(),
            "completed_at": now.isoformat(),
            "status": "succeeded",
            "source_scope": "full_account",
            "destination_ref": "test-seeded",
            "error_message": "",
        },
        caller="backup-restore-service",
    )

    # Genuinely past the 365-day Audit_Log retention window -- a real purge candidate.
    seed_gateway_record(
        gateway_url,
        "Audit_Log",
        {
            "id": old_audit_id,
            "audit_id": old_audit_id,
            "actor_id": "system",
            "action": "test.seeded_old_entry",
            "target_type": "Test",
            "target_id": "irrelevant",
            "target_label": "",
            "timestamp": (now - timedelta(days=400)).isoformat(),
            "detail_json": "{}",
        },
        caller="audit-service",
    )
    # Well within retention -- must survive as a negative control.
    seed_gateway_record(
        gateway_url,
        "Audit_Log",
        {
            "id": recent_audit_id,
            "audit_id": recent_audit_id,
            "actor_id": "system",
            "action": "test.seeded_recent_entry",
            "target_type": "Test",
            "target_id": "irrelevant",
            "target_label": "",
            "timestamp": now.isoformat(),
            "detail_json": "{}",
        },
        caller="audit-service",
    )

    backup_url = business_service("backup")

    # Cleanup Service has no REST surface -- start it directly via start_service (not the
    # business_service factory, whose Kafka-mode assumptions don't apply here) with a short
    # scheduler interval, then terminate it as soon as the purge is observed so its background
    # thread never gets a second cycle.
    cleanup_gen = start_service(
        "cleanup",
        PORTS["cleanup"],
        {
            "DATA_GATEWAY_MODE": "http",
            "DATA_GATEWAY_URL": gateway_url,
            "BACKUP_CHECK_MODE": "http",
            "BACKUP_RESTORE_SERVICE_URL": backup_url,
            "START_CLEANUP_SCHEDULER": "true",
            "CLEANUP_INTERVAL_SECONDS": "2",
        },
    )
    next(cleanup_gen)
    try:

        def _old_row_purged() -> bool:
            response = httpx.get(
                f"{gateway_url}/records/Audit_Log/{old_audit_id}",
                headers={"X-Caller-Service": "audit-service"},
                timeout=20,
            )
            return response.status_code == 404

        purged = _poll_until(_old_row_purged)
        assert purged, "the old Audit_Log row was never purged within the timeout"

        # Negative control: the recent row must still be there.
        recent_response = httpx.get(
            f"{gateway_url}/records/Audit_Log/{recent_audit_id}",
            headers={"X-Caller-Service": "audit-service"},
            timeout=20,
        )
        assert recent_response.status_code == 200, (
            "the recent Audit_Log row was purged too -- retention window check is broken"
        )
    finally:
        next(cleanup_gen, None)  # stop it immediately, don't let a second cycle run
