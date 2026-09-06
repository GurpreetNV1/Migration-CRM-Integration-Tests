import uuid
from datetime import UTC, datetime, timedelta

from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def _future_iso(**delta: float) -> str:
    return (datetime.now(UTC) + timedelta(**delta)).isoformat()


def test_create_manual_reminder_against_a_contact() -> None:
    response = client.post(
        "/reminders",
        json={
            "target_type": "Contact",
            "target_id": "CT-000001",
            "target_label": "Test Person",
            "fire_at": _future_iso(days=1),
            "delivery_channel": "email",
            "staff_id": "STF-000001",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["reminder_id"]
    assert body["source"] == "manual"
    assert body["status"] == "pending"


def test_list_reminders_filters_by_target() -> None:
    # Unique per run rather than the original's fixed "AP-list-1"/"AP-list-2" -- against the
    # real, shared Gateway (this file's own default mode, see conftest.py), a fixed target_id
    # accumulates one more real reminder row every re-run, so an exact-count assertion against it
    # eventually collides with earlier real runs the way a fresh in-memory Gateway never would.
    target_1 = f"AP-list-{uuid.uuid4().hex[:8]}"
    target_2 = f"AP-list-{uuid.uuid4().hex[:8]}"
    client.post(
        "/reminders",
        json={
            "target_type": "Application",
            "target_id": target_1,
            "target_label": "Test App",
            "fire_at": _future_iso(days=2),
            "staff_id": "STF-000001",
        },
    )
    client.post(
        "/reminders",
        json={
            "target_type": "Application",
            "target_id": target_2,
            "target_label": "Other App",
            "fire_at": _future_iso(days=2),
            "staff_id": "STF-000001",
        },
    )

    response = client.get(
        "/reminders", params={"target_type": "Application", "target_id": target_1}
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["target_id"] == target_1


def test_create_manual_reminder_against_a_task_is_rejected() -> None:
    response = client.post(
        "/reminders",
        json={
            "target_type": "Task",
            "target_id": "TK-000001",
            "target_label": "",
            "fire_at": _future_iso(days=1),
            "staff_id": "STF-000001",
        },
    )

    assert response.status_code == 422


def test_create_manual_reminder_with_a_past_fire_at_is_rejected() -> None:
    response = client.post(
        "/reminders",
        json={
            "target_type": "Contact",
            "target_id": "CT-000001",
            "target_label": "",
            "fire_at": "2020-01-01T00:00:00+00:00",
            "staff_id": "STF-000001",
        },
    )

    assert response.status_code == 422


def test_get_reminder_returns_what_was_created() -> None:
    created = client.post(
        "/reminders",
        json={
            "target_type": "Contact",
            "target_id": "CT-000001",
            "target_label": "Test Person",
            "fire_at": _future_iso(days=1),
            "staff_id": "STF-000001",
        },
    ).json()

    response = client.get(f"/reminders/{created['reminder_id']}")

    assert response.status_code == 200
    assert response.json()["reminder_id"] == created["reminder_id"]


def test_get_unknown_reminder_returns_404() -> None:
    assert client.get("/reminders/RM-999999").status_code == 404


def test_cancel_reminder_returns_204_and_removes_it() -> None:
    created = client.post(
        "/reminders",
        json={
            "target_type": "Contact",
            "target_id": "CT-000001",
            "target_label": "Test Person",
            "fire_at": _future_iso(days=1),
            "staff_id": "STF-000001",
        },
    ).json()

    response = client.delete(
        f"/reminders/{created['reminder_id']}", params={"reason": "no longer needed"}
    )

    assert response.status_code == 204
    assert client.get(f"/reminders/{created['reminder_id']}").status_code == 404


def test_cancelling_an_unknown_reminder_is_a_no_op_not_an_error() -> None:
    response = client.delete("/reminders/RM-999999")
    assert response.status_code == 204


def test_firing_sweep_fires_a_due_reminder_end_to_end() -> None:
    # Drives the sweep directly and synchronously (see tests/conftest.py) rather than through
    # the background thread, which never starts under test.
    created = client.post(
        "/reminders",
        json={
            "target_type": "Contact",
            "target_id": "CT-000001",
            "target_label": "Test Person",
            "fire_at": _future_iso(seconds=1),
            "staff_id": "STF-000001",
        },
    ).json()

    result = app.state.reminder_firing_sweep.run_sweep(
        as_of=datetime.now(UTC) + timedelta(seconds=2)
    )

    assert result.fired >= 1
    assert client.get(f"/reminders/{created['reminder_id']}").status_code == 404
