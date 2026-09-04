"""Real cross-process login: a staff credential is seeded directly into the real Gateway (as
Auth Service's own signup flow would, if one existed), then a separately running Auth Service
process, pointed at that same Gateway, authenticates against it. Proves Auth Service's real
BcryptPasswordHasher and session-token issuance work against a real, persisted Sheets row -- not
an in-memory fixture the per-service test suite would use instead.
"""

from __future__ import annotations

import uuid

import bcrypt
import httpx

from conftest import seed_gateway_record
from gateway_retry import call_with_quota_backoff


def test_login_succeeds_with_correct_password_and_rejects_the_wrong_one(gateway_url, business_service):
    staff_id = f"STF-{uuid.uuid4().hex[:8]}"
    password = "correct-horse-battery-staple"
    password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    seed_gateway_record(
        gateway_url,
        "Auth_Credentials",
        {
            "id": staff_id,
            "staff_or_client_id": staff_id,
            "account_type": "Staff",
            "password_hash": password_hash,
        },
        caller="auth-service",
    )

    auth_url = business_service("auth", extra_env={"IDENTITY_PROVIDER": "fake"})

    correct_login = call_with_quota_backoff(
        lambda: httpx.post(
            f"{auth_url}/auth/login",
            json={"identifier": staff_id, "password": password},
            timeout=20,
        )
    )
    assert correct_login.status_code == 200, correct_login.text
    body = correct_login.json()
    assert body["staff_or_client_id"] == staff_id
    assert body["account_type"] == "Staff"
    token = body["token"]
    assert token

    # Wrong password -- proves BcryptPasswordHasher really verifies the real persisted hash,
    # not a stub that always succeeds.
    wrong_login = httpx.post(
        f"{auth_url}/auth/login",
        json={"identifier": staff_id, "password": "not-the-right-password"},
        timeout=20,
    )
    assert wrong_login.status_code == 401, wrong_login.text

    # The token issued for the correct login actually validates.
    validate = httpx.post(f"{auth_url}/auth/validate-token", json={"token": token}, timeout=20)
    assert validate.status_code == 200, validate.text
    validated = validate.json()
    assert validated["valid"] is True
    assert validated["staff_or_client_id"] == staff_id
