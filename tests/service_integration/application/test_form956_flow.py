import io
import json

from app.main import app
from app.models import ContactRef
from fastapi.testclient import TestClient
from pypdf import PdfReader

client = TestClient(app)

DRIVE_CONTEXT = "ClientDocuments"


def _seed_contact(
    contact_id: str, full_name: str = "Jane Doe", **extra: str | None
) -> None:
    # app.state.user_service_client stays the in-memory stand-in in BOTH gateway modes here --
    # Application Service's own conftest.py never overrides user_service_mode/url, only
    # data_gateway_mode/admin_module_mode, so .seed() works identically in real and memory mode.
    app.state.client_registration_gate_service._user_service_client.seed(
        ContactRef(
            contact_id=contact_id,
            full_name=full_name,
            primary_email="jane@example.com",
            **extra,
        )
    )


def _seed_schema(visa_type: str) -> None:
    # AdminModuleApplicationTypeSchemaRepository is wired unconditionally in main.py -- it always
    # delegates to app.state.admin_module_client, never reads app.state.gateway directly. So which
    # backing store actually needs the row depends on which admin_module_client this run wired:
    #   - memory mode: admin_module_client stays InMemoryAdminModuleClient (this service's
    #     conftest.py only overrides data_gateway_mode in that branch) -- .seed_
    #     application_type_schema() is the only thing that reaches it.
    #     (Found live 2026-09-17: this folder's own test_application_flow.py::_seed_schema writes
    #     straight to app.state.gateway instead and is consequently broken in memory mode today --
    #     9 of its 12 tests fail with the same "'X' has no registered ... row" 422. Pre-existing,
    #     out of scope here, but not a pattern worth copying.)
    #   - real mode: conftest.py swaps admin_module_client to a real AdminModuleHttpClient (read-
    #     only, no seed method) whenever TEST_ADMIN_MODULE_URL is set -- that real Admin Module
    #     process reads the real Gateway's Application_Type_Field_Schemas tab, so the row has to
    #     land there instead, routed through _foreign_tab_gateway.py's ForeignTabAwareGatewayClient
    #     (that tab is admin-module-owned).
    admin_module_client = app.state.admin_module_client
    if hasattr(admin_module_client, "seed_application_type_schema"):
        admin_module_client.seed_application_type_schema(visa_type, {})
        return

    # Check-before-create: a real Sheets append can only ever add a new row, never overwrite an
    # existing one -- an unconditional create() here would leave a duplicate visa_type row behind
    # on every repeat real-mode run (same real-collision risk _seed_system_config_once already
    # guards against in the user/test_external_enquiry_lead_flow.py copy of this comment).
    if (
        app.state.gateway.get_by_id("Application_Type_Field_Schemas", visa_type)
        is not None
    ):
        return
    app.state.gateway.create(
        "Application_Type_Field_Schemas",
        {"visa_type": visa_type, "allowed_dynamic_fields_json": json.dumps({})},
    )


def _create_application(visa_type: str, contact_id: str) -> str:
    _seed_schema(visa_type)
    response = client.post(
        "/applications",
        json={
            "primary_applicant_contact_id": contact_id,
            "visa_type": visa_type,
            "dynamic_fields": {},
        },
    )
    assert response.status_code == 201
    application_id: str = response.json()["application_id"]
    return application_id


