import json

import pytest
from app.main import app
from app.models import InvalidStageTransitionError
from fastapi.testclient import TestClient

client = TestClient(app)


def _seed_schema(visa_type: str = "Student", allowed_fields: list[str] | None = None) -> None:
    gateway = app.state.gateway
    gateway.create(
        "Application_Type_Field_Schemas",
        {
            "id": visa_type,
            "visa_type": visa_type,
            "allowed_dynamic_fields_json": json.dumps(allowed_fields or ["course_name"]),
        },
    )


def _create_application(visa_type: str = "Student", dynamic_fields: dict | None = None) -> dict:
    response = client.post(
        "/applications",
        json={
            "primary_applicant_contact_id": "CT-000001",
            "visa_type": visa_type,
            "dynamic_fields": dynamic_fields or {},
        },
    )
    assert response.status_code == 201
    return response.json()


def test_create_application_with_valid_dynamic_fields() -> None:
    _seed_schema("Student-1")
    body = _create_application("Student-1", {"course_name": "CS"})

    # The real Data Gateway Service allocates an "AP-000001"-style id -- InMemoryDataGatewayClient,
    # used in this test, only guarantees a non-empty id, not that specific format.
    assert body["application_id"]
    assert body["stage"] == 1
    assert body["dynamic_fields"] == {"course_name": "CS"}


def test_create_application_rejects_unknown_visa_type() -> None:
    response = client.post(
        "/applications",
        json={
            "primary_applicant_contact_id": "CT-000001",
            "visa_type": "NoSuchVisaType",
            "dynamic_fields": {},
        },
    )
    assert response.status_code == 422


def test_create_application_rejects_unknown_dynamic_field() -> None:
    _seed_schema("Student-2")
    response = client.post(
        "/applications",
        json={
            "primary_applicant_contact_id": "CT-000001",
            "visa_type": "Student-2",
            "dynamic_fields": {"bogus_field": 1},
        },
    )
    assert response.status_code == 422


def test_get_application_returns_what_was_created() -> None:
    _seed_schema("Student-3")
    created = _create_application("Student-3")

    response = client.get(f"/applications/{created['application_id']}")

    assert response.status_code == 200
    assert response.json()["application_id"] == created["application_id"]


def test_get_unknown_application_returns_404() -> None:
    response = client.get("/applications/AP-999999")
    assert response.status_code == 404


def test_update_dynamic_fields_merges_into_existing() -> None:
    _seed_schema("Student-4", ["course_name", "campus"])
    created = _create_application("Student-4", {"course_name": "CS"})

    response = client.post(
        f"/applications/{created['application_id']}/dynamic-fields",
        json={"fields": {"campus": "City"}},
    )

    assert response.status_code == 200
    assert response.json()["dynamic_fields"] == {"course_name": "CS", "campus": "City"}


def test_record_trn() -> None:
    _seed_schema("Student-5")
    created = _create_application("Student-5")

    response = client.post(f"/applications/{created['application_id']}/trn", json={"trn": "TRN-1"})

    assert response.status_code == 200
    assert response.json()["trn"] == "TRN-1"


def test_record_outcome() -> None:
    _seed_schema("Student-6")
    created = _create_application("Student-6")

    response = client.post(
        f"/applications/{created['application_id']}/outcome", json={"outcome": "Grant"}
    )

    assert response.status_code == 200
    assert response.json()["outcome"] == "Grant"


def test_compliance_status_reflects_active_checklist_items() -> None:
    _seed_schema("Student-7")
    gateway = app.state.gateway
    gateway.create(
        "Compliance_Checklist_Item",
        {
            "id": "form_956_uploaded",
            "checklist_key": "form_956_uploaded",
            "label": "Form 956",
            "applies_to": "Application",
            "active": True,
        },
    )
    created = _create_application("Student-7")

    response = client.get(f"/applications/{created['application_id']}/compliance-status")

    assert response.status_code == 200
    body = response.json()
    assert any(
        item["checklist_key"] == "form_956_uploaded" and not item["completed"] for item in body
    )


def test_assign_case_officer() -> None:
    _seed_schema("Student-8")
    created = _create_application("Student-8")

    response = client.post(
        f"/applications/{created['application_id']}/case-officer",
        json={"case_officer_name": "Pat Smith", "received_date": "2026-09-01"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["assignment_id"]
    assert body["case_officer_name"] == "Pat Smith"


def test_list_case_officer_assignments_for_application() -> None:
    _seed_schema("Student-8b")
    created = _create_application("Student-8b")
    client.post(
        f"/applications/{created['application_id']}/case-officer",
        json={"case_officer_name": "Pat Smith", "received_date": "2026-09-01"},
    )

    response = client.get(f"/applications/{created['application_id']}/case-officer")

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["case_officer_name"] == "Pat Smith"


def test_advance_stage_beyond_client_registration_gate_is_rejected() -> None:
    _seed_schema("Student-9")
    created = _create_application("Student-9")

    # Direct service call, since no controller endpoint exposes advance_stage directly --
    # ApplicationController's stage progression is entirely gate-driven via
    # ClientRegistrationGateService.evaluate_gate.
    pipeline_service = app.state.application_pipeline_service

    with pytest.raises(InvalidStageTransitionError):
        pipeline_service.advance_stage(created["application_id"], target_stage=2)
