import json

from app.main import app
from app.models import ContactRef, StaffRef
from fastapi.testclient import TestClient

client = TestClient(app)


def _seed_schema(visa_type: str) -> None:
    # See conftest.py's module-level comment: AdminModuleApplicationTypeSchemaRepository always
    # reads through app.state.admin_module_client, not app.state.gateway directly.
    admin_module_client = app.state.admin_module_client
    if hasattr(admin_module_client, "seed_application_type_schema"):
        admin_module_client.seed_application_type_schema(visa_type, {})
        return
    gateway = app.state.gateway
    if gateway.get_by_id("Application_Type_Field_Schemas", visa_type) is not None:
        return
    gateway.create(
        "Application_Type_Field_Schemas",
        {"visa_type": visa_type, "allowed_dynamic_fields_json": json.dumps({})},
    )


def _seed_application(
    visa_type: str, contact_id: str = "CT-300", assigned_staff_id: str | None = "STF-1"
) -> str:
    _seed_schema(visa_type)
    app.state.user_service_client.seed(
        ContactRef(
            contact_id=contact_id,
            full_name="Test Contact",
            primary_email="contact@example.com",
            assigned_staff_id=assigned_staff_id,
        )
    )
    response = client.post(
        "/applications",
        json={
            "primary_applicant_contact_id": contact_id,
            "visa_type": visa_type,
            "dynamic_fields": {},
        },
    )
    return response.json()["application_id"]


def test_initiate_and_decide_art_review() -> None:
    application_id = _seed_application("ART-Visa-1")

    initiated = client.post(
        f"/applications/{application_id}/art-reviews",
        json={"decision_maker_role": "Consultant"},
    )
    assert initiated.status_code == 201
    review_id = initiated.json()["art_review_id"]
    assert initiated.json()["decision"] is None

    # The assigned consultant on the Application's Contact (seeded above as "STF-1") may record
    # the decision -- FR-3.4 / PENDING_ITEMS_MASTER_LIST.md section 1 item 7.
    decided = client.post(
        f"/art-reviews/{review_id}/decision",
        json={"decision": "Refused", "appeal_initiated": True},
        headers={"X-Caller-Id": "STF-1"},
    )
    assert decided.status_code == 200
    body = decided.json()
    assert body["decision"] == "Refused"
    assert body["appeal_initiated"] is True
    assert body["decided_at"] is not None


def test_admin_can_decide_art_review_not_assigned_to_them() -> None:
    application_id = _seed_application("ART-Visa-Admin", contact_id="CT-301")
    app.state.user_service_client.seed_staff(
        StaffRef(staff_id="STF-9", role_tier="Admin")
    )

    initiated = client.post(
        f"/applications/{application_id}/art-reviews",
        json={"decision_maker_role": "Consultant"},
    )
    review_id = initiated.json()["art_review_id"]

    decided = client.post(
        f"/art-reviews/{review_id}/decision",
        json={"decision": "Refused", "appeal_initiated": False},
        headers={"X-Caller-Id": "STF-9"},
    )
    assert decided.status_code == 200
    assert decided.json()["decision"] == "Refused"


def test_owner_can_decide_art_review_not_assigned_to_them() -> None:
    # "Director" was fully consolidated into "Owner" during this project's RBAC simplification
    # (New_Integrations_2026-09-16.md section 5) -- role_tier="Director" no longer resolves to any
    # Role_Hierarchy row (fails closed, 403), which is what broke this test in memory mode.
    application_id = _seed_application("ART-Visa-Owner", contact_id="CT-302")
    app.state.user_service_client.seed_staff(
        StaffRef(staff_id="STF-8", role_tier="Owner")
    )

    initiated = client.post(
        f"/applications/{application_id}/art-reviews",
        json={"decision_maker_role": "Consultant"},
    )
    review_id = initiated.json()["art_review_id"]

    decided = client.post(
        f"/art-reviews/{review_id}/decision",
        json={"decision": "Refused", "appeal_initiated": False},
        headers={"X-Caller-Id": "STF-8"},
    )
    assert decided.status_code == 200
    assert decided.json()["decision"] == "Refused"


def test_unrelated_staff_member_cannot_decide_art_review() -> None:
    application_id = _seed_application("ART-Visa-Unrelated", contact_id="CT-303")
    app.state.user_service_client.seed_staff(
        StaffRef(staff_id="STF-2", role_tier="Consultant")
    )

    initiated = client.post(
        f"/applications/{application_id}/art-reviews",
        json={"decision_maker_role": "Consultant"},
    )
    review_id = initiated.json()["art_review_id"]

    decided = client.post(
        f"/art-reviews/{review_id}/decision",
        json={"decision": "Refused", "appeal_initiated": False},
        headers={"X-Caller-Id": "STF-2"},
    )
    assert decided.status_code == 403


def test_decision_without_caller_id_is_rejected() -> None:
    application_id = _seed_application("ART-Visa-NoCaller", contact_id="CT-304")

    initiated = client.post(
        f"/applications/{application_id}/art-reviews",
        json={"decision_maker_role": "Consultant"},
    )
    review_id = initiated.json()["art_review_id"]

    decided = client.post(
        f"/art-reviews/{review_id}/decision",
        json={"decision": "Refused", "appeal_initiated": False},
    )
    assert decided.status_code == 403


def test_list_reviews_for_application() -> None:
    application_id = _seed_application("ART-Visa-2", contact_id="CT-305")
    client.post(
        f"/applications/{application_id}/art-reviews",
        json={"decision_maker_role": "Admin"},
    )

    response = client.get(f"/applications/{application_id}/art-reviews")

    assert response.status_code == 200
    assert len(response.json()) == 1


def test_initiate_review_on_missing_application_returns_404() -> None:
    response = client.post(
        "/applications/AP-999999/art-reviews",
        json={"decision_maker_role": "Consultant"},
    )
    assert response.status_code == 404
