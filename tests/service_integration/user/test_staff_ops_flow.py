from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def _seed_staff_once() -> None:
    gateway = app.state.gateway
    if gateway.get_by_id("Staff", "STF-000001") is None:
        gateway.create(
            "Staff",
            {
                "id": "STF-000001",
                "staff_id": "STF-000001",
                "name": "Requester",
                "email": "requester@example.com",
                "office_id": "OFF-000001",
                "role_tier": "Consultant",
                "active": True,
            },
        )
    if gateway.get_by_id("Staff", "STF-000002") is None:
        gateway.create(
            "Staff",
            {
                "id": "STF-000002",
                "staff_id": "STF-000002",
                "name": "Approver",
                "email": "approver@example.com",
                "office_id": "OFF-000001",
                # "Director" was fully consolidated into "Owner" during this project's RBAC
                # simplification (New_Integrations_2026-09-16.md section 5).
                "role_tier": "Owner",
                "active": True,
            },
        )
    # AdminModuleRoleHierarchyProvider (what RoleHierarchyApproverResolver actually calls) always
    # reads through app.state.admin_module_client, not app.state.gateway directly -- found live
    # 2026-09-17: seeding Role_Hierarchy straight into the gateway here was a no-op as far as
    # ApproverResolver's own get_hierarchy_level lookups are concerned in memory mode, so every
    # leave-request test 404'd with "No approver available".
    admin_module_client = app.state.admin_module_client
    if hasattr(admin_module_client, "seed_role_hierarchy"):
        admin_module_client.seed_role_hierarchy("Consultant", 1)
        admin_module_client.seed_role_hierarchy("Owner", 3)
    else:
        if gateway.get_by_id("Role_Hierarchy", "Consultant") is None:
            gateway.create(
                "Role_Hierarchy", {"role_tier": "Consultant", "hierarchy_level": 1}
            )
        if gateway.get_by_id("Role_Hierarchy", "Owner") is None:
            gateway.create(
                "Role_Hierarchy", {"role_tier": "Owner", "hierarchy_level": 3}
            )


_seed_staff_once()


def test_check_in_then_check_out() -> None:
    check_in = client.post(
        "/staff/STF-000001/attendance",
        json={"date": "2026-09-01", "action": "check_in", "time": "09:00"},
    )
    assert check_in.status_code == 201
    assert check_in.json()["check_in_time"] == "09:00"

    check_out = client.post(
        "/staff/STF-000001/attendance",
        json={"date": "2026-09-01", "action": "check_out", "time": "17:00"},
    )
    assert check_out.status_code == 201
    body = check_out.json()
    assert body["check_in_time"] == "09:00"
    assert body["check_out_time"] == "17:00"


def test_get_attendance_range() -> None:
    client.post(
        "/staff/STF-000001/attendance",
        json={"date": "2026-09-02", "action": "check_in", "time": "09:00"},
    )

    response = client.get(
        "/staff/STF-000001/attendance",
        params={"start": "2026-09-02", "end": "2026-09-02"},
    )

    assert response.status_code == 200
    assert len(response.json()) == 1


def test_submit_leave_request_routes_to_the_office_director() -> None:
    response = client.post(
        "/leave-requests",
        json={
            "staff_id": "STF-000001",
            "start_date": "2026-09-10",
            "end_date": "2026-09-12",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["approver_id"] == "STF-000002"
    assert body["status"] == "Requested"


def test_submit_leave_request_with_bad_date_range_returns_422() -> None:
    response = client.post(
        "/leave-requests",
        json={
            "staff_id": "STF-000001",
            "start_date": "2026-09-12",
            "end_date": "2026-09-10",
        },
    )
    assert response.status_code == 422


def test_decide_leave_request() -> None:
    submitted = client.post(
        "/leave-requests",
        json={
            "staff_id": "STF-000001",
            "start_date": "2026-09-15",
            "end_date": "2026-09-16",
        },
    ).json()

    response = client.patch(
        f"/leave-requests/{submitted['leave_request_id']}/decision",
        json={"decision": "Approved", "note": "enjoy", "decided_by": "STF-000002"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "Approved"
    assert body["decision_note"] == "enjoy"


def test_get_salary_with_no_attendance_data_returns_zero() -> None:
    response = client.get("/staff/STF-000001/salary", params={"period": "2099-01"})

    assert response.status_code == 200
    body = response.json()
    assert body["calculated_salary"] == 0.0
    assert body["basis_note"] == "no attendance data for period"
