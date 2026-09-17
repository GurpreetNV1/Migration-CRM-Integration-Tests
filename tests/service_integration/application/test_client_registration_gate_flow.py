import json
import uuid

from app.main import app
from app.models import ContactRef
from fastapi.testclient import TestClient

client = TestClient(app)


def _seed_schema(visa_type: str) -> None:
    # See application/conftest.py's module-level comment: AdminModuleApplicationTypeSchemaRepository
    # always reads through app.state.admin_module_client, not app.state.gateway directly.
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


def _seed_contact(
    contact_id: str, full_name: str = "Jane Doe", email: str = "jane@example.com"
) -> None:
    app.state.client_registration_gate_service._user_service_client.seed(
        ContactRef(contact_id=contact_id, full_name=full_name, primary_email=email)
    )


def _create_application(visa_type: str, contact_id: str) -> dict:
    _seed_schema(visa_type)
    _seed_contact(contact_id)
    response = client.post(
        "/applications",
        json={
            "primary_applicant_contact_id": contact_id,
            "visa_type": visa_type,
            "dynamic_fields": {},
        },
    )
    assert response.status_code == 201
    return response.json()


def _completed_webhook_payload(document_id: str) -> str:
    # BoldSign's real webhook shape -- an "event"/"data" envelope wrapping just the eventType
    # and the documentId, nothing application-specific. The adapter resolves which application
    # this belongs to via Application.pending_signature_reference, and downloads the combined
    # signed PDFs itself (InMemoryESignatureProviderClient.download_signed_document() returns a
    # fake ZIP containing both "Form 956.pdf" and "Client Agreement.pdf" for exactly this reason).
    return json.dumps(
        {"event": {"eventType": "Completed"}, "data": {"documentId": document_id}}
    )


def test_full_gate_flow_advances_application_to_stage_two() -> None:
    application = _create_application("GateVisa-1", "CT-100")
    application_id = application["application_id"]

    # Per the client's own workflow: opening a real Application promotes the contact from
    # Enquiry to Prospect immediately, independent of the signature/payment gate below.
    user_service_client = (
        app.state.client_registration_gate_service._user_service_client
    )
    assert ("CT-100", "Prospect") in user_service_client.lifecycle_transitions

    gate_status = client.get(
        f"/applications/{application_id}/registration/gate-status"
    ).json()
    assert gate_status["signature_requested"] is False

    response = client.post(
        f"/applications/{application_id}/registration/signature-request"
    )
    assert response.status_code == 202

    gate_status = client.get(
        f"/applications/{application_id}/registration/gate-status"
    ).json()
    assert gate_status["signature_requested"] is True

    # Look up by application_id, not just the first dict entry -- esign_client.requests
    # accumulates across every test in this module since app.state is built once in conftest.py.
    esign_client = app.state.esignature_provider_client
    provider_reference = next(
        ref
        for ref, data in esign_client.requests.items()
        if data["application_id"] == application_id
    )

    # One combined "completed" event covers both Form 956 and the Client Agreement, since they
    # were requested together in a single signing session.
    response = client.post(
        "/applications/registration/signature-webhook",
        content=_completed_webhook_payload(provider_reference),
    )
    assert response.status_code == 200

    gate_status = client.get(
        f"/applications/{application_id}/registration/gate-status"
    ).json()
    assert gate_status["form_956_uploaded"] is True
    assert gate_status["client_agreement_uploaded"] is True
    assert gate_status["gate_satisfied"] is False

    # Per the client's own workflow: once BOTH documents are signed, the contact becomes a
    # Client -- this is tied to signature completion, not the full gate (which also needs
    # payment, still pending at this point in the flow).
    assert ("CT-100", "Client") in user_service_client.lifecycle_transitions

    response = client.post(
        f"/applications/{application_id}/registration/invoice", json={"amount": 1000}
    )
    assert response.status_code == 201
    invoice_id = response.json()["invoice_id"]
    assert response.json()["payment_status"] == "Unrealised"

    listed_invoices = client.get(
        f"/applications/{application_id}/registration/invoices"
    ).json()
    assert len(listed_invoices) == 1
    assert listed_invoices[0]["invoice_id"] == invoice_id

    response = client.post(
        "/applications/registration/payment-webhook",
        content=json.dumps(
            {"invoice_id": invoice_id, "provider_reference": "prov-ref"}
        ),
    )
    assert response.status_code == 200

    final_application = client.get(f"/applications/{application_id}").json()
    assert final_application["stage"] == 2
    assert final_application["invoice_paid"] is True

    final_gate = client.get(
        f"/applications/{application_id}/registration/gate-status"
    ).json()
    assert final_gate["gate_satisfied"] is True


