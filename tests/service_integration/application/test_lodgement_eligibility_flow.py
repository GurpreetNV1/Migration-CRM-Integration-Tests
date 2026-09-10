import base64

from app.main import app
from app.models import ContactRef
from fastapi.testclient import TestClient

client = TestClient(app)


def _seed_contact(contact_id: str = "CT-000001") -> None:
    app.state.user_service_client.seed(
        ContactRef(
            contact_id=contact_id, full_name="Jane Student", primary_email="jane@example.com"
        )
    )


def _create_application(contact_id: str = "CT-000001") -> str:
    _seed_contact(contact_id)
    app.state.admin_module_client.seed_application_type_schema("Student", {})
    response = client.post(
        "/applications",
        json={
            "primary_applicant_contact_id": contact_id,
            "visa_type": "Student",
            "dynamic_fields": {},
        },
    )
    assert response.status_code == 201
    return response.json()["application_id"]


def test_set_stream_rejects_an_invalid_value() -> None:
    application_id = _create_application()

    response = client.post(f"/applications/{application_id}/stream", json={"stream": "postgrad"})

    assert response.status_code == 422


def test_set_stream_then_status_reflects_it() -> None:
    application_id = _create_application()

    response = client.post(f"/applications/{application_id}/stream", json={"stream": "vocational"})

    assert response.status_code == 200
    assert response.json()["stream"] == "vocational"


def test_create_course_rejects_an_unknown_course_type() -> None:
    application_id = _create_application()

    response = client.post(
        f"/applications/{application_id}/courses",
        json={"name": "Diploma of IT", "course_type": "phd"},
    )

    assert response.status_code == 422


def test_create_and_list_courses() -> None:
    application_id = _create_application()

    create_response = client.post(
        f"/applications/{application_id}/courses",
        json={
            "name": "Diploma of IT",
            "course_type": "diploma",
            "start_date": "2023-01-01",
            "end_date": "2024-11-01",
            "cricos_code": "ABC123",
        },
    )
    assert create_response.status_code == 201
    assert create_response.json()["name"] == "Diploma of IT"

    list_response = client.get(f"/applications/{application_id}/courses")
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1


def test_upload_lodgement_document_rejects_an_unknown_doc_type() -> None:
    application_id = _create_application()

    response = client.post(
        f"/applications/{application_id}/lodgement-documents",
        json={
            "doc_type": "not_a_real_type",
            "content_base64": base64.b64encode(b"pdf-bytes").decode(),
            "filename": "doc.pdf",
        },
    )

    assert response.status_code == 422


def test_upload_lodgement_document_for_application_target() -> None:
    application_id = _create_application()

    response = client.post(
        f"/applications/{application_id}/lodgement-documents",
        json={
            "doc_type": "CurrentVisa",
            "content_base64": base64.b64encode(b"pdf-bytes").decode(),
            "filename": "visa.pdf",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["doc_type"] == "CurrentVisa"
    assert body["drive_file_id"]


def test_upload_lodgement_document_for_course_target_requires_course_id() -> None:
    application_id = _create_application()

    response = client.post(
        f"/applications/{application_id}/lodgement-documents",
        json={
            "doc_type": "CompletionLetter",
            "content_base64": base64.b64encode(b"pdf-bytes").decode(),
            "filename": "letter.pdf",
            "target_type": "Course",
        },
    )

    assert response.status_code == 422


def test_eligibility_check_end_to_end_reaches_eligible() -> None:
    application_id = _create_application()
    client.post(f"/applications/{application_id}/stream", json={"stream": "vocational"})
    client.post(
        f"/applications/{application_id}/courses",
        json={
            "name": "Diploma of IT",
            "course_type": "diploma",
            "start_date": "2023-01-01",
            "end_date": "2024-11-01",
            "cricos_code": "ABC123",
        },
    )
    app.state.cricos_client.seed("ABC123", 92)

    response = client.post(f"/applications/{application_id}/eligibility-check")

    assert response.status_code == 200
    body = response.json()
    assert body["eligibility_status"] == "eligible"
    assert body["total_duration_weeks"] == 92
    assert body["duration_breakdown"]["total_weeks"] == 92


def test_document_validity_check_is_blocked_before_eligibility_check_runs() -> None:
    application_id = _create_application()

    response = client.post(f"/applications/{application_id}/document-validity-check")

    assert response.status_code == 200
    assert response.json()["document_validity_status"] == "pending"


def test_run_eligibility_checks_cascades_through_all_three() -> None:
    application_id = _create_application()
    client.post(f"/applications/{application_id}/stream", json={"stream": "vocational"})
    client.post(
        f"/applications/{application_id}/courses",
        json={
            "name": "Diploma of IT",
            "course_type": "diploma",
            "start_date": "2023-01-01",
            "end_date": "2024-11-01",
            "cricos_code": "ABC123",
        },
    )
    app.state.cricos_client.seed("ABC123", 92)

    response = client.post(f"/applications/{application_id}/run-eligibility-checks")

    assert response.status_code == 200
    body = response.json()
    assert body["eligibility_status"] == "eligible"
    assert body["document_validity_status"] == "pending"  # no documents uploaded yet
    assert body["calculated_lodgement_date_status"] == "pending"


def test_get_eligibility_status_reflects_persisted_state() -> None:
    application_id = _create_application()
    client.post(f"/applications/{application_id}/stream", json={"stream": "higher"})

    response = client.get(f"/applications/{application_id}/eligibility-status")

    assert response.status_code == 200
    assert response.json()["stream"] == "higher"
