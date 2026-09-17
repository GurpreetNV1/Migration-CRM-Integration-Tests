import json

from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def _seed_system_config(key: str, value: list[str]) -> None:
    # AdminModuleContactConfigProvider always reads through app.state.admin_module_client, not
    # app.state.gateway directly (main.py wires it unconditionally) -- which backing store
    # actually needs this row depends on which admin_module_client THIS run wired:
    #   - memory mode: stays InMemoryAdminModuleClient -- .seed_system_config() is the only thing
    #     that reaches it (found live 2026-09-17: the gateway.create() below, on its own, left
    #     every rating/enquiry-category-dependent test failing in memory mode -- the original,
    #     single-mode test_contacts_flow.py calls seed_system_config directly, never gateway.create).
    #   - real mode: conftest.py swaps it to a real, read-only AdminModuleHttpClient whenever
    #     TEST_ADMIN_MODULE_URL is set, which reads the real Gateway's own System_Config tab
    #     instead -- check-before-create there (never a blind create()) since rating_ladder/
    #     enquiry_categories already exist for real in the shared production Sheet, and a real
    #     Sheets append can only add a new row, never overwrite an existing one.
    admin_module_client = app.state.admin_module_client
    if hasattr(admin_module_client, "seed_system_config"):
        admin_module_client.seed_system_config(key, json.dumps(value))
        return
    gateway = app.state.gateway
    if gateway.get_by_id("System_Config", key) is not None:
        return
    gateway.create(
        "System_Config", {"config_key": key, "config_value": json.dumps(value)}
    )


def _seed_config_once() -> None:
    _seed_system_config("rating_ladder", ["Lost", "Cold", "Warm", "Hot"])
    _seed_system_config("enquiry_categories", ["Skilled Migration", "Student Visa"])


_seed_config_once()


def test_create_enquiry_defaults_to_cold_rating() -> None:
    response = client.post(
        "/contacts/enquiries", json={"source": "Walk-in", "full_name": "Test Person"}
    )
    assert response.status_code == 201
    body = response.json()
    assert body["contact_id"]
    assert body["rating"] == "Cold"
    assert body["lifecycle_state"] == "Enquiry"


def test_create_enquiry_accepts_social_media_source() -> None:
    response = client.post(
        "/contacts/enquiries",
        json={"source": "Social Media", "full_name": "Test Person"},
    )
    assert response.status_code == 201
    assert response.json()["source"] == "Social Media"


def test_get_contact_returns_what_was_created() -> None:
    created = client.post(
        "/contacts/enquiries", json={"source": "Form", "full_name": "Another Person"}
    ).json()

    response = client.get(f"/contacts/{created['contact_id']}")

    assert response.status_code == 200
    assert response.json()["full_name"] == "Another Person"


def test_get_unknown_contact_returns_404() -> None:
    response = client.get("/contacts/CT-999999")
    assert response.status_code == 404


def test_lifecycle_transition_enquiry_to_prospect() -> None:
    created = client.post(
        "/contacts/enquiries", json={"source": "Form", "full_name": "X"}
    ).json()

    response = client.post(
        f"/contacts/{created['contact_id']}/lifecycle-transitions",
        json={"target_state": "Prospect"},
    )

    assert response.status_code == 200
    assert response.json()["lifecycle_state"] == "Prospect"


def test_list_contacts_filters_by_rating() -> None:
    # Asserts membership, not exact list length: against the real, shared Gateway (this file's
    # own default mode -- see conftest.py) other "Hot"-rated contacts may already exist from
    # earlier runs/services, unlike the in-memory stand-in's always-fresh state, which the
    # original at server/services/01_user_service/tests/integration/test_contacts_flow.py relies
    # on and correctly keeps the exact-length assertion for.
    created = client.post(
        "/contacts/enquiries", json={"source": "Form", "full_name": "X"}
    ).json()
    client.post(f"/contacts/{created['contact_id']}/rating", json={"rating": "Hot"})
    client.post("/contacts/enquiries", json={"source": "Form", "full_name": "Y"})

    response = client.get("/contacts", params={"rating": "Hot"})

    assert response.status_code == 200
    body = response.json()
    assert created["contact_id"] in {c["contact_id"] for c in body}
    assert all(c["rating"] == "Hot" for c in body)


def test_skipping_a_lifecycle_stage_returns_409() -> None:
    created = client.post(
        "/contacts/enquiries", json={"source": "Form", "full_name": "X"}
    ).json()

    response = client.post(
        f"/contacts/{created['contact_id']}/lifecycle-transitions",
        json={"target_state": "Client"},
    )

    assert response.status_code == 409


def test_assign_rating_outside_the_active_ladder_returns_422() -> None:
    created = client.post(
        "/contacts/enquiries", json={"source": "Form", "full_name": "X"}
    ).json()

    response = client.post(
        f"/contacts/{created['contact_id']}/rating", json={"rating": "Nonexistent"}
    )

    assert response.status_code == 422


def test_assign_rating_within_the_active_ladder_succeeds() -> None:
    created = client.post(
        "/contacts/enquiries", json={"source": "Form", "full_name": "X"}
    ).json()

    response = client.post(
        f"/contacts/{created['contact_id']}/rating", json={"rating": "Hot"}
    )

    assert response.status_code == 200
    assert response.json()["rating"] == "Hot"


def test_set_enquiry_category_with_a_valid_category() -> None:
    created = client.post(
        "/contacts/enquiries", json={"source": "Form", "full_name": "X"}
    ).json()

    response = client.post(
        f"/contacts/{created['contact_id']}/enquiry-category",
        json={"category": "Student Visa"},
    )

    assert response.status_code == 200
    assert response.json()["enquiry_category"] == "Student Visa"


def test_set_enquiry_category_with_an_invalid_category_returns_422() -> None:
    created = client.post(
        "/contacts/enquiries", json={"source": "Form", "full_name": "X"}
    ).json()

    response = client.post(
        f"/contacts/{created['contact_id']}/enquiry-category",
        json={"category": "Not Real"},
    )

    assert response.status_code == 422


def test_link_sponsor_between_two_contacts() -> None:
    contact_a = client.post(
        "/contacts/enquiries", json={"source": "Form", "full_name": "A"}
    ).json()
    contact_b = client.post(
        "/contacts/enquiries", json={"source": "Form", "full_name": "B"}
    ).json()

    response = client.post(
        f"/contacts/{contact_a['contact_id']}/sponsor-link",
        json={"sponsor_id": contact_b["contact_id"], "relationship_type": "Sponsor"},
    )

    assert response.status_code == 200
    assert response.json()["linked_contact_id"] == contact_b["contact_id"]


def test_link_sponsor_to_self_returns_409() -> None:
    contact = client.post(
        "/contacts/enquiries", json={"source": "Form", "full_name": "A"}
    ).json()

    response = client.post(
        f"/contacts/{contact['contact_id']}/sponsor-link",
        json={"sponsor_id": contact["contact_id"], "relationship_type": "Sponsor"},
    )

    assert response.status_code == 409


def test_appointment_intake_and_conversion_to_contact() -> None:
    appointment = client.post(
        "/appointments",
        json={
            "enquiry_date": "2026-09-01",
            "contact_number": "0400000000",
            "message": "call me",
        },
    ).json()
    assert appointment["appointment_id"]

    response = client.post(f"/appointments/{appointment['appointment_id']}/convert")

    assert response.status_code == 200
    body = response.json()
    assert body["contact_id"]
    assert body["primary_phone"] == "0400000000"
