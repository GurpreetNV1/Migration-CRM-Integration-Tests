from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def _complete_request() -> str:
    request_id = client.post(
        "/content-requests",
        json={
            "title": "x",
            "description": "x",
            "request_type": "reel",
            "created_by_staff_id": "STF-100",
        },
    ).json()["request_id"]
    client.post(f"/content-requests/{request_id}/accept", json={"designer_staff_id": "STF-200"})
    client.post(
        f"/content-requests/{request_id}/deliverables",
        files=[("files", ("d.mp4", b"bytes", "video/mp4"))],
        data={"actor_id": "STF-200"},
    )
    client.post(f"/content-requests/{request_id}/submit-review", json={"actor_id": "STF-200"})
    client.post(f"/content-requests/{request_id}/approve", json={"actor_id": "STF-100"})
    return request_id


def test_publish_completed_request_to_multiple_platforms() -> None:
    request_id = _complete_request()

    response = client.post(
        f"/content-requests/{request_id}/publish", json={"platforms": ["instagram", "facebook"]}
    )
    assert response.status_code == 200
    outcomes = {o["platform"]: o["success"] for o in response.json()["outcomes"]}
    assert outcomes == {"instagram": True, "facebook": True}

    updated = client.get(f"/content-requests/{request_id}").json()
    assert updated["published_platforms"] == {"instagram": "published", "facebook": "published"}


def test_publish_rejected_for_non_completed_request() -> None:
    request_id = client.post(
        "/content-requests",
        json={
            "title": "x",
            "description": "x",
            "request_type": "reel",
            "created_by_staff_id": "STF-100",
        },
    ).json()["request_id"]

    response = client.post(
        f"/content-requests/{request_id}/publish", json={"platforms": ["instagram"]}
    )
    assert response.status_code == 409


def test_publish_to_unknown_platform_returns_400() -> None:
    request_id = _complete_request()
    response = client.post(
        f"/content-requests/{request_id}/publish", json={"platforms": ["myspace"]}
    )
    assert response.status_code == 400
