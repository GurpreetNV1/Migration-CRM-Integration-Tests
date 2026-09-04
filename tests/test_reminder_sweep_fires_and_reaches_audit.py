"""Reminder Service's own real periodic sweep engine against real Sheets + real Kafka publish.
No live cross-service Kafka producer currently targets Reminder Service's own consumer rule
(nothing publishes "reminder.schedule_requested" today outside the per-service in-memory tests --
see reminder_schedule_rules.py), so this proves the service's own real, scheduled behavior
instead: a manually-created reminder with a near-future fire_at (ReminderCreationService rejects
a fire_at already in the past -- InvalidFireAtError, real validation, not something this test can
work around) actually becomes due and gets picked up by a real background sweep thread, moved
from Reminders_Pending to Reminders_History in real Sheets, and reaches Audit Service as a
correctly-attributed real Kafka event -- one envelope per reminder, not a single batch event with
no usable target_id.
"""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime, timedelta

import httpx

from gateway_retry import call_with_quota_backoff

POLL_INTERVAL_SECONDS = 1.0
POLL_TIMEOUT_SECONDS = 20


def _poll_until(predicate, timeout_seconds: float = POLL_TIMEOUT_SECONDS):
    deadline = time.monotonic() + timeout_seconds
    last = None
    while time.monotonic() < deadline:
        last = predicate()
        if last:
            return last
        time.sleep(POLL_INTERVAL_SECONDS)
    return last


def test_a_due_reminder_fires_and_lands_in_audit(gateway_url, business_service, audit_service_url):
    reminder_url = business_service(
        "reminder",
        extra_env={
            "SWEEP_INTERVAL_SECONDS": "2",
            "START_SWEEP_SCHEDULER": "true",
        },
    )

    target_id = f"CT-{uuid.uuid4().hex[:8]}"
    # Must be a real future timestamp at creation time -- ReminderCreationService's own
    # InvalidFireAtError rejects anything already in the past. A few seconds out is enough for
    # it to become genuinely due well within the 2s sweep interval below.
    near_future_fire_at = (datetime.now(UTC) + timedelta(seconds=3)).isoformat()

    created = call_with_quota_backoff(
        lambda: httpx.post(
            f"{reminder_url}/reminders",
            json={
                "target_type": "Contact",
                "target_id": target_id,
                "target_label": "Reminder Sweep Test",
                "fire_at": near_future_fire_at,
                "delivery_channel": "email",
                "staff_id": f"STF-{uuid.uuid4().hex[:8]}",
            },
            timeout=20,
        )
    )
    assert created.status_code == 201, created.text
    reminder_id = created.json()["reminder_id"]
    assert created.json()["status"] == "pending"

    def _reminder_no_longer_pending() -> bool:
        response = httpx.get(f"{reminder_url}/reminders/{reminder_id}", timeout=20)
        # A fired reminder is removed from Reminders_Pending entirely (see
        # ReminderRepository.remove_from_pending) -- 404 here means the sweep already fired it.
        return response.status_code == 404

    fired = _poll_until(_reminder_no_longer_pending)
    assert fired, "the due reminder was never picked up by the real sweep within the timeout"

    def _audit_has_fired_entry() -> list | None:
        response = call_with_quota_backoff(
            lambda: httpx.get(
                f"{audit_service_url}/audit-logs",
                params={"target_type": "Reminder", "target_id": reminder_id},
                timeout=20,
            )
        )
        response.raise_for_status()
        body = response.json()
        matches = [entry for entry in body if entry["action"] == "reminder.fired_batch"]
        return matches if matches else None

    audit_entries = _poll_until(_audit_has_fired_entry)
    assert audit_entries, (
        "Audit Service never recorded a reminder.fired_batch entry correctly attributed to "
        f"reminder_id={reminder_id} -- if this fails, check whether the batch-explode-into-"
        "per-reminder-envelope logic in event_publisher.py regressed"
    )
    assert audit_entries[0]["target_id"] == reminder_id
