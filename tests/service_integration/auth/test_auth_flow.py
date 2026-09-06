import uuid

from app.main import app
from app.models import AccountType, AuthCredentials
from app.repositories import AuthCredentialsRepository
from fastapi.testclient import TestClient

client = TestClient(app)


def _seed_password_account_once(staff_or_client_id: str, password: str) -> None:
    repo = AuthCredentialsRepository(app.state.gateway)
    try:
        repo.find_by_id(staff_or_client_id)
    except Exception:
        from app.clients import BcryptPasswordHasher

        credentials = AuthCredentials(
            staff_or_client_id=staff_or_client_id, account_type=AccountType.STAFF
        )
        credentials.set_password(BcryptPasswordHasher().hash(password))
        repo.save(credentials)


# Unique per run rather than the original's fixed "STF-000001" -- against the real, shared
# Gateway (this file's own default mode, see conftest.py), a fixed id is a genuine, persistent
# row across runs, and test_password_reset_full_flow below mutates its password -- a fixed id
# would find that mutated row already exists on the next run and skip re-seeding "correct-horse",
# unlike a fresh in-memory Gateway which never carries state between runs.
STAFF_ID = f"STF-{uuid.uuid4().hex[:8]}"

_seed_password_account_once(STAFF_ID, "correct-horse")


def test_password_login_succeeds_with_the_right_password() -> None:
    response = client.post(
        "/auth/login", json={"identifier": STAFF_ID, "password": "correct-horse"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["staff_or_client_id"] == STAFF_ID
    assert body["account_type"] == "Staff"
    assert body["token"]


def test_password_login_fails_with_the_wrong_password() -> None:
    response = client.post("/auth/login", json={"identifier": STAFF_ID, "password": "wrong"})
    assert response.status_code == 401


def test_login_with_neither_shape_returns_400() -> None:
    response = client.post("/auth/login", json={})
    assert response.status_code == 400


def test_sso_login_with_a_fake_token_for_a_known_staff_identity() -> None:
    from app.clients import BcryptPasswordHasher

    repo = AuthCredentialsRepository(app.state.gateway)
    credentials = AuthCredentials(
        staff_or_client_id="staff-subject-9", account_type=AccountType.STAFF
    )
    credentials.set_password(BcryptPasswordHasher().hash("unused"))
    repo.save(credentials)

    response = client.post(
        "/auth/login", json={"id_token": "staff-subject-9:staff@example.com:Staff"}
    )

    assert response.status_code == 200
    assert response.json()["staff_or_client_id"] == "staff-subject-9"


def test_sso_login_for_a_first_seen_client_is_denied_by_default() -> None:
    response = client.post(
        "/auth/login", json={"id_token": "client-subject-9:client@example.com:Client"}
    )
    assert response.status_code == 403


def test_validate_token_round_trip() -> None:
    login = client.post(
        "/auth/login", json={"identifier": STAFF_ID, "password": "correct-horse"}
    ).json()

    response = client.post("/auth/validate-token", json={"token": login["token"]})

    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is True
    assert body["staff_or_client_id"] == STAFF_ID


def test_validate_token_rejects_garbage() -> None:
    response = client.post("/auth/validate-token", json={"token": "not-a-real-token"})
    assert response.status_code == 200
    assert response.json()["valid"] is False


def test_password_reset_full_flow() -> None:
    reset_request = client.post("/auth/password-reset/request", json={"identifier": STAFF_ID})
    assert reset_request.status_code == 202

    otp = app.state.otp_notifier.sent[-1][1]

    confirm = client.post(
        "/auth/password-reset/confirm",
        json={"identifier": STAFF_ID, "otp": otp, "new_password": "brand-new-password"},
    )
    assert confirm.status_code == 200

    login = client.post(
        "/auth/login", json={"identifier": STAFF_ID, "password": "brand-new-password"}
    )
    assert login.status_code == 200


def test_password_reset_confirm_with_wrong_otp_returns_400() -> None:
    _seed_password_account_once("STF-000002", "some-password")
    client.post("/auth/password-reset/request", json={"identifier": "STF-000002"})

    response = client.post(
        "/auth/password-reset/confirm",
        json={"identifier": "STF-000002", "otp": "000000", "new_password": "x"},
    )
    assert response.status_code == 400
