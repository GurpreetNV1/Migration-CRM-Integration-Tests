from datetime import UTC, datetime, timedelta

from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def test_is_backed_up_false_before_any_backup_has_run() -> None:
    # BackupCoverageChecker.is_backed_up() checks completed_at >= up_to_date across every
    # succeeded FULL_BACKUP ever recorded (see its own docstring) -- against the real, shared
    # Gateway (this file's own default mode, see conftest.py) a real backup genuinely completed
    # "today" persists forever, so a fixed *past* up_to_date like the original "2026-09-01" would
    # find it satisfied by any backup this suite (or anything else) has ever actually run, unlike
    # the in-memory stand-in's always-empty-at-start Backup_Run_Log. A far-future date can never
    # be satisfied by a real backup's completed_at (which can only ever be "now" or earlier),
    # so it reliably proves "no backup" regardless of real history.
    response = client.get(
        "/backup/is-backed-up", params={"entity_name": "Audit_Log", "up_to_date": "2099-01-01"}
    )

    assert response.status_code == 200
    assert response.json()["is_backed_up"] is False


def test_is_backed_up_true_after_a_successful_backup() -> None:
    triggered = client.post("/backup/trigger", params={"staff_id": "STF-000001"}).json()
    assert triggered["status"] == "succeeded"

    response = client.get(
        "/backup/is-backed-up", params={"entity_name": "Audit_Log", "up_to_date": "2020-01-01"}
    )

    assert response.status_code == 200
    assert response.json()["is_backed_up"] is True


def test_trigger_backup_succeeds() -> None:
    response = client.post("/backup/trigger", params={"staff_id": "STF-000001"})

    assert response.status_code == 201
    body = response.json()
    assert body["run_id"]
    assert body["status"] == "succeeded"
    assert body["run_type"] == "full_backup"


def test_trigger_backup_while_one_is_in_progress_returns_409() -> None:
    from app.models import BackupRunLog, RunStatus, RunType

    # get_latest picks the max started_at -- must be demonstrably later than the real
    # SystemClock "now" used by any earlier trigger in this suite, regardless of when the
    # suite actually runs.
    future_started_at = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    in_progress = app.state.run_log_repository.save(
        BackupRunLog(
            run_id=None,
            run_type=RunType.FULL_BACKUP,
            started_at=future_started_at,
            status=RunStatus.IN_PROGRESS,
            source_scope="full",
        )
    )

    try:
        response = client.post("/backup/trigger", params={"staff_id": "STF-000001"})

        assert response.status_code == 409
    finally:
        # Against the real, shared Gateway (this file's own default mode, see conftest.py) this
        # row is a genuine, persistent real row -- get_latest's own "max started_at" rule (see
        # above) would make it "the latest FULL_BACKUP run" forever, permanently 409-blocking
        # every trigger in every later real-mode run, unlike the in-memory stand-in which starts
        # empty each run. Resolve it back to SUCCEEDED so the real system is left exactly as
        # healthy as it was before this test touched it.
        in_progress.status = RunStatus.SUCCEEDED
        in_progress.completed_at = datetime.now(UTC).isoformat()
        app.state.run_log_repository.save(in_progress)


def test_trigger_filtered_export_succeeds() -> None:
    response = client.post(
        "/backup/export",
        params={"staff_id": "STF-000001"},
        json={"report_name": "Cold Contacts", "export_format": "csv"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["run_type"] == "filtered_export"
    assert body["status"] == "succeeded"


def test_trigger_filtered_export_with_an_unsupported_format_returns_422() -> None:
    response = client.post(
        "/backup/export",
        params={"staff_id": "STF-000001"},
        json={"report_name": "Cold Contacts", "export_format": "xlsx"},
    )

    assert response.status_code == 422


def test_trigger_filtered_export_with_an_empty_report_name_returns_422() -> None:
    response = client.post(
        "/backup/export",
        params={"staff_id": "STF-000001"},
        json={"report_name": ""},
    )

    assert response.status_code == 422


def test_initiate_restore_succeeds() -> None:
    response = client.post(
        "/backup/restore",
        params={"staff_id": "STF-ADMIN"},
        json={"target_scope": "Contact", "point_in_time": "2026-08-01T00:00:00+00:00"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "partial"
    assert "Contact" in body["details"]


def test_initiate_restore_with_missing_scope_returns_422() -> None:
    response = client.post(
        "/backup/restore",
        params={"staff_id": "STF-ADMIN"},
        json={"target_scope": "", "point_in_time": "2026-08-01T00:00:00+00:00"},
    )

    assert response.status_code == 422
