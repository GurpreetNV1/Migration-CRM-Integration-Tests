import uuid

from app.clients import BcryptPasswordHasher
from app.main import app
from app.models import AccountType, AuthCredentials
from app.repositories import AuthCredentialsRepository
from fastapi.testclient import TestClient

client = TestClient(app)


def _seed_staff_with_phone_login(phone_number: str, password: str) -> str:
    # Mirrors StaffCredentialsService.set_staff_password's real create-or-update semantics, and
    # test_auth_flow.py's own _seed_password_account_once -- staff_or_client_id/X-Caller-Id is
    # always the real staff_id, never the phone number (StaffPhoneLoginStrategy resolves phone ->
    # staff_id via User Service first, exactly what app.state.user_service_client stands in for
    # here). Unique staff_id per call (see test_auth_flow.py's STAFF_ID comment) since this runs
    # against the real, shared Gateway in real mode.
    staff_id = f"STF-{uuid.uuid4().hex[:8]}"
    app.state.user_service_client.seed_staff_phone_number(phone_number, staff_id)

    repo = AuthCredentialsRepository(app.state.gateway)
    credentials = AuthCredentials(
        staff_or_client_id=staff_id, account_type=AccountType.STAFF
    )
    credentials.set_password(BcryptPasswordHasher().hash(password))
    repo.save(credentials)
    return staff_id


def test_phone_login_succeeds_and_session_carries_the_real_staff_id_not_the_phone_number() -> (
    None
):
    staff_id = _seed_staff_with_phone_login("0400111222", "Sup3rSecret!")

    response = client.post(
        "/auth/login", json={"phone_number": "0400111222", "password": "Sup3rSecret!"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["staff_or_client_id"] == staff_id
    assert body["account_type"] == "Staff"


def test_phone_login_fails_with_the_wrong_password() -> None:
    _seed_staff_with_phone_login("0400333444", "correct-password")

    response = client.post(
        "/auth/login", json={"phone_number": "0400333444", "password": "wrong-password"}
    )

    assert response.status_code == 401


def test_phone_login_fails_for_an_unknown_phone_number() -> None:
    response = client.post(
        "/auth/login", json={"phone_number": "0400999999", "password": "irrelevant"}
    )

    assert response.status_code == 401
