import json
import uuid

from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def _seed_application(visa_type: str, trn: str) -> str:
    app.state.gateway.create(
        "Application_Type_Field_Schemas",
        {"id": visa_type, "visa_type": visa_type, "allowed_dynamic_fields_json": json.dumps([])},
    )
    application_id = client.post(
        "/applications",
        json={
            "primary_applicant_contact_id": "CT-400",
            "visa_type": visa_type,
            "dynamic_fields": {},
        },
    ).json()["application_id"]
    client.post(f"/applications/{application_id}/trn", json={"trn": trn})
    return application_id


def test_process_matches_by_trn_and_creates_rfi_request() -> None:
    # Unique per run rather than the original's fixed "TRN-IDP-1"/"S56-IDP"/"S56_DOC"/
    # "Inbound-Visa-1" -- against the real, shared Gateway (this file's own default mode, see
    # conftest.py):
    #  - a fixed TRN is a genuine, persistent real Application field across runs, so re-matching
    #    by it would find more than one real application and come back "ambiguous" instead of
    #    "matched";
    #  - GatewayTypeConfigRepository.find_by_document_type_key just takes query(...)[0] -- a
    #    fixed document_type_key would resolve to an *older* run's real RFI_Type_Config row
    #    (whichever the Gateway returns first), not this run's freshly created one, breaking the
    #    rfi_type assertion below;
    # unlike a fresh in-memory Gateway, neither of which this test would ever see.
    rfi_type_key = f"S56-IDP-{uuid.uuid4().hex[:8]}"
    document_type_key = f"S56_DOC-{uuid.uuid4().hex[:8]}"
    trn = f"TRN-IDP-{uuid.uuid4().hex[:8]}"
    app.state.gateway.create(
        "RFI_Type_Config",
        {
            "id": rfi_type_key,
            "rfi_type_key": rfi_type_key,
            "label": "Section 56",
            "active": True,
            "document_type_key": document_type_key,
        },
    )
    application_id = _seed_application(f"Inbound-Visa-{uuid.uuid4().hex[:8]}", trn)

    log = app.state.inbound_document_processing_service.process(
        document_type_key, {"trn": trn, "last_date_for_submission": "2026-10-01"}, "drv-1"
    )

    assert log.match_status.value == "matched"
    assert log.matched_application_id == application_id
    rfis = client.get("/rfi-requests", params={"application_id": application_id}).json()
    assert len(rfis) == 1
    assert rfis[0]["rfi_type"] == rfi_type_key


def test_process_with_no_trn_match_lands_in_manual_review_queue() -> None:
    log = app.state.inbound_document_processing_service.process(
        "UNKNOWN_DOC", {"trn": "NO-SUCH-TRN"}, "drv-2"
    )

    assert log.match_status.value == "unmatched"
    unmatched = client.get("/inbound-documents/unmatched").json()
    assert any(item["log_id"] == log.log_id for item in unmatched)


def test_resolve_manually_marks_log_matched() -> None:
    application_id = _seed_application("Inbound-Visa-2", "TRN-IDP-2")
    log = app.state.inbound_document_processing_service.process(
        "STILL_UNKNOWN", {"trn": "NO-MATCH-HERE"}, "drv-3"
    )

    response = client.post(
        f"/inbound-documents/{log.log_id}/resolve",
        json={"application_id": application_id, "staff_id": "STF-500"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["match_status"] == "matched"
    assert body["matched_application_id"] == application_id
    assert body["reviewed_by_staff_id"] == "STF-500"


def test_resolve_manually_on_missing_log_returns_404() -> None:
    application_id = _seed_application("Inbound-Visa-3", "TRN-IDP-3")

    response = client.post(
        "/inbound-documents/IDP-999999/resolve",
        json={"application_id": application_id, "staff_id": "STF-500"},
    )

    assert response.status_code == 404
