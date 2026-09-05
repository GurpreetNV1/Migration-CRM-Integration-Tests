"""Flagship real-Kafka flow: Application Service's full client-registration gate (signature +
invoice + payment, exactly what the client-facing UI drives) advances a real Application to
stage 2, publishing a real "application.stage_changed" event over a real local Kafka broker.
Task Service consumes it and auto-creates a real Task -- proving the event-contract fix made
this session (the real event only ever carries application_id/from_stage/to_stage, not the
follow_up_due_date/assigned_staff_id fields the original rule assumed) actually works end to end,
against real Sheets and real Drive, not the in-memory/mocked path each service's own test suite
uses. Also confirms Audit Service saw the same event via its own real Kafka consumption.

Services used: Data Gateway Service, User Service, Application Service, Task Service, Audit
Service (plus real Kafka) -- the most services any single test in this suite exercises together.
"""

from __future__ import annotations

import json
import time
import uuid

import httpx

from conftest import seed_gateway_record, seed_gateway_record_if_missing
from gateway_retry import call_with_quota_backoff

# Each poll here reads through the real Gateway (Application + compliance-status rows), so a
# single check already costs 4-6s of real Sheets round-trip on a slow day -- confirmed live, a
# run this test previously passed reliably failed once with only ~5 iterations fitting in a 25s
# budget. Widened for headroom against that latency variance, not because the flow is slow.
POLL_INTERVAL_SECONDS = 1.0
POLL_TIMEOUT_SECONDS = 45

# User Service's contact-creation path (hit below) requires this config to exist, same as
# test_user_contact_rating_against_real_config.py. This test used to silently rely on that other
# file already having seeded it -- true only by accident of alphabetical run order and years of
# leftover real Sheets state. Confirmed live: it breaks the moment the sheets are ever cleared,
# since this file runs before that one. Seeding it here too (idempotently) removes that hidden
# cross-file, run-order dependency entirely.
RATING_LADDER_DEFAULT = ["Lost", "Cold", "Warm", "Hot"]


def _poll_until(predicate, timeout_seconds: float = POLL_TIMEOUT_SECONDS):
    deadline = time.monotonic() + timeout_seconds
    last = None
    while time.monotonic() < deadline:
        last = predicate()
        if last:
            return last
        time.sleep(POLL_INTERVAL_SECONDS)
    return last


