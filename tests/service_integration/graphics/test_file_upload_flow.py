from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def _create() -> str:
    return client.post(
        "/content-requests",
        json={
            "title": "x",
            "description": "x",
            "request_type": "reel",
            "created_by_staff_id": "STF-100",
        },
    ).json()["request_id"]


def test_upload_raw_files_updates_stats_and_timestamp() -> None:
    request_id = _create()
    response = client.post(
        f"/content-requests/{request_id}/raw-files",
        files=[("files", ("a.mp4", b"bytes", "video/mp4"))],
        data={"actor_id": "STF-200"},
    )
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["file_role"] == "raw"

    updated = client.get(f"/content-requests/{request_id}").json()
    assert updated["raw_file_count"] == 1
    assert updated["raw_uploaded_at"] is not None


def test_deliverables_upload_rejected_before_designer_accepts() -> None:
    request_id = _create()
    response = client.post(
        f"/content-requests/{request_id}/deliverables",
        files=[("files", ("d.png", b"bytes", "image/png"))],
        data={"actor_id": "STF-200"},
    )
    assert response.status_code == 409


def test_deliverables_upload_allowed_once_in_progress() -> None:
    request_id = _create()
    client.post(f"/content-requests/{request_id}/accept", json={"designer_staff_id": "STF-200"})
    response = client.post(
        f"/content-requests/{request_id}/deliverables",
        files=[("files", ("d.png", b"bytes", "image/png"))],
        data={"actor_id": "STF-200"},
    )
    assert response.status_code == 200

    updated = client.get(f"/content-requests/{request_id}").json()
    assert updated["deliverables_file_count"] == 1


def test_upload_rejected_once_cancelled() -> None:
    request_id = _create()
    client.post(f"/content-requests/{request_id}/cancel", json={"actor_id": "STF-100"})
    response = client.post(
        f"/content-requests/{request_id}/raw-files",
        files=[("files", ("a.mp4", b"bytes", "video/mp4"))],
        data={"actor_id": "STF-200"},
    )
    assert response.status_code == 409


def test_multiple_files_in_one_upload_all_saved() -> None:
    request_id = _create()
    response = client.post(
        f"/content-requests/{request_id}/raw-files",
        files=[
            ("files", ("a.mp4", b"bytes", "video/mp4")),
            ("files", ("b.mp4", b"more-bytes", "video/mp4")),
        ],
        data={"actor_id": "STF-200"},
    )
    assert response.status_code == 200
    assert len(response.json()) == 2
    assert client.get(f"/content-requests/{request_id}").json()["raw_file_count"] == 2
