import uuid

from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)
TASK_CALLER = {"X-Caller-Service": "task-service"}


def test_create_record_allocates_a_gateway_id() -> None:
    response = client.post(
        "/records/Task", json={"fields": {"status": "open"}}, headers=TASK_CALLER
    )

    assert response.status_code == 201
    body = response.json()
    assert body["record_id"].startswith("TK-")
    assert body["fields"]["status"] == "open"


def test_get_record_returns_what_was_created() -> None:
    created = client.post(
        "/records/Task", json={"fields": {"status": "open"}}, headers=TASK_CALLER
    ).json()

    response = client.get(f"/records/Task/{created['record_id']}", headers=TASK_CALLER)

    assert response.status_code == 200
    assert response.json()["record_id"] == created["record_id"]


def test_get_unknown_record_returns_404() -> None:
    response = client.get("/records/Task/TK-999999", headers=TASK_CALLER)
    assert response.status_code == 404


def test_get_record_is_not_restricted_to_the_owning_caller() -> None:
    created = client.post(
        "/records/Task", json={"fields": {"status": "open"}}, headers=TASK_CALLER
    ).json()

    response = client.get(
        f"/records/Task/{created['record_id']}",
        headers={"X-Caller-Service": "application-service"},
    )

    assert response.status_code == 200


def test_create_with_wrong_caller_returns_403() -> None:
    response = client.post(
        "/records/Task",
        json={"fields": {"status": "open"}},
        headers={"X-Caller-Service": "application-service"},
    )
    assert response.status_code == 403


def test_unregistered_tab_returns_404() -> None:
    response = client.post("/records/NotARealTab", json={"fields": {}}, headers=TASK_CALLER)
    assert response.status_code == 404


def test_update_record_overwrites_fields() -> None:
    created = client.post(
        "/records/Task", json={"fields": {"status": "open"}}, headers=TASK_CALLER
    ).json()

    response = client.put(
        f"/records/Task/{created['record_id']}",
        json={"fields": {"status": "done"}},
        headers=TASK_CALLER,
    )

    assert response.status_code == 200
    assert response.json()["fields"]["status"] == "done"


def test_batch_get_preserves_requested_order() -> None:
    first = client.post(
        "/records/Task", json={"fields": {"status": "open"}}, headers=TASK_CALLER
    ).json()
    second = client.post(
        "/records/Task", json={"fields": {"status": "done"}}, headers=TASK_CALLER
    ).json()

    response = client.post(
        "/records/Task/batch-get",
        json={"record_ids": [second["record_id"], first["record_id"]]},
        headers=TASK_CALLER,
    )

    assert response.status_code == 200
    body = response.json()
    assert [r["record_id"] for r in body] == [second["record_id"], first["record_id"]]


def test_query_records_with_no_filters_returns_everything_in_the_tab() -> None:
    client.post("/records/Task", json={"fields": {"status": "open"}}, headers=TASK_CALLER)
    client.post("/records/Task", json={"fields": {"status": "done"}}, headers=TASK_CALLER)

    response = client.post("/records/Task/query", json={}, headers=TASK_CALLER)

    assert response.status_code == 200
    assert len(response.json()) >= 2


def test_query_records_filters_by_field() -> None:
    # Unique per run rather than the original's fixed "blocked-for-query-test" -- against the
    # real, shared Gateway (this file's own default mode, see conftest.py), the Task tab is a
    # genuine, persistent real tab across runs, so a fixed status value would collide with the
    # same test's own earlier real runs, unlike a fresh in-memory Gateway.
    status_value = f"blocked-for-query-test-{uuid.uuid4().hex[:8]}"
    client.post("/records/Task", json={"fields": {"status": "open"}}, headers=TASK_CALLER)
    unique = client.post(
        "/records/Task", json={"fields": {"status": status_value}}, headers=TASK_CALLER
    ).json()

    response = client.post(
        "/records/Task/query",
        json={"filters": {"status": status_value}},
        headers=TASK_CALLER,
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["record_id"] == unique["record_id"]


def test_query_records_is_not_restricted_to_the_owning_caller() -> None:
    # System_Design.md section 6: ownership is a write restriction ("no service can write
    # into another service's sheet") -- config-driven tabs are meant to be read by every
    # service, so a non-owning caller querying a tab is not a 403.
    response = client.post(
        "/records/Task/query",
        json={},
        headers={"X-Caller-Service": "application-service"},
    )
    assert response.status_code == 200


def test_delete_record_soft_deletes_by_default() -> None:
    created = client.post(
        "/records/Contact",
        json={"fields": {"full_name": "Test Person"}},
        headers={"X-Caller-Service": "user-service"},
    ).json()

    response = client.delete(
        f"/records/Contact/{created['record_id']}",
        headers={"X-Caller-Service": "user-service"},
    )
    assert response.status_code == 204

    fetched = client.get(
        f"/records/Contact/{created['record_id']}",
        headers={"X-Caller-Service": "user-service"},
    ).json()
    assert fetched["fields"]["is_deleted"] is True


def test_delete_record_hard_deletes_when_requested() -> None:
    created = client.post(
        "/records/Task", json={"fields": {"status": "open"}}, headers=TASK_CALLER
    ).json()

    response = client.delete(f"/records/Task/{created['record_id']}?hard=true", headers=TASK_CALLER)
    assert response.status_code == 204

    fetched = client.get(f"/records/Task/{created['record_id']}", headers=TASK_CALLER)
    assert fetched.status_code == 404
