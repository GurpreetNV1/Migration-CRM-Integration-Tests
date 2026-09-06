from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def _create() -> str:
    return client.post(
        "/content-requests",
        json={
            "title": "x",
            "description": "x",
            "request_type": "story",
            "created_by_staff_id": "STF-100",
        },
    ).json()["request_id"]


def test_add_and_list_comments() -> None:
    request_id = _create()

    response = client.post(
        f"/content-requests/{request_id}/comments",
        json={
            "author_id": "STF-100",
            "message": "please clarify the deadline",
            "comment_type": "clarification",
        },
    )
    assert response.status_code == 201
    assert response.json()["comment_type"] == "clarification"

    listed = client.get(f"/content-requests/{request_id}/comments")
    assert listed.status_code == 200
    assert len(listed.json()) == 1


def test_comment_on_unknown_request_returns_404() -> None:
    response = client.post(
        "/content-requests/GRX-999999/comments", json={"author_id": "STF-100", "message": "x"}
    )
    assert response.status_code == 404
