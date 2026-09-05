"""Real cross-process proof of this session's Data Import fix: a submitted job must always reach
a real terminal status (completed, or a clean failed with a recorded reason) -- never get stuck
at "processing" forever. Against the real Gateway's actual ownership rules, importing into
"Contact" (owned exclusively by user-service, per TAB_OWNERSHIP) is a genuine 403 for this
service (it always identifies itself as "data-import-service"), so this specifically exercises
the fixed failure path: before the fix, write_reconciled_batch's exception had no handler and
ThreadPoolJobRunner's fire-and-forget submit() meant nobody ever recorded it.
"""

from __future__ import annotations

import time
import uuid

import httpx

from gateway_retry import call_with_quota_backoff

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


def test_a_submitted_job_never_hangs_at_processing(gateway_url, business_service):
    data_import_url = business_service("data_import")

    submitted = call_with_quota_backoff(
        lambda: httpx.post(
            f"{data_import_url}/import-jobs",
            json={
                "source_type": "csv",
                "submitted_by": f"STF-{uuid.uuid4().hex[:8]}",
                "target_entity_type": "Contact",
                "field_map": {"Name": "full_name", "Email": "primary_email"},
                "raw_input": f"Name,Email\r\nJane {uuid.uuid4().hex[:6]},jane@example.com\r\n",
            },
            timeout=20,
        )
    )
    assert submitted.status_code == 202, submitted.text
    job_id = submitted.json()["import_job_id"]
    assert submitted.json()["status"] in ("queued", "processing")

    def _reached_terminal_status() -> dict | None:
        # A 503 here can be the real Gateway's own quota ceiling (this service proxies its own
        # reads through it) -- ride it out the same way the initial submit above does, rather
        # than letting a transient quota block fail this poll outright.
        response = call_with_quota_backoff(
            lambda: httpx.get(f"{data_import_url}/import-jobs/{job_id}", timeout=20)
        )
        response.raise_for_status()
        body = response.json()
        return body if body["status"] in ("completed", "failed") else None

    final = _poll_until(_reached_terminal_status)
    assert final is not None, (
        "job never reached a terminal status within the timeout -- it's stuck at "
        "queued/processing, which is exactly the bug this fix was meant to close"
    )

    # "Contact" is owned exclusively by user-service in the real Gateway's TAB_OWNERSHIP, and
    # this service always identifies itself as "data-import-service" -- a real 403 is the
    # expected, correct outcome here, and the fix's job is to make sure it's recorded cleanly
    # rather than silently hanging.
    if final["status"] == "failed":
        report = httpx.get(f"{data_import_url}/import-jobs/{job_id}/report", timeout=20)
        assert report.status_code == 200, report.text
        assert report.json()["errors"], "job failed but recorded no reason"
    else:
        assert final["status"] == "completed"
