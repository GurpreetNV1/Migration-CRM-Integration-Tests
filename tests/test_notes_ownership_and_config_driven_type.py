"""Real config-driven validation and real ownership enforcement for Notes Service, both against
persisted Sheets data rather than an in-memory fixture. Ensures the "note_types" System_Config
row exists (idempotent -- shared, fixed-key config), reads back whatever's really active, then
proves: a real member of that list is accepted and a bogus one is rejected (NoteTypeValidator
really reads live config through the real Gateway), and a different author's real, persisted
author_id is correctly rejected by NoteOwnershipGuard on an update (not an in-memory fixture
author that never round-trips through a real store).

Services used: Data Gateway Service, Notes Service.
"""

from __future__ import annotations

import json
import uuid

import httpx

from conftest import seed_gateway_record_if_missing
from gateway_retry import call_with_quota_backoff

NOTE_TYPES_DEFAULT = ["General", "Internal", "Client-Facing"]


def test_note_type_validation_and_ownership_guard_against_real_data(gateway_url, business_service):
    seed_gateway_record_if_missing(
        gateway_url,
        "System_Config",
        "note_types",
        {
            "config_key": "note_types",
            "config_value": json.dumps(NOTE_TYPES_DEFAULT),
            "description": "",
        },
        caller="admin-module",
    )
    config_response = call_with_quota_backoff(
        lambda: httpx.get(
            f"{gateway_url}/records/System_Config/note_types",
            headers={"X-Caller-Service": "admin-module"},
            timeout=20,
        )
    )
    assert config_response.status_code == 200, config_response.text
    active_types = json.loads(config_response.json()["fields"]["config_value"])
    assert active_types, "note_types config exists but is empty"
    a_real_type = active_types[0]

    notes_url = business_service("notes")
    target_id = f"AP-{uuid.uuid4().hex[:8]}"
    author_a = f"STF-{uuid.uuid4().hex[:8]}"
    author_b = f"STF-{uuid.uuid4().hex[:8]}"

    # A real member of the currently active list -- accepted.
    created = call_with_quota_backoff(
        lambda: httpx.post(
            f"{notes_url}/notes",
            json={
                "target_type": "Application",
                "target_id": target_id,
                "content": "Initial note content.",
                "author_id": author_a,
                "note_type": a_real_type,
            },
            timeout=20,
        )
    )
    assert created.status_code == 201, created.text
    note_id = created.json()["note_id"]
    assert created.json()["note_type"] == a_real_type

    # Not a real configured type at all -- proves real config-driven validation, not a stub.
    rejected_type = httpx.post(
        f"{notes_url}/notes",
        json={
            "target_type": "Application",
            "target_id": target_id,
            "content": "Should be rejected.",
            "author_id": author_a,
            "note_type": "NotARealNoteType",
        },
        timeout=20,
    )
    assert rejected_type.status_code == 422, rejected_type.text

    # A different (real, distinct) staff id attempting to edit -- rejected by the ownership
    # guard against the real, persisted author_id on this note.
    rejected_edit = httpx.patch(
        f"{notes_url}/notes/{note_id}",
        json={"content": "Trying to edit as someone else.", "requesting_staff_id": author_b},
        timeout=20,
    )
    assert rejected_edit.status_code == 403, rejected_edit.text

    # The real author succeeds.
    real_edit = httpx.patch(
        f"{notes_url}/notes/{note_id}",
        json={"content": "Updated by the real author.", "requesting_staff_id": author_a},
        timeout=20,
    )
    assert real_edit.status_code == 200, real_edit.text
    assert real_edit.json()["content"] == "Updated by the real author."
