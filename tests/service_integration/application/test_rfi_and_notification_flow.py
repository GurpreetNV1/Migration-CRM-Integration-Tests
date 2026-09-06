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
            "primary_applicant_contact_id": "CT-200",
            "visa_type": visa_type,
            "dynamic_fields": {},
        },
    )
    return response.json()["application_id"]


def _rfi_payload(rfi_type: str) -> dict:
    return {
        "rfi_type": rfi_type,
        "request_date": "2026-09-01",
        "last_date_for_submission": "2026-09-15",
    }


def _seed_rfi_type(rfi_type_key: str = "S56") -> None:
    app.state.gateway.create(
        "RFI_Type_Config",
        {
            "id": rfi_type_key,
            "rfi_type_key": rfi_type_key,
            "label": "Section 56",
            "active": True,
            "document_type_key": None,
        },
    )


def _seed_notification_type(key: str = "bridging_visa") -> None:
    app.state.gateway.create(
        "Notification_Type_Config",
        {
            "id": key,
            "notification_type_key": key,
            "label": "Bridging Visa",
            "active": True,
            "document_type_key": None,
        },
    )


def test_create_rfi_computes_reminder_date_from_lead_days() -> None:
    _seed_rfi_type("S56-1")
    application_id = _seed_application("RFI-Visa-1")

    response = client.post(
        f"/applications/{application_id}/rfi-requests", json=_rfi_payload("S56-1")
    )

    assert response.status_code == 201
    body = response.json()
    assert body["reminder_required"] is True
    assert body["reminder_date"] == "2026-09-12"  # 3-day default lead time


def test_create_rfi_with_unknown_type_returns_422() -> None:
    application_id = _seed_application("RFI-Visa-2")

    response = client.post(
        f"/applications/{application_id}/rfi-requests", json=_rfi_payload("NoSuchType")
    )

    assert response.status_code == 422


def test_mark_rfi_handled_excludes_it_from_open_list() -> None:
    _seed_rfi_type("S56-2")
    application_id = _seed_application("RFI-Visa-3")
    created = client.post(
        f"/applications/{application_id}/rfi-requests", json=_rfi_payload("S56-2")
    ).json()

    response = client.post(f"/rfi-requests/{created['rfi_request_id']}/handled")
    assert response.status_code == 200
    assert response.json()["handled"] is True

    open_list = client.get("/rfi-requests", params={"application_id": application_id}).json()
    assert all(rfi["rfi_request_id"] != created["rfi_request_id"] for rfi in open_list)


def test_create_notification_with_unknown_type_returns_422() -> None:
    application_id = _seed_application("Notif-Visa-1")

    response = client.post(
        f"/applications/{application_id}/notifications",
        json={"notification_type": "NoSuchType"},
    )

    assert response.status_code == 422


def test_create_and_mark_notification_handled() -> None:
    _seed_notification_type("bridging_visa-1")
    application_id = _seed_application("Notif-Visa-2")

    created = client.post(
        f"/applications/{application_id}/notifications",
        json={"notification_type": "bridging_visa-1", "details": {"arrival_time": "10am"}},
    )
    assert created.status_code == 201
    notification_id = created.json()["notification_id"]
    assert created.json()["details"] == {"arrival_time": "10am"}

    handled = client.post(f"/notifications/{notification_id}/handled")
    assert handled.status_code == 200
    assert handled.json()["handled"] is True

    listed = client.get(f"/applications/{application_id}/notifications").json()
    assert any(n["notification_id"] == notification_id for n in listed)
