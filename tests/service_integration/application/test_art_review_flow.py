import json

from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def _seed_application(visa_type: str) -> str:
    app.state.gateway.create(
        "Application_Type_Field_Schemas",
        {"id": visa_type, "visa_type": visa_type, "allowed_dynamic_fields_json": json.dumps([])},
    )
    response = client.post(
        "/applications",
        json={
            "primary_applicant_contact_id": "CT-300",
            "visa_type": visa_type,
            "dynamic_fields": {},
        },
    )
    return response.json()["application_id"]


def test_initiate_and_decide_art_review() -> None:
    application_id = _seed_application("ART-Visa-1")

    initiated = client.post(
        f"/applications/{application_id}/art-reviews", json={"decision_maker_role": "Consultant"}
    )
    assert initiated.status_code == 201
    review_id = initiated.json()["art_review_id"]
    assert initiated.json()["decision"] is None

    decided = client.post(
        f"/art-reviews/{review_id}/decision", json={"decision": "Refused", "appeal_initiated": True}
    )
    assert decided.status_code == 200
    body = decided.json()
    assert body["decision"] == "Refused"
    assert body["appeal_initiated"] is True
    assert body["decided_at"] is not None


def test_list_reviews_for_application() -> None:
    application_id = _seed_application("ART-Visa-2")
    client.post(
        f"/applications/{application_id}/art-reviews", json={"decision_maker_role": "Admin"}
    )

    response = client.get(f"/applications/{application_id}/art-reviews")

    assert response.status_code == 200
    assert len(response.json()) == 1


def test_initiate_review_on_missing_application_returns_404() -> None:
    response = client.post(
        "/applications/AP-999999/art-reviews", json={"decision_maker_role": "Consultant"}
    )
    assert response.status_code == 404
