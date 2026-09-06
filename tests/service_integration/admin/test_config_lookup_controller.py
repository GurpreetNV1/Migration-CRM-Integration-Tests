from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def test_get_role_hierarchy_reflects_rows_created_via_the_admin_surface() -> None:
    client.post(
        "/admin/config/RoleHierarchy",
        json={
            "data": {
                "role_tier": "Lookup-Tier",
                "hierarchy_level": 1,
                "allowed_consultants": ["U1"],
            }
        },
    )

    response = client.get("/config/role-hierarchy")

    assert response.status_code == 200
    matching = [row for row in response.json() if row["role_tier"] == "Lookup-Tier"]
    assert matching == [
        {"role_tier": "Lookup-Tier", "hierarchy_level": 1, "allowed_consultants": ["U1"]}
    ]


def test_get_system_config_value_returns_the_stored_value() -> None:
    client.post(
        "/admin/config/SystemConfig",
        json={"data": {"config_key": "lookup_window_days", "config_value": "7"}},
    )

    response = client.get("/config/system-config/lookup_window_days")

    assert response.status_code == 200
    assert response.json() == {"config_key": "lookup_window_days", "config_value": "7"}


def test_get_system_config_value_for_a_missing_key_returns_404() -> None:
    response = client.get("/config/system-config/no-such-key")
    assert response.status_code == 404


def test_get_application_type_field_schema_returns_the_stored_schema() -> None:
    client.post(
        "/admin/config/ApplicationTypeFieldSchema",
        json={"data": {"visa_type": "Lookup-189", "allowed_dynamic_fields": {"age": "int"}}},
    )

    response = client.get("/config/application-type-schema/Lookup-189")

    assert response.status_code == 200
    assert response.json()["allowed_dynamic_fields"] == {"age": "int"}


def test_get_active_rfi_types_excludes_deactivated_rows() -> None:
    client.post(
        "/admin/config/RFITypeConfig",
        json={"data": {"rfi_type_key": "lookup-active", "label": "Active"}},
    )
    client.post(
        "/admin/config/RFITypeConfig",
        json={"data": {"rfi_type_key": "lookup-inactive", "label": "Inactive"}},
    )
    client.delete("/admin/config/RFITypeConfig/lookup-inactive")

    response = client.get("/config/rfi-types/active")

    keys = {row["rfi_type_key"] for row in response.json()}
    assert "lookup-active" in keys
    assert "lookup-inactive" not in keys


def test_get_active_notification_types_excludes_deactivated_rows() -> None:
    client.post(
        "/admin/config/NotificationTypeConfig",
        json={"data": {"notification_type_key": "lookup-notif-active", "label": "Active"}},
    )
    client.post(
        "/admin/config/NotificationTypeConfig",
        json={"data": {"notification_type_key": "lookup-notif-inactive", "label": "Inactive"}},
    )
    client.delete("/admin/config/NotificationTypeConfig/lookup-notif-inactive")

    response = client.get("/config/notification-types/active")

    keys = {row["notification_type_key"] for row in response.json()}
    assert "lookup-notif-active" in keys
    assert "lookup-notif-inactive" not in keys


def test_get_active_compliance_checklist_filters_by_active_and_applies_to() -> None:
    client.post(
        "/admin/config/ComplianceChecklistItem",
        json={
            "data": {
                "checklist_key": "lookup-passport",
                "label": "Passport",
                "applies_to": "189-lookup",
            }
        },
    )
    client.post(
        "/admin/config/ComplianceChecklistItem",
        json={
            "data": {"checklist_key": "lookup-visa", "label": "Visa", "applies_to": "482-lookup"}
        },
    )

    response = client.get("/config/compliance-checklist/189-lookup")

    keys = {row["checklist_key"] for row in response.json()}
    assert keys == {"lookup-passport"}


def test_get_discount_coupon_looks_up_by_code_not_by_coupon_id() -> None:
    client.post(
        "/admin/config/DiscountCoupon",
        json={
            "data": {
                "code": "LOOKUPCODE",
                "type": "discount",
                "discount_type": "percentage",
                "discount_value": 15,
                "issued_at": "2026-01-01T00:00:00+00:00",
            }
        },
    )

    response = client.get("/config/discount-coupon/LOOKUPCODE")

    assert response.status_code == 200
    assert response.json()["code"] == "LOOKUPCODE"
    assert response.json()["coupon_id"]


def test_get_discount_coupon_for_a_missing_code_returns_404() -> None:
    response = client.get("/config/discount-coupon/NO-SUCH-CODE")
    assert response.status_code == 404
