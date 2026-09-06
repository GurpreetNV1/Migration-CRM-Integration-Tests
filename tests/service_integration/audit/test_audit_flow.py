import uuid
from datetime import UTC, datetime

from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def make_event(target_id: str, action: str = "contact.created") -> dict:
    return {
        "event_id": f"evt-{target_id}-{action}",
        "source_service": "user-service",
        "actor_id": "STF-000001",
        "action": action,
        "target_type": "Contact",
        "target_id": target_id,
        "occurred_at_utc": datetime.now(UTC).isoformat(),
        "detail_json": {"note": "test"},
    }


def test_ingest_event_returns_202() -> None:
    response = client.post("/audit-events", json=make_event("CT-100001"))
    assert response.status_code == 202


def test_ingested_event_appears_in_the_audit_trail_after_force_flush() -> None:
    # Unique per run rather than the original's fixed "CT-100002" -- against the real, shared
    # Gateway (this file's own default mode, see conftest.py), Audit_Log rows are genuine,
    # persistent real rows across runs, so an exact-count assertion against a fixed target_id
    # would collide with the same test's own earlier real runs, unlike a fresh in-memory Gateway.
    target_id = f"CT-{uuid.uuid4().hex[:8]}"
    client.post("/audit-events", json=make_event(target_id))
    app.state.buffer.force_flush()

    response = client.get(
        "/audit-logs", params={"target_type": "Contact", "target_id": target_id}
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["action"] == "contact.created"


def test_audit_trail_missing_target_type_returns_400() -> None:
    response = client.get("/audit-logs", params={"target_id": "CT-100002"})
    assert response.status_code == 400


def test_audit_trail_missing_target_id_returns_400() -> None:
    response = client.get("/audit-logs", params={"target_type": "Contact"})
    assert response.status_code == 400


def test_malformed_ingested_event_is_dead_lettered_and_never_flushed() -> None:
    payload = make_event("CT-100003")
    del payload["actor_id"]

    response = client.post("/audit-events", json=payload)

    # Pydantic itself rejects the missing required field before it reaches the consumer --
    # confirms the schema-level guard is doing its job too.
    assert response.status_code == 422


def test_multiple_events_batch_and_flush_together() -> None:
    # Unique per run -- see test_ingested_event_appears_in_the_audit_trail_after_force_flush
    # above for why a fixed target_id doesn't survive repeat real runs.
    target_id = f"CT-{uuid.uuid4().hex[:8]}"
    for i in range(3):
        client.post("/audit-events", json=make_event(target_id, action=f"action-{i}"))
    app.state.buffer.force_flush()

    response = client.get(
        "/audit-logs", params={"target_type": "Contact", "target_id": target_id}
    )

    assert response.status_code == 200
    assert len(response.json()) == 3
