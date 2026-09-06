from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def _create(request_type: str = "story", **overrides) -> dict:
    payload = {
        "title": "Test request",
        "description": "A description",
        "request_type": request_type,
        "created_by_staff_id": "STF-100",
    }
    payload.update(overrides)
    response = client.post("/content-requests", json=payload)
    assert response.status_code == 201
    return response.json()


def test_create_request_defaults_to_pending() -> None:
    body = _create()
    assert body["request_id"]
    assert body["status"] == "pending"
    assert body["assigned_designer_staff_id"] is None


def test_get_request_returns_what_was_created() -> None:
    created = _create()
    response = client.get(f"/content-requests/{created['request_id']}")
    assert response.status_code == 200
    assert response.json()["request_id"] == created["request_id"]


def test_get_unknown_request_returns_404() -> None:
    response = client.get("/content-requests/GRX-999999")
    assert response.status_code == 404


def test_list_requests_filters_by_status() -> None:
    created = _create()
    response = client.get("/content-requests", params={"status": "pending"})
    assert response.status_code == 200
    assert any(r["request_id"] == created["request_id"] for r in response.json())


def test_accept_request_assigns_designer_and_moves_to_in_progress() -> None:
    created = _create()
    response = client.post(
        f"/content-requests/{created['request_id']}/accept", json={"designer_staff_id": "STF-200"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "in_progress"
    assert body["assigned_designer_staff_id"] == "STF-200"


def test_update_request_applies_partial_fields() -> None:
    created = _create()
    response = client.patch(
        f"/content-requests/{created['request_id']}",
        json={"actor_id": "STF-100", "title": "New title", "priority": "urgent"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "New title"
    assert body["priority"] == "urgent"
    assert body["description"] == created["description"]  # untouched field preserved


def test_update_request_after_cancellation_is_rejected() -> None:
    created = _create()
    client.post(f"/content-requests/{created['request_id']}/cancel", json={"actor_id": "STF-100"})
    response = client.patch(
        f"/content-requests/{created['request_id']}", json={"actor_id": "STF-100", "title": "nope"}
    )
    assert response.status_code == 409


def test_cancel_request_twice_is_rejected() -> None:
    created = _create()
    first = client.post(
        f"/content-requests/{created['request_id']}/cancel", json={"actor_id": "STF-100"}
    )
    assert first.status_code == 200
    second = client.post(
        f"/content-requests/{created['request_id']}/cancel", json={"actor_id": "STF-100"}
    )
    assert second.status_code == 409