def test_fill_form956_uploads_the_filled_pdf_and_registers_completion_watching() -> (
    None
):
    contact_id = "CT-Form956Flow-1"
    _seed_contact(contact_id)
    application_id = _create_application("Form956Flow-Visa-1", contact_id)

    response = client.post(f"/applications/{application_id}/form956/fill")

    assert response.status_code == 201
    body = response.json()
    assert body["application_id"] == application_id
    assert body["doc_type"] == "Form956"
    assert body["drive_file_id"]
    assert body["pending_id"] is not None

    # Uploaded into the application's own IMMI/<application_name> folder. get_by_id gives
    # metadata only in real mode (DriveRepository.get_by_id never downloads content -- that's a
    # separate real Drive API call, get_document_content/files_get_content); the in-memory
    # stand-in happens to inline "content" into the same dict, so use get_document_content for
    # the actual bytes -- the one thing both clients implement uniformly (see
    # shared/data_gateway_client/in_memory_mock.py and http_client.py).
    uploaded = app.state.gateway.get_by_id(DRIVE_CONTEXT, body["drive_file_id"])
    assert uploaded is not None
    assert uploaded["name"] == f"{application_id}_Form956.pdf"
    if "folder_path" in uploaded:
        # In-memory stand-in only -- carries the full path by name for easy assertions.
        assert uploaded["folder_path"][1] == "IMMI"
    else:
        # Real Drive metadata carries folder_id, not a resolvable path -- IMMI subfolder
        # placement itself was already live-proven manually (New_Integrations_2026-09-16.md
        # section 14), this just confirms the real upload landed inside *some* real folder.
        assert uploaded["folder_id"]
    if "mimeType" in uploaded:
        # In-memory stand-in only -- the real GoogleDriveClient.files_get only requests
        # id/webViewLink/parents/trashed/name/createdTime from the real Drive API (never
        # mimeType), so this key simply doesn't exist on a real-mode read-back. The upload
        # itself still sets it correctly (files_create passes mimeType through); confirmed by the
        # PDF content check below actually parsing as a real PDF.
        assert uploaded["mimeType"] == "application/pdf"
    content = app.state.gateway.get_document_content(
        DRIVE_CONTEXT, body["drive_file_id"]
    )
    assert content.startswith(b"%PDF")


def test_fill_form956_with_an_unknown_application_id_returns_404() -> None:
    response = client.post("/applications/AP-does-not-exist/form956/fill")

    assert response.status_code == 404


def test_fill_form956_includes_locked_agent_fields_regardless_of_application_data() -> (
    None
):
    # Confirms the locked Migration Agent Info constants make it into the actual produced PDF
    # even though nothing about this application/contact carries agent info.
    contact_id = "CT-Form956Flow-2"
    _seed_contact(contact_id)
    application_id = _create_application("Form956Flow-Visa-2", contact_id)

    response = client.post(f"/applications/{application_id}/form956/fill")
    assert response.status_code == 201

    drive_file_id = response.json()["drive_file_id"]
    content = app.state.gateway.get_document_content(DRIVE_CONTEXT, drive_file_id)

    reader = PdfReader(io.BytesIO(content))
    fields = reader.get_fields()
    assert fields is not None
    assert str(fields["mg.name fam"].get("/V")) == "Singh"
    assert str(fields["mg.marn"].get("/V")) == "2418573"


def test_fill_form956_maps_the_widened_contact_fields_onto_client_mobile_and_dob() -> (
    None
):
    # ContactRef was widened 2026-09-17 (primary_phone/date_of_birth/nationality/current_address)
    # to close a real gap found during Form 956 field-mapping -- confirms the real, filled PDF
    # actually carries these through end to end, not just the unit-level field_mapper.
    contact_id = "CT-Form956Flow-3"
    _seed_contact(
        contact_id,
        full_name="Widened Fields Person",
        primary_phone="0412345678",
        date_of_birth="1990-01-01",
    )
    application_id = _create_application("Form956Flow-Visa-3", contact_id)

    response = client.post(f"/applications/{application_id}/form956/fill")
    assert response.status_code == 201

    drive_file_id = response.json()["drive_file_id"]
    content = app.state.gateway.get_document_content(DRIVE_CONTEXT, drive_file_id)

    reader = PdfReader(io.BytesIO(content))
    fields = reader.get_fields()
    assert fields is not None
    assert str(fields["cc.mob"].get("/V")) == "0412345678"
    assert str(fields["cc.dob"].get("/V")) == "1990-01-01"
