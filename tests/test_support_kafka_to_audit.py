"""Same cross-process pattern as test_application_kafka_to_audit.py, against Support Service --
confirms real Kafka delivery into Audit Service is a repeatable system property, not a fluke of
one service's wiring.
"""

from __future__ import annotations

import time
import uuid

import httpx


def _poll_audit_trail(audit_url: str, target_type: str, target_id: str, timeout_seconds: float = 20):
    deadline = time.monotonic() + timeout_seconds
    last: list = []
    while time.monotonic() < deadline:
        response = httpx.get(
            f"{audit_url}/audit-logs",
            params={"target_type": target_type, "target_id": target_id},
            timeout=5,
        )
        response.raise_for_status()
        last = response.json()
        if last:
            return last
        time.sleep(0.5)
    return last


def test_ticket_created_event_reaches_audit_service(gateway_url, audit_service_url, business_service):
    support_url = business_service("support")

    create_response = httpx.post(
        f"{support_url}/tickets",
        json={
            "raised_by_id": f"STF-{uuid.uuid4().hex[:8]}",
            "subject": "Integration demo ticket",
            "description": "Raised by the cross-service integration suite.",
        },
        timeout=5,
    )
    assert create_response.status_code == 201, create_response.text
    ticket_id = create_response.json()["ticket_id"]
    assert ticket_id

    audit_trail = _poll_audit_trail(audit_service_url, "Ticket", ticket_id)
    assert audit_trail, "ticket.created event never reached Audit Service via Kafka"
    assert audit_trail[0]["action"] == "ticket.created"
    assert audit_trail[0]["target_id"] == ticket_id
