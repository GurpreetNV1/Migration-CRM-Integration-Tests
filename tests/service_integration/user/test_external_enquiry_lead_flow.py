import json
import random

from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def _seed_system_config_once(key: str, value: list[str]) -> None:
    # AdminModuleContactConfigProvider (the thing ConfigDrivenRatingStrategy actually calls)
    # always delegates to app.state.admin_module_client, never reads app.state.gateway directly --
    # same "which backing store needs the row depends on which admin_module_client this run
    # wired" situation as application/test_form956_flow.py::_seed_schema (see that file's comment
    # for the full explanation, including the pre-existing memory-mode bug this avoids copying):
    #   - memory mode: admin_module_client stays InMemoryAdminModuleClient -- .seed_system_config()
    #     is the only thing that reaches it.
    #   - real mode: conftest.py swaps it to a real, read-only AdminModuleHttpClient whenever
    #     TEST_ADMIN_MODULE_URL is set, which reads the real Gateway's System_Config tab instead --
    #     check-before-create there (never a blind create()) since rating_ladder already exists
    #     for real in the shared production Sheet, and the real Gateway's Sheets-backed create()
    #     can only append a new row, never overwrite an existing one (a second unconditional
    #     create() with the same key would leave a real, physical duplicate row behind -- exactly
    #     the kind of collision this project hit once before with a manually-seeded Staff row).
    admin_module_client = app.state.admin_module_client
    if hasattr(admin_module_client, "seed_system_config"):
        admin_module_client.seed_system_config(key, json.dumps(value))
        return

    gateway = app.state.gateway
    if gateway.get_by_id("System_Config", key) is not None:
        return
    # System_Config's own record key IS its "config_key" field value (TAB_SCHEMAS' first column
    # convention, see 12_data_gateway_service/app/services/record_gateway_service.py's
    # _with_allocated_id) -- no separate "id" field exists on this tab.
    gateway.create(
        "System_Config",
        {"config_key": key, "config_value": json.dumps(value)},
    )


_seed_system_config_once("rating_ladder", ["Lost", "Cold", "Warm", "Hot"])


def _seed_lead_row(
    name: str,
    email: str = "",
    phone: str = "",
    enquiry_message: str = "",
    conversion: str = "",
) -> int:
    # app.state.external_enquiry_sheet_client stays the in-memory fake in BOTH gateway modes --
    # EXTERNAL_ENQUIRY_INGESTION_MODE is a separate axis this copied conftest.py never overrides,
    # so it keeps Settings' own "memory" default regardless of TEST_GATEWAY_MODE. Deliberate: the
    # real external "Enquiries" sheet is a separate, real, shared production spreadsheet -- this
    # dual-mode suite proves the CRM's own mirror/convert logic against real Sheets-backed CRM
    # tabs (External_Enquiry_Lead, Contact, Note), never against that external tool itself (that
    # was proven live manually, see New_Integrations_2026-09-16.md section 15).
    #
    # Unique per call rather than a fixed row_number -- External_Enquiry_Lead is a real, shared,
    # persisted Gateway tab even though the sheet client itself is fake, and both the auto-convert
    # and manual-convert paths are idempotent no-ops for an already-converted row. Found live
    # 2026-09-17: a fixed row_number's SECOND real-mode run found the previous run's own already-
    # converted mirror row, so the manual-convert endpoint correctly no-op'd instead of actually
    # calling mark_converted this run -- failing this test's own "was mark_converted called"
    # assertion. Same reasoning as application/test_client_registration_gate_flow.py's coupon fix.
    row_number = random.randint(100_000, 999_999)
    app.state.external_enquiry_sheet_client.seed_row(
        row_number,
        name=name,
        email=email,
        phone=phone,
        enquiry_message=enquiry_message,
        conversion=conversion,
    )
    return row_number


def test_poll_mirrors_every_row_regardless_of_conversion_status() -> None:
    row_number = _seed_lead_row(
        name="Not Yet Lead", email="notyet@example.com", conversion="Not yet"
    )

    app.state.external_enquiry_ingestion_scheduler.trigger_poll()

    response = client.get("/external-enquiry-leads")
    assert response.status_code == 200
    leads_by_row = {lead["row_number"]: lead for lead in response.json()}
    assert leads_by_row[row_number]["name"] == "Not Yet Lead"
    assert leads_by_row[row_number]["conversion"] == "Not yet"
    assert leads_by_row[row_number]["contact_id"] is None


def test_poll_auto_converts_yes_rows_into_a_real_prospect_contact() -> None:
    row_number = _seed_lead_row(
        name="Auto Yes Lead",
        email="autoyes@example.com",
        enquiry_message="Interested in a student visa",
        conversion="Yes",
    )

    app.state.external_enquiry_ingestion_scheduler.trigger_poll()

    response = client.get("/external-enquiry-leads")
    lead = next(row for row in response.json() if row["row_number"] == row_number)
    assert lead["contact_id"] is not None

    contact = client.get(f"/contacts/{lead['contact_id']}")
    assert contact.status_code == 200
    assert contact.json()["lifecycle_state"] == "Prospect"


def test_manual_convert_creates_a_prospect_and_writes_back_to_the_sheet() -> None:
    row_number = _seed_lead_row(
        name="Manual Convert Lead",
        email="manualconvert@example.com",
        enquiry_message="Interested in a partner visa",
        conversion="Not yet",
    )
    app.state.external_enquiry_ingestion_scheduler.trigger_poll()

    response = client.post(f"/external-enquiry-leads/row_{row_number}/convert")

    assert response.status_code == 200
    body = response.json()
    assert body["contact_id"] is not None
    assert (
        row_number
        in app.state.external_enquiry_sheet_client.marked_converted_row_numbers
    )

    contact = client.get(f"/contacts/{body['contact_id']}")
    assert contact.status_code == 200
    assert contact.json()["lifecycle_state"] == "Prospect"


def test_manual_convert_of_an_unknown_row_key_returns_404() -> None:
    response = client.post("/external-enquiry-leads/row_999999/convert")

    assert response.status_code == 404
