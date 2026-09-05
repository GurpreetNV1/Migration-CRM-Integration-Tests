"""Real cross-process proof: Application Service publishes a real Kafka event, and a separately
running Audit Service (its own real Kafka consumer) picks it up and makes it queryable over its
own real HTTP API. Three real OS processes (Gateway, Audit Service, Application Service), one
real local Kafka broker -- no TestClient, no in-memory stand-ins anywhere in this path.

Services used: Data Gateway Service, Application Service, Audit Service (plus real Kafka).
"""

from __future__ import annotations

import time
import uuid

import httpx

from conftest import seed_gateway_record
from gateway_retry import call_with_quota_backoff


def _poll_audit_trail(audit_url: str, target_type: str, target_id: str, timeout_seconds: float = 20):
    deadline = time.monotonic() + timeout_seconds
    last: list = []
    while time.monotonic() < deadline:
        response = call_with_quota_backoff(
            lambda: httpx.get(
                f"{audit_url}/audit-logs",
                params={"target_type": target_type, "target_id": target_id},
                timeout=20,
            )
        )
        response.raise_for_status()
        last = response.json()
        if last:
            return last
        time.sleep(0.5)
    return last


def test_application_created_event_reaches_audit_service(gateway_url, audit_service_url, business_service):
    # Application Service refuses to create an application for a visa_type with no seeded
    # Application_Type_Field_Schemas row (Admin-Module-owned config) -- seed it directly as
    # admin-module would, since this test is about Kafka delivery, not Admin Module itself.
    visa_type = f"VISITOR-{uuid.uuid4().hex[:8]}"
    seed_gateway_record(
        gateway_url,
        "Application_Type_Field_Schemas",
        {"visa_type": visa_type, "allowed_dynamic_fields_json": "{}"},
        caller="admin-module",
    )

    application_url = business_service("application")

    create_response = httpx.post(
        f"{application_url}/applications",
        json={
            "primary_applicant_contact_id": f"CT-{uuid.uuid4().hex[:8]}",
            "visa_type": visa_type,
            "dynamic_fields": {},
        },
        timeout=20,
    )
    assert create_response.status_code == 201, create_response.text
    application_id = create_response.json()["application_id"]
    assert application_id

    audit_trail = _poll_audit_trail(audit_service_url, "Application", application_id)
    assert audit_trail, "application.created event never reached Audit Service via Kafka"
    assert audit_trail[0]["action"] == "application.created"
    assert audit_trail[0]["target_id"] == application_id
