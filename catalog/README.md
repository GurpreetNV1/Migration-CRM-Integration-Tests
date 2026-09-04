# Test Catalog — Index

Every integration/unit test across every currently-built service, plus the 4 new true
cross-service tests in `../tests/`, each with a 50-60 word plain-English summary of what it
proves. Built for a demo: use this as narration/talking points rather than reading code live.

**743 tests documented total** — 739 existing per-service tests (already built, run via
`TestClient` against an in-memory Gateway stand-in, fully isolated from other services) plus the
4 new cross-service tests below (real, separate OS processes, real HTTP/Kafka).

## True cross-service tests (new, this repo)

These are NOT in the per-service catalogs below — they live in `../tests/` and are the
centerpiece of the demo, since they're the only tests proving the *system* works together rather
than one service in isolation.

| Test | Proves |
|---|---|
| `test_application_kafka_to_audit.py::test_application_created_event_reaches_audit_service` | Application Service → real Kafka → Audit Service: a real cross-process event lands and is queryable via Audit Service's own real HTTP API. |
| `test_support_kafka_to_audit.py::test_ticket_created_event_reaches_audit_service` | Same pattern against Support Service — confirms real Kafka delivery into Audit Service is a repeatable system property, not a fluke of one service's wiring. |
| `test_admin_config_shared_via_gateway.py::test_application_service_sees_config_written_by_admin_module` | Two independently-running service processes share live data through the real Data Gateway (not Kafka) — Admin Module writes a config row via its real API, Application Service reads it live to validate a request, with no direct call between the two services at all. |
| `test_graphics_full_lifecycle_over_http.py::test_poster_lifecycle_create_to_publish_and_kpi` | A complete real business flow (create → accept → submit for review → approve → publish → KPI query) driven entirely over real HTTP against a real Gateway-backed Graphics Service process. |

**A real bug was found and fixed while building these tests**: the real Data Gateway's
`update_by_id` used to do a full-row overwrite, silently blanking every column not explicitly
resent — invisible to every single-service test (which all run against a different in-memory
stand-in with correct merge semantics), and only caught because a true multi-process test
exercised the real Gateway end to end. See `12_data_gateway_service.md`'s entry for
`test_update_by_id_merges_onto_the_existing_row_instead_of_blanking_it` for the full story — good
material for explaining why this suite exists at all.

## Per-service catalogs (existing tests, 739 total)

| Service | Catalog | Tests |
|---|---|---|
| User Service | [01_user_service.md](01_user_service.md) | 86 |
| Application Service | [02_application_service.md](02_application_service.md) | 49 |
| Task Service | [03_task_service.md](03_task_service.md) | 50 |
| Reminder Service | [04_reminder_service.md](04_reminder_service.md) | 63 |
| Email Draft Service | [05_email_draft_service.md](05_email_draft_service.md) | 1 |
| Graphics Service | [07_graphics_service.md](07_graphics_service.md) | 42 |
| Support Service | [09_support_service.md](09_support_service.md) | 27 |
| Data-Import Service | [11_data_import_service.md](11_data_import_service.md) | 53 |
| Data Gateway Service | [12_data_gateway_service.md](12_data_gateway_service.md) | 82 |
| Admin Module | [14_admin_module.md](14_admin_module.md) | 117 |
| Backup & Restore Service | [16_backup_restore_service.md](16_backup_restore_service.md) | 46 |
| Audit Service | [17_audit_service.md](17_audit_service.md) | 40 |
| Cleanup Service | [18_cleanup_service.md](18_cleanup_service.md) | 36 |
| Notes Service | [19_notes_service.md](19_notes_service.md) | 47 |

Not yet built (no tests to catalog): Regional Office Service, Auth Service, OTP Forwarding
Module, Reports Service, Client Portal Service.

## Notable coverage gaps surfaced while cataloging (worth saying out loud in the demo, not hiding)

- **Email Draft Service has only 1 test** (a bare health check) — none of its drafting, source
  classification, templating, cc-recipients, re-check, or approval-before-send logic is covered
  yet.
- **Support Service's escalation-candidate detection for stale tickets** is referenced by a
  `TicketEscalationNotifier` class but has no test directly exercising the stale-ticket
  escalation behavior itself.
- Several services (Reminder, Notes, Data Gateway) have tests that exist specifically because a
  real production bug was found and fixed — see each catalog's entries for
  `test_add_pending_explicitly_sets_is_deleted_false_on_create` (Reminder),
  `test_attach_review_does_not_change_content_or_author` (Notes), and
  `test_update_by_id_merges_onto_the_existing_row_instead_of_blanking_it` (Data Gateway) for good
  demo material on how bugs were actually found in this project.