def test_signature_request_and_invoice_creation_each_schedule_a_followup_reminder() -> (
    None
):
    # Reminder Service's existing generic "reminder.schedule_requested" rule needs no changes
    # to pick this up -- see reminder_schedule_rules.py in that service.
    application = _create_application("GateVisa-Reminder", "CT-105")
    application_id = application["application_id"]
    published = app.state.event_publisher.published

    response = client.post(
        f"/applications/{application_id}/registration/signature-request"
    )
    assert response.status_code == 202
    reminder_events = [
        event
        for topic, event in published
        if topic == "reminder.schedule_requested"
        and event["target_id"] == application_id
    ]
    assert len(reminder_events) == 1
    assert reminder_events[0]["target_type"] == "Application"
    assert reminder_events[0]["delivery_channel"] == "email"
    assert reminder_events[0]["fire_at"]  # a real future timestamp, not blank

    client.post(
        f"/applications/{application_id}/registration/invoice", json={"amount": 250}
    )
    reminder_events = [
        event
        for topic, event in published
        if topic == "reminder.schedule_requested"
        and event["target_id"] == application_id
    ]
    assert (
        len(reminder_events) == 2
    )  # one from the signature request, one from the invoice


def test_redelivered_signature_webhook_is_idempotent() -> None:
    application = _create_application("GateVisa-2", "CT-101")
    application_id = application["application_id"]

    response = client.post(
        f"/applications/{application_id}/registration/signature-request"
    )
    assert response.status_code == 202
    esign_client = app.state.esignature_provider_client
    provider_reference = next(
        ref
        for ref, data in esign_client.requests.items()
        if data["application_id"] == application_id
    )

    payload = _completed_webhook_payload(provider_reference)
    first = client.post("/applications/registration/signature-webhook", content=payload)
    second = client.post(
        "/applications/registration/signature-webhook", content=payload
    )

    assert first.status_code == 200
    assert second.status_code == 200
    documents = (
        app.state.client_registration_gate_service._document_repo.find_by_target(
            "Application", application_id
        )
    )
    # Both doc types land from the one combined session -- redelivering the same completed
    # event must not duplicate either of them.
    assert len(documents) == 2


def test_handle_signature_completed_resumes_after_a_partial_failure() -> None:
    # Simulates a real failure mode: the Document row got saved as SIGNED, but the very next
    # step (persisting the Application's form_956_uploaded flag) never completed -- two
    # separate Sheets writes, not one atomic transaction. A naive idempotency check keyed only
    # on "is there already a SIGNED Document row" would treat this as already-done forever,
    # permanently blocking the registration gate. This confirms a retry resumes and finishes
    # the interrupted work instead, without duplicating the Document row.
    application = _create_application("GateVisa-Resume", "CT-104")
    application_id = application["application_id"]
    gate_service = app.state.client_registration_gate_service

    gate_service.handle_signature_completed(
        {
            "application_id": application_id,
            "doc_type": "Form956",
            "drive_file_id": "drive-file-1",
            "provider_reference": "prov-resume",
        }
    )

    # Revert just the Application flag, as if that half of the operation never persisted --
    # the Document row from the call above stays SIGNED, untouched.
    stalled_application = gate_service._application_repo.get_by_id(application_id)
    stalled_application.form_956_uploaded = False
    gate_service._application_repo.save(stalled_application)

    gate_service.handle_signature_completed(
        {
            "application_id": application_id,
            "doc_type": "Form956",
            "drive_file_id": "drive-file-1",
            "provider_reference": "prov-resume",
        }
    )

    resumed_application = gate_service._application_repo.get_by_id(application_id)
    assert resumed_application.form_956_uploaded is True
    documents = gate_service._document_repo.find_by_target(
        "Application", application_id
    )
    form_956_documents = [d for d in documents if d.doc_type.value == "Form956"]
    assert len(form_956_documents) == 1


