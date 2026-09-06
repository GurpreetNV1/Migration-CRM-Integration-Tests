import uuid

from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def test_create_role_hierarchy_then_read_it_back() -> None:
    # Unique per run rather than the original's fixed "Tier-A" -- RoleHierarchy rows are keyed
    # by role_tier and rejected as a 409 duplicate on re-create (see the next test below); against
    # the real, shared Gateway (this file's own default mode, see conftest.py) that key is a
    # genuine, persistent real row across runs, unlike a fresh in-memory Gateway.
    role_tier = f"Tier-{uuid.uuid4().hex[:8]}"
    response = client.post(
        "/admin/config/RoleHierarchy",
        json={"data": {"role_tier": role_tier, "hierarchy_level": 1, "allowed_consultants": []}},
    )
    assert response.status_code == 201
    assert response.json()["data"]["role_tier"] == role_tier

    response = client.get(f"/admin/config/RoleHierarchy/{role_tier}")
    assert response.status_code == 200
    assert response.json()["data"]["hierarchy_level"] == 1


def test_create_role_hierarchy_rejects_a_duplicate_role_tier() -> None:
    client.post(
        "/admin/config/RoleHierarchy",
        json={"data": {"role_tier": "Tier-B", "hierarchy_level": 1, "allowed_consultants": []}},
    )

    response = client.post(
        "/admin/config/RoleHierarchy",
        json={"data": {"role_tier": "Tier-B", "hierarchy_level": 2, "allowed_consultants": []}},
    )

    assert response.status_code == 409


def test_get_config_for_a_missing_key_returns_404() -> None:
    response = client.get("/admin/config/RoleHierarchy/NoSuchTier")
    assert response.status_code == 404


def test_deactivate_role_hierarchy_returns_409_since_it_has_no_active_or_is_deleted_column() -> (
    None
):
    client.post(
        "/admin/config/RoleHierarchy",
        json={"data": {"role_tier": "Tier-C", "hierarchy_level": 1, "allowed_consultants": []}},
    )

    response = client.delete("/admin/config/RoleHierarchy/Tier-C")

    assert response.status_code == 409


def test_create_update_deactivate_and_relist_an_rfi_type_config() -> None:
    # Unique per run rather than the original's fixed "S56-IT" -- same reasoning as
    # test_create_role_hierarchy_then_read_it_back above.
    rfi_type_key = f"S56-{uuid.uuid4().hex[:8]}"
    response = client.post(
        "/admin/config/RFITypeConfig",
        json={"data": {"rfi_type_key": rfi_type_key, "label": "Section 56"}},
    )
    assert response.status_code == 201

    response = client.put(
        f"/admin/config/RFITypeConfig/{rfi_type_key}",
        json={"data": {"label": "Section 56 (updated)"}},
    )
    assert response.status_code == 200
    assert response.json()["data"]["label"] == "Section 56 (updated)"

    response = client.delete(f"/admin/config/RFITypeConfig/{rfi_type_key}")
    assert response.status_code == 204

    response = client.get(f"/admin/config/RFITypeConfig/{rfi_type_key}")
    assert response.json()["data"]["active"] is False


def test_list_config_returns_every_row_for_that_config_type() -> None:
    client.post(
        "/admin/config/NotificationTypeConfig",
        json={"data": {"notification_type_key": "nt-list-1", "label": "One"}},
    )
    client.post(
        "/admin/config/NotificationTypeConfig",
        json={"data": {"notification_type_key": "nt-list-2", "label": "Two"}},
    )

    response = client.get("/admin/config/NotificationTypeConfig")

    assert response.status_code == 200
    keys = {row["data"]["notification_type_key"] for row in response.json()}
    assert {"nt-list-1", "nt-list-2"} <= keys


def test_create_config_for_an_unsupported_config_type_returns_400() -> None:
    response = client.post("/admin/config/NoSuchConfigType", json={"data": {}})
    assert response.status_code == 400


def test_create_discount_coupon_with_an_invalid_enum_value_returns_422_not_500() -> None:
    # Regression test: repo.build() raises a bare ValueError for an out-of-enum "type" (e.g.
    # CouponType("not_a_real_type")) -- without a registered handler this used to propagate as an
    # unhandled 500 with no CORS headers, which a browser reports as a blocked network request
    # rather than a normal error response. See Pending_Items.md's Epic 14 section.
    response = client.post(
        "/admin/config/DiscountCoupon",
        json={
            "data": {
                "code": "BADENUM",
                "type": "not_a_real_type",
                "discount_type": "percentage",
                "discount_value": 10,
                "issued_at": "2026-01-01T00:00:00+00:00",
            }
        },
    )
    assert response.status_code == 422


def test_create_discount_coupon_auto_generates_the_coupon_id() -> None:
    response = client.post(
        "/admin/config/DiscountCoupon",
        json={
            "data": {
                "code": "INTEGRATION10",
                "type": "discount",
                "discount_type": "percentage",
                "discount_value": 10,
                "issued_at": "2026-01-01T00:00:00+00:00",
            }
        },
    )

    assert response.status_code == 201
    assert response.json()["data"]["coupon_id"]


def test_deactivate_discount_coupon_expires_it_instead_of_soft_deleting() -> None:
    created = client.post(
        "/admin/config/DiscountCoupon",
        json={
            "data": {
                "code": "INTEGRATION_EXPIRE",
                "type": "discount",
                "discount_type": "percentage",
                "discount_value": 10,
                "issued_at": "2026-01-01T00:00:00+00:00",
            }
        },
    ).json()["data"]

    response = client.delete(f"/admin/config/DiscountCoupon/{created['coupon_id']}")
    assert response.status_code == 204

    response = client.get(f"/admin/config/DiscountCoupon/{created['coupon_id']}")
    assert response.json()["data"]["status"] == "expired"


def test_list_counters_returns_the_read_only_counters_tab() -> None:
    response = client.get("/admin/counters")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_get_counter_for_a_missing_prefix_returns_404() -> None:
    response = client.get("/admin/counters/NOPE")
    assert response.status_code == 404
