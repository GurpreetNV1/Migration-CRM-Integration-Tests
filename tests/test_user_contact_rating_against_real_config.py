"""Real config-driven validation: User Service's ConfigDrivenRatingStrategy reads the
"rating_ladder" System_Config row through the real Gateway, not a hardcoded/in-memory default.
Ensures that row exists (idempotent -- shared, fixed-key config, never clobbered if another test
or a manual session already set it up), then dynamically reads back whatever the real active
ladder currently is rather than assuming its exact contents, and proves both a real member of
that ladder and a genuinely unrecognized rating are handled correctly against real, persisted
Sheets data.

Services used: Data Gateway Service, User Service.
"""

from __future__ import annotations

import json
import uuid

import httpx

from conftest import seed_gateway_record_if_missing
from gateway_retry import call_with_quota_backoff

RATING_LADDER_DEFAULT = ["Lost", "Cold", "Warm", "Hot"]


def test_rating_assignment_validates_against_the_real_active_ladder(gateway_url, business_service):
    seed_gateway_record_if_missing(
        gateway_url,
        "System_Config",
        "rating_ladder",
        {
            "config_key": "rating_ladder",
            "config_value": json.dumps(RATING_LADDER_DEFAULT),
            "description": "",
        },
        caller="admin-module",
    )
    # Read back whatever's really active rather than assuming it's exactly the default above --
    # another test run or a manual session may have already seeded it with a different set.
    config_response = call_with_quota_backoff(
        lambda: httpx.get(
            f"{gateway_url}/records/System_Config/rating_ladder",
            headers={"X-Caller-Service": "admin-module"},
            timeout=20,
        )
    )
    assert config_response.status_code == 200, config_response.text
    active_ladder = json.loads(config_response.json()["fields"]["config_value"])
    assert active_ladder, "rating_ladder config exists but is empty"
    a_real_rating = active_ladder[0]

    user_url = business_service("user")

    created = call_with_quota_backoff(
        lambda: httpx.post(
            f"{user_url}/contacts/enquiries",
            json={
                "source": "Form",
                "full_name": f"Rating Test {uuid.uuid4().hex[:8]}",
                "primary_email": f"{uuid.uuid4().hex[:8]}@example.com",
            },
            timeout=20,
        )
    )
    assert created.status_code == 201, created.text
    contact_id = created.json()["contact_id"]

    # A real member of the currently active ladder -- persists.
    valid_assignment = httpx.post(
        f"{user_url}/contacts/{contact_id}/rating", json={"rating": a_real_rating}, timeout=20
    )
    assert valid_assignment.status_code == 200, valid_assignment.text
    assert valid_assignment.json()["rating"] == a_real_rating

    fetched = httpx.get(f"{user_url}/contacts/{contact_id}", timeout=20)
    assert fetched.status_code == 200, fetched.text
    assert fetched.json()["rating"] == a_real_rating

    # Not a real RatingLadder member at all -- proves the real config-driven strategy is
    # actually validating, not accepting any string.
    invalid_assignment = httpx.post(
        f"{user_url}/contacts/{contact_id}/rating",
        json={"rating": "NotARealRating"},
        timeout=20,
    )
    assert invalid_assignment.status_code == 422, invalid_assignment.text
