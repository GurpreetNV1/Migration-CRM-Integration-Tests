from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def test_poster_without_pii_masking_is_rejected_but_still_created() -> None:
    response = client.post(
        "/content-requests",
        json={
            "title": "Poster",
            "description": "x",
            "request_type": "poster",
            "created_by_staff_id": "STF-100",
            "raw_generation_text": "raw text",
            "pii_masking_applied": False,
        },
    )
    assert response.status_code == 422

    # The row is still created despite the 422 -- documented behavior, not a bug.
    listed = client.get("/content-requests", params={"created_by_staff_id": "STF-100"}).json()
    assert any(r["title"] == "Poster" and r["status"] == "pending" for r in listed)


def test_poster_with_pii_masking_triggers_generation_and_completes_on_callback() -> None:
    created = client.post(
        "/content-requests",
        json={
            "title": "Poster2",
            "description": "x",
            "request_type": "poster",
            "created_by_staff_id": "STF-100",
            "raw_generation_text": "raw text",
            "pii_masking_applied": True,
        },
    ).json()
    assert created["ai_generation_status"] == "pending"

    ai_client = app.state.ai_summarization_client
    assert created["request_id"] in ai_client.requests
    ai_client.complete(created["request_id"], "Summarized poster text")

    updated = client.get(f"/content-requests/{created['request_id']}").json()
    assert updated["ai_generation_status"] == "generated"
    assert updated["generated_text"] == "Summarized poster text"
    assert updated["generation_method"] == "gemini_api"


def test_video_generation_triggers_on_raw_upload_not_at_creation() -> None:
    created = client.post(
        "/content-requests",
        json={
            "title": "Video",
            "description": "x",
            "request_type": "video",
            "created_by_staff_id": "STF-100",
            "pii_masking_applied": True,
            "client_approver_contact_id": "CT-1",
        },
    ).json()
    # No raw file uploaded yet -- generation must not have fired.
    assert created["ai_generation_status"] == "not_applicable"

    client.post(
        f"/content-requests/{created['request_id']}/accept", json={"designer_staff_id": "STF-200"}
    )
    client.post(
        f"/content-requests/{created['request_id']}/raw-files",
        files=[("files", ("video.mp4", b"bytes", "video/mp4"))],
        data={"actor_id": "STF-200"},
    )

    after_upload = client.get(f"/content-requests/{created['request_id']}").json()
    assert after_upload["ai_generation_status"] == "pending"

    media_client = app.state.media_production_client
    media_client.complete(created["request_id"], "Auto-generated subtitles")

    final = client.get(f"/content-requests/{created['request_id']}").json()
    assert final["ai_generation_status"] == "generated"
    assert final["generation_method"] == "media_production_api"


def test_non_ai_request_type_never_enters_generation_pipeline() -> None:
    created = client.post(
        "/content-requests",
        json={
            "title": "x",
            "description": "x",
            "request_type": "banner",
            "created_by_staff_id": "STF-100",
        },
    ).json()
    assert created["ai_generation_status"] == "not_applicable"
