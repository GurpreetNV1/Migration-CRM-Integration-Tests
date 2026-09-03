"""A complete real business flow over real HTTP against the real Gateway: create a poster
content request, accept it, submit it for review, approve it, publish it -- then confirm the KPI
endpoint reflects the same real data it just wrote. Single service (Graphics), but every step is
a real request against a real Gateway-backed process, not TestClient/in-memory.
"""

from __future__ import annotations

import uuid

import httpx


def test_poster_lifecycle_create_to_publish_and_kpi(gateway_url, business_service):
    graphics_url = business_service("graphics")
    staff_id = f"STF-{uuid.uuid4().hex[:8]}"
    designer_id = f"STF-{uuid.uuid4().hex[:8]}"

    create_response = httpx.post(
        f"{graphics_url}/content-requests",
        json={
            "title": "Integration demo poster",
            "description": "Full lifecycle exercised by the cross-service integration suite.",
            "request_type": "poster",
            "created_by_staff_id": staff_id,
            "platforms": ["instagram"],
            "pii_masking_applied": True,
            "raw_generation_text": "Draft copy for the poster.",
        },
        timeout=5,
    )
    assert create_response.status_code == 201, create_response.text
    request_id = create_response.json()["request_id"]
    assert request_id
    # Poster's AI-generation pipeline fires immediately at creation (unlike video, which waits
    # for a raw file upload) -- confirms the in-memory AI stand-in was actually invoked. It only
    # reaches "generated" once something calls the client's completion callback (e.g. a real
    # Gemini webhook), which nothing does in this dev stand-in, so "pending" here is correct.
    assert create_response.json()["ai_generation_status"] == "pending"

    accept_response = httpx.post(
        f"{graphics_url}/content-requests/{request_id}/accept",
        json={"designer_staff_id": designer_id},
        timeout=5,
    )
    assert accept_response.status_code == 200, accept_response.text
    assert accept_response.json()["status"] == "in_progress"

    review_response = httpx.post(
        f"{graphics_url}/content-requests/{request_id}/submit-review",
        json={"actor_id": designer_id},
        timeout=5,
    )
    assert review_response.status_code == 200, review_response.text
    assert review_response.json()["status"] == "review"

    approve_response = httpx.post(
        f"{graphics_url}/content-requests/{request_id}/approve",
        json={"actor_id": staff_id},  # poster requires no client approval -> creator approves
        timeout=5,
    )
    assert approve_response.status_code == 200, approve_response.text
    assert approve_response.json()["status"] == "completed"

    publish_response = httpx.post(
        f"{graphics_url}/content-requests/{request_id}/publish",
        json={"platforms": ["instagram"]},
        timeout=5,
    )
    assert publish_response.status_code == 200, publish_response.text
    outcomes = publish_response.json()["outcomes"]
    assert outcomes and outcomes[0]["platform"] == "instagram"
    assert outcomes[0]["success"] is True

    kpi_response = httpx.get(
        f"{graphics_url}/kpis/summary",
        params={"created_by_staff_id": staff_id},
        timeout=5,
    )
    assert kpi_response.status_code == 200, kpi_response.text
    summary = kpi_response.json()["summary"]
    assert summary["overview"]["total"] >= 1
    assert summary["overview"]["completed"] >= 1
