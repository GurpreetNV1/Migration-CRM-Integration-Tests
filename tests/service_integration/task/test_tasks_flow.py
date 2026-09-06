import uuid

from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def _seed_contact(full_name: str = "Test Person") -> str:
    # Unique per call rather than the original's fixed "CT-000001" -- against the real, shared
    # Gateway (this file's own default mode, see conftest.py), "CT-000001" is a genuine
    # long-lived contact from earlier real usage, not a blank slate the way a fresh in-memory
    # Gateway always is, so reusing a fixed id here would silently read back someone else's data
    # instead of what this test just seeded.
    gateway = app.state.gateway
    contact_id = f"CT-{uuid.uuid4().hex[:8]}"
    # "id" is what the in-memory Gateway stand-in keys records by (see
    # data_gateway_client/in_memory_mock.py's create()); "contact_id" is the real Data Gateway
    # Service's actual key column for this tab (see 12_data_gateway_service/app/config.py's
    # TAB_SCHEMAS) -- both point at the same value so this seed works identically in either mode.
    gateway.create("Contact", {"id": contact_id, "contact_id": contact_id, "full_name": full_name})
    return contact_id


def _seed_application(visa_type: str = "Skilled Migration") -> str:
    # Same reasoning as _seed_contact above -- unique per call, not the original's fixed
    # "AP-000001".
    gateway = app.state.gateway
    application_id = f"AP-{uuid.uuid4().hex[:8]}"
    gateway.create(
        "Application",
        {"id": application_id, "application_id": application_id, "visa_type": visa_type},
    )
    return application_id


def test_create_task_against_a_contact() -> None:
    contact_id = _seed_contact()

    response = client.post(
        "/tasks",
        json={
            "target_type": "Contact",
            "target_id": contact_id,
            "due_date": "2026-09-10",
            "assigned_staff_id": "STF-000001",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["task_id"]
    assert body["target_label"] == "Test Person"
    assert body["status"] == "open"


def test_create_task_against_an_application() -> None:
    application_id = _seed_application()

    response = client.post(
        "/tasks",
        json={
            "target_type": "Application",
            "target_id": application_id,
            "due_date": "2026-09-12",
            "assigned_staff_id": "STF-000001",
        },
    )

    assert response.status_code == 201
    assert response.json()["target_label"] == f"Skilled Migration ({application_id})"


def test_create_task_against_a_missing_target_returns_404() -> None:
    response = client.post(
        "/tasks",
        json={
            "target_type": "Contact",
            "target_id": "CT-999999",
            "due_date": "2026-09-10",
            "assigned_staff_id": "STF-000001",
        },
    )

    assert response.status_code == 404


def test_create_task_with_an_unsupported_target_type_returns_422() -> None:
    response = client.post(
        "/tasks",
        json={
            "target_type": "Ticket",
            "target_id": "TCK-000001",
            "due_date": "2026-09-10",
            "assigned_staff_id": "STF-000001",
        },
    )

    assert response.status_code == 422


def test_get_task_returns_what_was_created() -> None:
    contact_id = _seed_contact()
    created = client.post(
        "/tasks",
        json={
            "target_type": "Contact",
            "target_id": contact_id,
            "due_date": "2026-09-10",
            "assigned_staff_id": "STF-000001",
        },
    ).json()

    response = client.get(f"/tasks/{created['task_id']}")

    assert response.status_code == 200
    assert response.json()["task_id"] == created["task_id"]


def test_get_unknown_task_returns_404() -> None:
    response = client.get("/tasks/TK-999999")
    assert response.status_code == 404


def test_list_tasks_filters_by_assigned_staff_id() -> None:
    contact_id = _seed_contact()
    created = client.post(
        "/tasks",
        json={
            "target_type": "Contact",
            "target_id": contact_id,
            "due_date": "2026-09-10",
            "assigned_staff_id": "STF-777777",
        },
    ).json()

    response = client.get("/tasks", params={"assigned_staff_id": "STF-777777"})

    assert response.status_code == 200
    body = response.json()
    assert any(task["task_id"] == created["task_id"] for task in body)


def test_update_task_status_to_done() -> None:
    contact_id = _seed_contact()
    created = client.post(
        "/tasks",
        json={
            "target_type": "Contact",
            "target_id": contact_id,
            "due_date": "2026-09-10",
            "assigned_staff_id": "STF-000001",
        },
    ).json()

    response = client.post(f"/tasks/{created['task_id']}/status", json={"status": "done"})

    assert response.status_code == 200
    assert response.json()["status"] == "done"


def test_reassign_task() -> None:
    contact_id = _seed_contact()
    created = client.post(
        "/tasks",
        json={
            "target_type": "Contact",
            "target_id": contact_id,
            "due_date": "2026-09-10",
            "assigned_staff_id": "STF-000001",
        },
    ).json()

    response = client.post(
        f"/tasks/{created['task_id']}/reassign", json={"assigned_staff_id": "STF-000002"}
    )

    assert response.status_code == 200
    assert response.json()["assigned_staff_id"] == "STF-000002"
