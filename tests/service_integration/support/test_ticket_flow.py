from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def _create(raised_by_id: str = "CT-000001", **overrides: object) -> dict:
    body = {
        "raised_by_id": raised_by_id,
        "subject": "Cannot log in",
        "description": "Password reset link never arrives",
        **overrides,
    }
    response = client.post("/tickets", json=body)
    assert response.status_code == 201
    return response.json()


def _move_to_resolved(ticket_id: str) -> None:
    # OPEN -> RESOLVED isn't a legal direct transition; go through IN_PROGRESS first.
    in_progress = client.post(
        f"/tickets/{ticket_id}/status", json={"next_status": "in_progress", "actor_id": "STF-1"}
    )
    assert in_progress.status_code == 200
    resolved = client.post(
        f"/tickets/{ticket_id}/status", json={"next_status": "resolved", "actor_id": "STF-1"}
    )
    assert resolved.status_code == 200


def test_create_ticket() -> None:
    body = _create()

    assert body["ticket_id"]
    assert body["status"] == "open"
    assert body["subject"] == "Cannot log in"


def test_create_ticket_with_target() -> None:
    body = _create(target_type="Application", target_id="AP-000001", target_label="AP-000001")

    assert body["target_type"] == "Application"
    assert body["target_id"] == "AP-000001"


def test_create_ticket_with_target_type_but_no_target_id_returns_400() -> None:
    response = client.post(
        "/tickets",
        json={
            "raised_by_id": "CT-000001",
            "subject": "x",
            "description": "x",
            "target_type": "Application",
        },
    )
    assert response.status_code == 400


def test_get_ticket_returns_what_was_created() -> None:
    created = _create()

    response = client.get(f"/tickets/{created['ticket_id']}")

    assert response.status_code == 200
    assert response.json()["ticket_id"] == created["ticket_id"]


def test_get_unknown_ticket_returns_404() -> None:
    response = client.get("/tickets/TCK-999999")
    assert response.status_code == 404


def test_list_tickets_filters_by_raised_by_id() -> None:
    created = _create(raised_by_id="CT-777777")

    response = client.get("/tickets", params={"raised_by_id": "CT-777777"})

    assert response.status_code == 200
    assert any(ticket["ticket_id"] == created["ticket_id"] for ticket in response.json())


def test_list_for_target() -> None:
    created = _create(target_type="Contact", target_id="CT-TARGET-1", target_label="CT-TARGET-1")

    response = client.get("/tickets/by-target/Contact/CT-TARGET-1")

    assert response.status_code == 200
    assert any(ticket["ticket_id"] == created["ticket_id"] for ticket in response.json())


def test_full_lifecycle_open_to_closed() -> None:
    created = _create()
    ticket_id = created["ticket_id"]

    in_progress = client.post(
        f"/tickets/{ticket_id}/status", json={"next_status": "in_progress", "actor_id": "STF-1"}
    )
    assert in_progress.status_code == 200
    assert in_progress.json()["status"] == "in_progress"

    resolved = client.post(
        f"/tickets/{ticket_id}/status", json={"next_status": "resolved", "actor_id": "STF-1"}
    )
    assert resolved.status_code == 200
    assert resolved.json()["status"] == "resolved"

    closed = client.post(
        f"/tickets/{ticket_id}/status", json={"next_status": "closed", "actor_id": "STF-1"}
    )
    assert closed.status_code == 200
    assert closed.json()["status"] == "closed"


def test_illegal_transition_returns_409_with_allowed_states() -> None:
    created = _create()
    ticket_id = created["ticket_id"]
    _move_to_resolved(ticket_id)

    response = client.post(
        f"/tickets/{ticket_id}/status", json={"next_status": "in_progress", "actor_id": "STF-1"}
    )

    assert response.status_code == 409
    body = response.json()
    assert body["current_status"] == "resolved"
    assert "in_progress" not in body["allowed_next_states"]


def test_reopen_from_resolved_is_allowed() -> None:
    created = _create()
    ticket_id = created["ticket_id"]
    _move_to_resolved(ticket_id)

    response = client.post(
        f"/tickets/{ticket_id}/reopen", json={"actor_id": "STF-1", "reason": "still broken"}
    )

    assert response.status_code == 200
    assert response.json()["status"] == "open"


def test_reopen_from_closed_is_rejected() -> None:
    created = _create()
    ticket_id = created["ticket_id"]
    client.post(f"/tickets/{ticket_id}/status", json={"next_status": "closed", "actor_id": "STF-1"})

    response = client.post(
        f"/tickets/{ticket_id}/reopen", json={"actor_id": "STF-1", "reason": "try again"}
    )

    assert response.status_code == 409


def test_reassign_ticket() -> None:
    created = _create()

    response = client.post(f"/tickets/{created['ticket_id']}/reassign", json={"staff_id": "STF-42"})

    assert response.status_code == 200
    assert response.json()["assigned_staff_id"] == "STF-42"
