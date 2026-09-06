from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def _create_and_accept(request_type: str = "banner", **overrides) -> str:
    payload = {
        "title": "Test",
        "description": "x",
        "request_type": request_type,
        "created_by_staff_id": "STF-100",
    }
    payload.update(overrides)
    request_id = client.post("/content-requests", json=payload).json()["request_id"]
    client.post(f"/content-requests/{request_id}/accept", json={"designer_staff_id": "STF-200"})
    return request_id


def _upload_deliverable(request_id: str, filename: str = "d.png") -> None:
    response = client.post(
        f"/content-requests/{request_id}/deliverables",
        files=[("files", (filename, b"bytes", "image/png"))],
        data={"actor_id": "STF-200"},
    )
    assert response.status_code == 200


def test_submit_for_review_requires_in_progress_or_changes_requested() -> None:
    request_id = _create_and_accept()
    response = client.post(
        f"/content-requests/{request_id}/submit-review", json={"actor_id": "STF-200"}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "review"


def test_approve_by_creator_completes_the_request() -> None:
    request_id = _create_and_accept()
    _upload_deliverable(request_id)
    client.post(f"/content-requests/{request_id}/submit-review", json={"actor_id": "STF-200"})

    response = client.post(f"/content-requests/{request_id}/approve", json={"actor_id": "STF-100"})
    assert response.status_code == 200
    assert response.json()["status"] == "completed"


def test_approve_by_wrong_actor_is_rejected() -> None:
    request_id = _create_and_accept()
    client.post(f"/content-requests/{request_id}/submit-review", json={"actor_id": "STF-200"})

    response = client.post(f"/content-requests/{request_id}/approve", json={"actor_id": "STF-999"})
    assert response.status_code == 403


def test_request_changes_then_resubmit_and_approve() -> None:
    request_id = _create_and_accept()
    client.post(f"/content-requests/{request_id}/submit-review", json={"actor_id": "STF-200"})

    changes = client.post(
        f"/content-requests/{request_id}/request-changes",
        json={"actor_id": "STF-100", "reason": "wrong colors"},
    )
    assert changes.status_code == 200
    assert changes.json()["status"] == "changes_requested"

    _upload_deliverable(request_id, "d2.png")
    resubmit = client.post(
        f"/content-requests/{request_id}/submit-review", json={"actor_id": "STF-200"}
    )
    assert resubmit.status_code == 200
    assert resubmit.json()["status"] == "review"

    approve = client.post(f"/content-requests/{request_id}/approve", json={"actor_id": "STF-100"})
    assert approve.status_code == 200
    assert approve.json()["status"] == "completed"


def test_video_request_routes_approval_to_client_not_creator() -> None:
    request_id = _create_and_accept(
        request_type="video", pii_masking_applied=True, client_approver_contact_id="CT-1"
    )
    client.post(f"/content-requests/{request_id}/submit-review", json={"actor_id": "STF-200"})

    creator_attempt = client.post(
        f"/content-requests/{request_id}/approve", json={"actor_id": "STF-100"}
    )
    assert creator_attempt.status_code == 403

    client_attempt = client.post(
        f"/content-requests/{request_id}/approve", json={"actor_id": "CT-1"}
    )
    assert client_attempt.status_code == 200
    assert client_attempt.json()["status"] == "completed"
