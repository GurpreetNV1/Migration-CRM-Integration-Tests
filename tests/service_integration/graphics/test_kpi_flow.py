from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def test_kpi_summary_reflects_a_completed_request() -> None:
    request_id = client.post(
        "/content-requests",
        json={
            "title": "x",
            "description": "x",
            "request_type": "reel",
            "created_by_staff_id": "STF-KPI",
        },
    ).json()["request_id"]
    client.post(f"/content-requests/{request_id}/accept", json={"designer_staff_id": "STF-KPI-D"})
    client.post(
        f"/content-requests/{request_id}/deliverables",
        files=[("files", ("d.mp4", b"bytes", "video/mp4"))],
        data={"actor_id": "STF-KPI-D"},
    )
    client.post(f"/content-requests/{request_id}/submit-review", json={"actor_id": "STF-KPI-D"})
    client.post(f"/content-requests/{request_id}/approve", json={"actor_id": "STF-KPI"})

    response = client.get("/kpis/summary", params={"created_by_staff_id": "STF-KPI"})
    assert response.status_code == 200
    overview = response.json()["summary"]["overview"]
    assert overview["completed"] >= 1
    assert overview["total"] >= 1


def test_kpi_summary_filters_by_designer() -> None:
    response = client.get("/kpis/summary", params={"designer_id": "no-such-designer"})
    assert response.status_code == 200
    assert response.json()["summary"]["overview"]["total"] == 0
