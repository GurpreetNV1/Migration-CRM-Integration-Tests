from datetime import UTC, datetime

from app.main import app

# This service has no REST surface at all (LLD section 8.1: "no inbound callers... no
# user-facing surface") -- there is no TestClient/HTTP path to exercise. "Integration" here
# means driving the fully-wired CleanupOrchestrator (built by tests/conftest.py's
# build_app_state) against the real InMemoryDataGatewayClient, the same role a TestClient
# plays in every other service's integration suite.


def _seed_audit_log(log_id: str, timestamp: str) -> None:
    app.state.gateway.create(
        "Audit_Log", {"id": log_id, "audit_id": log_id, "timestamp": timestamp}
    )


def _seed_reminder_history(reminder_id: str, fired_at: str) -> None:
    app.state.gateway.create(
        "Reminders_History", {"id": reminder_id, "reminder_id": reminder_id, "fired_at": fired_at}
    )


def test_full_cycle_purges_old_rows_once_backup_is_confirmed() -> None:
    _seed_audit_log("AUD-100001", "2020-01-01T00:00:00+00:00")
    _seed_reminder_history("RM-100001", "2020-01-01T00:00:00+00:00")
    app.state.backup_check_client.always_approve = True

    result = app.state.cleanup_orchestrator.run_cleanup_cycle()

    entity_outcomes = {outcome.entity_name: outcome for outcome in result.outcomes}
    assert entity_outcomes["Audit_Log"].purged_count >= 1
    assert entity_outcomes["Reminders_History"].purged_count >= 1
    assert app.state.gateway.get_by_id("Audit_Log", "AUD-100001") is None
    assert app.state.gateway.get_by_id("Reminders_History", "RM-100001") is None


def test_full_cycle_skips_old_rows_when_backup_is_not_confirmed() -> None:
    _seed_audit_log("AUD-100002", "2020-01-01T00:00:00+00:00")
    app.state.backup_check_client.always_approve = False

    result = app.state.cleanup_orchestrator.run_cleanup_cycle()

    entity_outcomes = {outcome.entity_name: outcome for outcome in result.outcomes}
    assert entity_outcomes["Audit_Log"].skipped_count >= 1
    assert app.state.gateway.get_by_id("Audit_Log", "AUD-100002") is not None

    # Restore the default for any test that runs after this one in the same session.
    app.state.backup_check_client.always_approve = True


def test_full_cycle_leaves_recent_rows_alone() -> None:
    recent_timestamp = datetime.now(UTC).isoformat()
    _seed_audit_log("AUD-100003", recent_timestamp)
    app.state.backup_check_client.always_approve = True

    app.state.cleanup_orchestrator.run_cleanup_cycle()

    assert app.state.gateway.get_by_id("Audit_Log", "AUD-100003") is not None