def test_full_registration_gate_publishes_stage_changed_and_task_service_creates_a_task(
    gateway_url, business_service, audit_service_url
):
    visa_type = f"VISA-{uuid.uuid4().hex[:8]}"
    seed_gateway_record(
        gateway_url,
        "Application_Type_Field_Schemas",
        {"id": visa_type, "visa_type": visa_type, "allowed_dynamic_fields_json": json.dumps([])},
        caller="admin-module",
    )
    seed_gateway_record_if_missing(
        gateway_url,
        "System_Config",
        "rating_ladder",
        {
            "config_key": "rating_ladder",
            "config_value": json.dumps(RATING_LADDER_DEFAULT),
            "description": "",
        },
        caller="admin-module",
    )

    user_url = business_service("user")
    application_url = business_service(
        "application", extra_env={"USER_SERVICE_MODE": "http", "USER_SERVICE_URL": user_url}
    )
    task_url = business_service("task", extra_env={"EVENT_CONSUMER_MODE": "kafka"})

    contact = call_with_quota_backoff(
        lambda: httpx.post(
            f"{user_url}/contacts/enquiries",
            json={
                "source": "Form",
                "full_name": f"Gate Flow {uuid.uuid4().hex[:8]}",
                "primary_email": f"{uuid.uuid4().hex[:8]}@example.com",
            },
            timeout=20,
        )
    )
    assert contact.status_code == 201, contact.text
    contact_id = contact.json()["contact_id"]

    application = call_with_quota_backoff(
        lambda: httpx.post(
            f"{application_url}/applications",
            json={
                "primary_applicant_contact_id": contact_id,
                "visa_type": visa_type,
                "dynamic_fields": {},
            },
            timeout=20,
        )
    )
    assert application.status_code == 201, application.text
    application_id = application.json()["application_id"]

    signature_request = httpx.post(
        f"{application_url}/applications/{application_id}/registration/signature-request",
        timeout=30,
    )
    assert signature_request.status_code == 202, signature_request.text

    # pending_signature_reference isn't in ApplicationResponse (only a signature_requested bool
    # is) -- read the real row straight from the Gateway, same pattern used to confirm this
    # exact flow by hand earlier this session.
    app_record = call_with_quota_backoff(
        lambda: httpx.get(
            f"{gateway_url}/records/Application/{application_id}",
            headers={"X-Caller-Service": "application-service"},
            timeout=20,
        )
    )
    assert app_record.status_code == 200, app_record.text
    provider_reference = app_record.json()["fields"]["pending_signature_reference"]
    assert provider_reference

    webhook_payload = json.dumps(
        {"event": {"eventType": "Completed"}, "data": {"documentId": provider_reference}}
    )
    webhook_response = httpx.post(
        f"{application_url}/applications/registration/signature-webhook",
        content=webhook_payload,
        headers={"Content-Type": "application/json"},
        timeout=30,
    )
    assert webhook_response.status_code == 200, webhook_response.text

    def _gate_status() -> dict | None:
        response = call_with_quota_backoff(
            lambda: httpx.get(
                f"{application_url}/applications/{application_id}/registration/gate-status",
                timeout=20,
            )
        )
        response.raise_for_status()
        body = response.json()
        return body if body["form_956_uploaded"] and body["client_agreement_uploaded"] else None

    signed = _poll_until(_gate_status)
    assert signed is not None, "both documents were never marked signed within the timeout"

    invoice = httpx.post(
        f"{application_url}/applications/{application_id}/registration/invoice",
        json={"amount": 500},
        timeout=30,
    )
    assert invoice.status_code == 201, invoice.text
    invoice_id = invoice.json()["invoice_id"]

    payment_webhook = httpx.post(
        f"{application_url}/applications/registration/payment-webhook",
        content=json.dumps({"invoice_id": invoice_id, "provider_reference": "prov-ref"}),
        headers={"Content-Type": "application/json"},
        timeout=30,
    )
    assert payment_webhook.status_code == 200, payment_webhook.text

    def _gate_satisfied() -> dict | None:
        response = call_with_quota_backoff(
            lambda: httpx.get(
                f"{application_url}/applications/{application_id}/registration/gate-status",
                timeout=20,
            )
        )
        response.raise_for_status()
        body = response.json()
        return body if body["gate_satisfied"] else None

    satisfied = _poll_until(_gate_satisfied)
    assert satisfied is not None, "registration gate was never satisfied within the timeout"

    final_application = httpx.get(f"{application_url}/applications/{application_id}", timeout=20)
    assert final_application.status_code == 200, final_application.text
    assert final_application.json()["stage"] == 2  # confirms advance_stage really ran

    # Task Service consumed the real "application.stage_changed" Kafka event and auto-created a
    # real Task -- this is the fixed behavior; before today's fix, TaskCreationRulesEvaluator's
    # rule expected fields the real event never sends, so this always came back empty.
    def _task_created() -> list | None:
        response = call_with_quota_backoff(
            lambda: httpx.get(
                f"{task_url}/tasks",
                params={"target_type": "Application", "target_id": application_id},
                timeout=20,
            )
        )
        response.raise_for_status()
        body = response.json()
        return body if body else None

    tasks = _poll_until(_task_created)
    assert tasks, "Task Service never created a task for the stage-changed event"
    assert tasks[0]["target_type"] == "Application"
    assert tasks[0]["target_id"] == application_id
    assert tasks[0]["status"] == "open"

    # Audit Service saw the same real event too.
    def _audit_has_stage_changed() -> list | None:
        response = call_with_quota_backoff(
            lambda: httpx.get(
                f"{audit_service_url}/audit-logs",
                params={"target_type": "Application", "target_id": application_id},
                timeout=20,
            )
        )
        response.raise_for_status()
        body = response.json()
        matches = [entry for entry in body if entry["action"] == "application.stage_changed"]
        return matches if matches else None

    audit_entries = _poll_until(_audit_has_stage_changed)
    assert audit_entries, "Audit Service never recorded the application.stage_changed event"
