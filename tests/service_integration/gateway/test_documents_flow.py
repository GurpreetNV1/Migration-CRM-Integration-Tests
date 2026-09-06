import base64

from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)
APPLICATION_CALLER = {"X-Caller-Service": "application-service"}


def test_upload_document_returns_a_file_ref() -> None:
    content = base64.b64encode(b"pdf-bytes").decode()

    response = client.post(
        "/documents/ClientDocuments",
        json={
            "content_base64": content,
            "metadata": {"name": "Form956.pdf"},
            "folder_path": ["CT-000001 - Test Person"],
        },
        headers=APPLICATION_CALLER,
    )

    assert response.status_code == 201
    body = response.json()
    assert body["file_id"]
    assert body["web_link"]


def test_get_document_returns_the_uploaded_file() -> None:
    content = base64.b64encode(b"pdf-bytes").decode()
    uploaded = client.post(
        "/documents/ClientDocuments",
        json={"content_base64": content, "metadata": {"name": "a.pdf"}},
        headers=APPLICATION_CALLER,
    ).json()

    response = client.get(
        f"/documents/ClientDocuments/{uploaded['file_id']}", headers=APPLICATION_CALLER
    )

    assert response.status_code == 200
    assert response.json()["file_id"] == uploaded["file_id"]


def test_get_document_is_not_restricted_to_the_owning_caller() -> None:
    # System_Design.md section 6: ownership is a write restriction ("no service can write
    # into another service's sheet") -- a non-owning caller reading a document is not a 403.
    content = base64.b64encode(b"pdf-bytes").decode()
    uploaded = client.post(
        "/documents/ClientDocuments",
        json={"content_base64": content, "metadata": {}},
        headers=APPLICATION_CALLER,
    ).json()

    response = client.get(
        f"/documents/ClientDocuments/{uploaded['file_id']}",
        headers={"X-Caller-Service": "graphics-service"},
    )
    assert response.status_code == 200


def test_upload_document_with_wrong_caller_returns_403() -> None:
    content = base64.b64encode(b"pdf-bytes").decode()

    response = client.post(
        "/documents/ClientDocuments",
        json={"content_base64": content, "metadata": {}},
        headers={"X-Caller-Service": "graphics-service"},
    )

    assert response.status_code == 403


def test_delete_document_hard_delete_removes_it() -> None:
    content = base64.b64encode(b"pdf-bytes").decode()
    uploaded = client.post(
        "/documents/ClientDocuments",
        json={"content_base64": content, "metadata": {}},
        headers=APPLICATION_CALLER,
    ).json()

    response = client.delete(
        f"/documents/ClientDocuments/{uploaded['file_id']}?hard=true",
        headers=APPLICATION_CALLER,
    )
    assert response.status_code == 204

    fetched = client.get(
        f"/documents/ClientDocuments/{uploaded['file_id']}", headers=APPLICATION_CALLER
    )
    assert fetched.status_code == 404
