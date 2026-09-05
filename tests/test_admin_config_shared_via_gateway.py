"""Real cross-process data sharing through the Gateway (not Kafka): Admin Module writes a config
row via its own real HTTP API into the real Gateway process; a separately running Application
Service process, pointed at that same Gateway, reads it live to validate a request. Two
independent business services, one shared real Gateway, no direct service-to-service call at all
-- the data itself is the integration point.

Services used: Data Gateway Service, Admin Module, Application Service.
"""

from __future__ import annotations

import uuid

import httpx

from gateway_retry import call_with_quota_backoff


def test_application_service_sees_config_written_by_admin_module(gateway_url, business_service):
    admin_url = business_service("admin")
    application_url = business_service("application")

    visa_type = f"SKILLED-{uuid.uuid4().hex[:8]}"
    create_config_response = call_with_quota_backoff(
        lambda: httpx.post(
            f"{admin_url}/admin/config/ApplicationTypeFieldSchema",
            json={
                "data": {"visa_type": visa_type, "allowed_dynamic_fields": {"points_score": "int"}}
            },
            timeout=20,
        )
    )
    assert create_config_response.status_code == 201, create_config_response.text

    # Application Service was never told about this config directly -- it only shares the same
    # real Gateway process Admin Module just wrote into.
    create_application_response = call_with_quota_backoff(
        lambda: httpx.post(
            f"{application_url}/applications",
            json={
                "primary_applicant_contact_id": f"CT-{uuid.uuid4().hex[:8]}",
                "visa_type": visa_type,
                "dynamic_fields": {"points_score": 65},
            },
            timeout=20,
        )
    )
    assert create_application_response.status_code == 201, create_application_response.text
    assert create_application_response.json()["dynamic_fields"] == {"points_score": 65}

    # A field not declared in Admin Module's config is rejected -- proves the validation is
    # really reading the shared config, not just accepting anything.
    rejected_response = call_with_quota_backoff(
        lambda: httpx.post(
            f"{application_url}/applications",
            json={
                "primary_applicant_contact_id": f"CT-{uuid.uuid4().hex[:8]}",
                "visa_type": visa_type,
                "dynamic_fields": {"undeclared_field": "x"},
            },
            timeout=20,
        )
    )
    assert rejected_response.status_code == 422, rejected_response.text