def test_redelivered_payment_webhook_is_idempotent() -> None:
    application = _create_application("GateVisa-3", "CT-102")
    application_id = application["application_id"]

    invoice = client.post(
        f"/applications/{application_id}/registration/invoice", json={"amount": 500}
    ).json()

    payload = json.dumps(
        {"invoice_id": invoice["invoice_id"], "provider_reference": "prov-1"}
    )
    first = client.post("/applications/registration/payment-webhook", content=payload)
    second = client.post("/applications/registration/payment-webhook", content=payload)

    assert first.status_code == 200
    assert second.status_code == 200


def test_invalid_coupon_code_is_rejected() -> None:
    application = _create_application("GateVisa-4", "CT-103")
    application_id = application["application_id"]

    response = client.post(
        f"/applications/{application_id}/registration/invoice",
        json={"amount": 500, "coupon_code": "NOPE"},
    )

    assert response.status_code == 400


def test_valid_coupon_applies_discount_and_gets_redeemed() -> None:
    application = _create_application("GateVisa-5", "CT-104")
    application_id = application["application_id"]

    # Unique per run rather than a fixed "CPN-TEST-1"/"SAVE10" -- this test's own redeem() call
    # mutates the row (status "active" -> "redeemed"), so a fixed id is a genuine, permanently
    # redeemed real row after the first real-mode run (found live 2026-09-17: a second run's
    # check-before-create skipped re-seeding an "active" row entirely, since one already existed
    # from the previous run's redemption, and the invoice call then correctly 400'd against an
    # already-redeemed coupon). Same reasoning as test_inbound_document_flow.py's own uuid-keyed
    # seeding against the real, shared Gateway.
    coupon_id = f"CPN-TEST-{uuid.uuid4().hex[:8]}"
    coupon_code = f"SAVE10-{uuid.uuid4().hex[:8]}"
    coupon_fields = {
        "coupon_id": coupon_id,
        "code": coupon_code,
        "type": "discount",
        "discount_type": "percentage",
        "discount_value": 10,
        "status": "active",
        "issued_at": "2026-01-01T00:00:00+00:00",
    }
    # Two different read paths, so (per the original single-mode test's own comment) this is
    # seeded into both stores: get_active_by_code reads through admin_module_client (audit item
    # 7.11), but redeem() still writes through app.state.gateway directly -- no Admin Module
    # write endpoint exists for that (see GatewayCouponRepository's own docstring). This
    # gateway.create() runs in BOTH modes (redeem() always needs a real row to update() against,
    # unlike admin_module_client which is skippable in real mode) -- and needs an explicit "id"
    # field for the shared InMemoryDataGatewayClient's own key derivation
    # (shared/data_gateway_client/in_memory_mock.py's create(): `record.get("id") or <auto-
    # incremented counter>`, unrelated to the real server-side Gateway's schema-driven id column
    # convention) -- found live 2026-09-17: omitting it silently created the row under a
    # different, auto-allocated id, so redeem()'s later update(coupon_id, ...) 404'd.
    admin_module_client = app.state.admin_module_client
    if hasattr(admin_module_client, "seed_discount_coupon"):
        admin_module_client.seed_discount_coupon(coupon_code, dict(coupon_fields))
    app.state.gateway.create("Discount_Coupon", {"id": coupon_id, **coupon_fields})

    response = client.post(
        f"/applications/{application_id}/registration/invoice",
        json={"amount": 500, "coupon_code": coupon_code},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["discount_amount"] == 50.0
    # 500 - 50 discount = 450 subtotal; +10% default tax rate = 45; final = 495.
    assert body["tax_rate"] == 0.10
    assert body["tax_amount"] == 45.0
    assert body["final_amount"] == 495.0

    coupon_row = app.state.gateway.get_by_id("Discount_Coupon", coupon_id)
    assert coupon_row["status"] == "redeemed"
