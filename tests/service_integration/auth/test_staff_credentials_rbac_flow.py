import uuid

from app.main import app
from app.models import StaffRef
from fastapi.testclient import TestClient

client = TestClient(app)


def _seed_role_hierarchy_once() -> None:
    # Real deployment's actual 3 tiers post-consolidation (Owner=3, Admin=2, Consultant=1) -- see
    # New_Integrations_2026-09-16.md section 13 and this session's Role_Hierarchy cleanup.
    # InMemoryAdminModuleClient.seed_role_hierarchy_level is a plain dict overwrite, safe to call
    # more than once.
    admin_module_client = app.state.admin_module_client
    admin_module_client.seed_role_hierarchy_level("Owner", 3)
    admin_module_client.seed_role_hierarchy_level("Admin", 2)
    admin_module_client.seed_role_hierarchy_level("Consultant", 1)


_seed_role_hierarchy_once()


def _seed_staff(role_tier: str) -> str:
    staff_id = f"STF-{uuid.uuid4().hex[:8]}"
    app.state.user_service_client.seed_staff(
        StaffRef(staff_id=staff_id, name="Test Staff", role_tier=role_tier)
    )
    return staff_id


def test_missing_caller_header_returns_422() -> None:
    response = client.post(
        "/auth/staff-credentials",
        json={"staff_id": "STF-000001", "password": "Sup3rSecret!"},
    )

    assert response.status_code == 422


def test_unknown_caller_is_forbidden() -> None:
    response = client.post(
        "/auth/staff-credentials",
        json={"staff_id": "STF-000001", "password": "Sup3rSecret!"},
        headers={"X-Caller-Id": "STF-does-not-exist"},
    )

    assert response.status_code == 403


def test_consultant_caller_is_forbidden() -> None:
    caller_id = _seed_staff("Consultant")
    target_id = _seed_staff("Consultant")

    response = client.post(
        "/auth/staff-credentials",
        json={"staff_id": target_id, "password": "Sup3rSecret!"},
        headers={"X-Caller-Id": caller_id},
    )

    assert response.status_code == 403


def test_admin_caller_can_provision_another_staff_members_credentials() -> None:
    caller_id = _seed_staff("Admin")
    target_id = _seed_staff("Consultant")

    response = client.post(
        "/auth/staff-credentials",
        json={"staff_id": target_id, "password": "Sup3rSecret!"},
        headers={"X-Caller-Id": caller_id},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["staff_id"] == target_id
    assert body["account_type"] == "Staff"

    # The provisioned credentials actually work for the real phone-login path too.
    login = client.post(
        "/auth/login", json={"identifier": target_id, "password": "Sup3rSecret!"}
    )
    assert login.status_code == 200


def test_owner_caller_can_provision_another_staff_members_credentials() -> None:
    caller_id = _seed_staff("Owner")
    target_id = _seed_staff("Consultant")

    response = client.post(
        "/auth/staff-credentials",
        json={"staff_id": target_id, "password": "Sup3rSecret!"},
        headers={"X-Caller-Id": caller_id},
    )

    assert response.status_code == 200
