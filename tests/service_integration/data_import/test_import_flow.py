import uuid

from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def _submit(**overrides: object) -> dict:
    # Unique email per call rather than the original's fixed "jane@example.com" -- against the
    # real, shared Gateway (this file's own default mode, see conftest.py), the imported Contact
    # row is a genuine, persistent real row across every run, unlike the in-memory stand-in's
    # per-test-session-only persistence the original comments below already account for, so a
    # fixed email would be flagged a duplicate on the very next real run.
    body = {
        "source_type": "csv",
        "submitted_by": "STF-000001",
        "target_entity_type": "Contact",
        "field_map": {"Name": "full_name", "Email": "primary_email"},
        "raw_input": f"Name,Email\r\nJane Doe,jane-{uuid.uuid4().hex[:8]}@example.com\r\n",
    }
    body.update(overrides)
    return client.post("/import-jobs", json=body).json()


def test_submit_job_returns_202_with_the_job_queued() -> None:
    response = client.post(
        "/import-jobs",
        json={
            "source_type": "csv",
            "submitted_by": "STF-000001",
            "target_entity_type": "Contact",
            "field_map": {"Name": "full_name"},
            "raw_input": "Name\r\nJane Doe\r\n",
        },
    )

    assert response.status_code == 202
    body = response.json()
    assert body["import_job_id"]
    assert body["status"] == "queued"


def test_job_completes_synchronously_under_the_test_inline_runner_and_report_is_correct() -> None:
    submitted = _submit()

    status_response = client.get(f"/import-jobs/{submitted['import_job_id']}")
    report_response = client.get(f"/import-jobs/{submitted['import_job_id']}/report")

    # Used to fail in real mode (Build_vs_Requirements_Audit.md audit item 7.2): the real
    # Gateway rejected "Contact" creates from "data-import-service" since create was strictly
    # owner-only with no exceptions. Fixed by adding an also_allow_create_by allowlist
    # (12_data_gateway_service/app/config.py) and adding "data-import-service" to Contact's
    # entry -- passes identically in both modes now.
    assert status_response.status_code == 200
    assert status_response.json()["status"] == "completed"
    assert report_response.status_code == 200
    report = report_response.json()
    assert report["records_imported"] == 1
    assert report["records_skipped_as_duplicate"] == 0
    assert report["records_failed_validation"] == 0


def test_submit_job_with_an_unrecognized_source_type_returns_422_and_creates_no_job() -> None:
    response = client.post(
        "/import-jobs",
        json={
            "source_type": "sharepoint",
            "submitted_by": "STF-000001",
            "target_entity_type": "Contact",
            "field_map": {"Name": "full_name"},
            "raw_input": "Name\r\nJane Doe\r\n",
        },
    )

    assert response.status_code == 422


def test_submit_job_with_empty_raw_input_returns_422() -> None:
    response = client.post(
        "/import-jobs",
        json={
            "source_type": "csv",
            "submitted_by": "STF-000001",
            "target_entity_type": "Contact",
            "field_map": {"Name": "full_name"},
            "raw_input": "",
        },
    )

    assert response.status_code == 422


def test_get_status_for_an_unknown_job_returns_404() -> None:
    assert client.get("/import-jobs/IMP-999999").status_code == 404


def test_get_report_for_an_unknown_job_returns_404() -> None:
    assert client.get("/import-jobs/IMP-999999/report").status_code == 404


def test_a_second_submission_of_the_same_row_is_skipped_as_a_duplicate() -> None:
    # A row unique to this test AND to this run -- the shared Contact tab persists across every
    # test in this module (in-memory: for the session; real: forever), so reusing _submit()'s
    # default row here, or a fixed literal across runs, would already find a duplicate left over
    # from an earlier test/run and make "first" look like a dupe too.
    unique_row = f"Name,Email\r\nDup Test,dup-test-{uuid.uuid4().hex[:8]}@example.com\r\n"
    first = _submit(submitted_by="STF-000002", raw_input=unique_row)
    second = _submit(submitted_by="STF-000002", raw_input=unique_row)

    first_report = client.get(f"/import-jobs/{first['import_job_id']}/report").json()
    second_report = client.get(f"/import-jobs/{second['import_job_id']}/report").json()

    assert first_report["records_imported"] == 1
    assert second_report["records_imported"] == 0
    assert second_report["records_skipped_as_duplicate"] == 1


def test_unparseable_raw_input_marks_the_job_failed() -> None:
    submitted = _submit(source_type="google", raw_input="not valid json")

    status = client.get(f"/import-jobs/{submitted['import_job_id']}").json()

    assert status["status"] == "failed"
