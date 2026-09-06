# Test Catalog — Index

Every unit/integration test across every currently-built service, plus the 11 true cross-service
tests in `../tests/`, each with a 50-60 word plain-English summary of what it proves. Built for a
demo: use this as narration/talking points rather than reading code live.

To actually run any of this yourself rather than just read about it, see
`../TESTING_GUIDE.md` — `python run_unit_tests.py` (607 tests) and
`python run_service_integration_tests.py` (210 tests) together run every per-service test below,
each well under a minute, in-memory; `pytest tests/ -v` runs the 11 true cross-service tests (~7
minutes, real Sheets/Drive/Kafka).

**828 tests documented total** — 817 existing per-service tests (already built, run via
`TestClient` against an in-memory Gateway stand-in, fully isolated from other services) plus the
11 true cross-service tests below (real, separate OS processes, real HTTP/Kafka/Sheets).

Of those 817, 210 are per-service **integration** tests (still in-memory, but exercise a real HTTP
route end-to-end within that one service) — see
**[integration_tests_index.md](integration_tests_index.md)** for a consolidated, at-a-glance
table of all 210, one line per test, same style as the cross-service table below. The remaining
607 unit tests have no equivalent single-page index — their full detail lives only in each
service's own `catalog/<n>.md` file, linked in the table further down.

## True cross-service tests (this repo's own `../tests/`)

These are NOT in the per-service catalogs below — they're the centerpiece of the demo, since
they're the only tests proving the *system* works together rather than one service in isolation,
and the only ones running against real Google Sheets/Drive rather than an in-memory stand-in.

| Test | Proves |
|---|---|
| `test_application_kafka_to_audit.py::test_application_created_event_reaches_audit_service` | Application Service → real Kafka → Audit Service: a real cross-process event lands and is queryable via Audit Service's own real HTTP API. |
| `test_support_kafka_to_audit.py::test_ticket_created_event_reaches_audit_service` | Same pattern against Support Service — confirms real Kafka delivery into Audit Service is a repeatable system property, not a fluke of one service's wiring. |
| `test_admin_config_shared_via_gateway.py::test_application_service_sees_config_written_by_admin_module` | Two independently-running service processes share live data through the real Data Gateway (not Kafka) — Admin Module writes a config row via its real API, Application Service reads it live to validate a request, with no direct call between the two services at all. |
| `test_graphics_full_lifecycle_over_http.py::test_poster_lifecycle_create_to_publish_and_kpi` | A complete real business flow (create → accept → submit for review → approve → publish → KPI query) driven entirely over real HTTP against a real Gateway-backed Graphics Service process. |
| `test_auth_login_against_real_gateway_credentials.py::test_login_succeeds_with_correct_password_and_rejects_the_wrong_one` | Auth Service validates a real bcrypt-hashed credential row through the real Gateway — correct password logs in, wrong password is rejected, and the issued token is checked. |
| `test_user_contact_rating_against_real_config.py::test_rating_assignment_validates_against_the_real_active_ladder` | User Service's rating strategy reads Admin Module's live `rating_ladder` config through the real Gateway rather than a hardcoded default — a real ladder value is accepted, a made-up one is rejected. |
| `test_task_stage_change_creates_task.py::test_full_registration_gate_publishes_stage_changed_and_task_service_creates_a_task` | **Flagship test.** The full real client-registration gate (signature request → both documents signed → invoice → payment) advances a real Application, publishes a real Kafka `application.stage_changed` event, Task Service auto-creates a Task from it, and Audit Service records the same event. |
| `test_reminder_sweep_fires_and_reaches_audit.py::test_a_due_reminder_fires_and_lands_in_audit` | Reminder Service's own real background sweep thread picks up a due reminder, moves it from pending to history in real Sheets, and publishes a correctly-attributed real Kafka event. |
| `test_data_import_reaches_a_terminal_status.py::test_a_submitted_job_never_hangs_at_processing` | A submitted import job always reaches a real terminal status — never hangs at "processing" — including a genuine Gateway ownership-rejection recorded with its actual reason. |
| `test_cleanup_purges_only_after_backup_confirmed.py::test_cleanup_purges_the_old_row_and_leaves_the_recent_one` | Cleanup Service only purges old Audit_Log rows once Backup & Restore has a confirmed successful run recorded — an old row is purged, a recent one survives. |
| `test_notes_ownership_and_config_driven_type.py::test_note_type_validation_and_ownership_guard_against_real_data` | Notes Service validates note_type against live Admin Module config and enforces its author-only ownership guard against real persisted data. |

**Real bugs were found and fixed while building these tests** — good material for explaining why
this suite exists at all, not just what it covers:
- The real Data Gateway's `update_by_id` used to do a full-row overwrite, silently blanking every
  column not explicitly resent — invisible to every single-service test (which all run against a
  different in-memory stand-in with correct merge semantics), and only caught because a true
  multi-process test exercised the real Gateway end to end. See `12_data_gateway_service.md`'s
  entry for `test_update_by_id_merges_onto_the_existing_row_instead_of_blanking_it`.
- Task Service's auto-task rule expected event fields the real `application.stage_changed` event
  never actually sends.
- The real Gateway's shared Google Sheets/Drive client wasn't thread-safe, so concurrent requests
  from multiple real services under this suite could corrupt each other's connection — only
  surfaced under genuine concurrent multi-process load, never in any single-service test.
- `Data_Import_Job`'s real Gateway schema was missing 4 columns the repository always wrote,
  silently dropping every failed job's recorded error reason.

## Per-service catalogs (existing tests, 817 total)

| Service | Catalog | Tests |
|---|---|---|
| User Service | [01_user_service.md](01_user_service.md) | 86 |
| Application Service | [02_application_service.md](02_application_service.md) | 65 |
| Task Service | [03_task_service.md](03_task_service.md) | 51 |
| Reminder Service | [04_reminder_service.md](04_reminder_service.md) | 65 |
| Email Draft Service | [05_email_draft_service.md](05_email_draft_service.md) | 1 |
| Graphics Service | [07_graphics_service.md](07_graphics_service.md) | 42 |
| Support Service | [09_support_service.md](09_support_service.md) | 27 |
| Data-Import Service | [11_data_import_service.md](11_data_import_service.md) | 54 |
| Data Gateway Service | [12_data_gateway_service.md](12_data_gateway_service.md) | 92 |
| Auth Service | [13_auth_service.md](13_auth_service.md) | 48 |
| Admin Module | [14_admin_module.md](14_admin_module.md) | 117 |
| Backup & Restore Service | [16_backup_restore_service.md](16_backup_restore_service.md) | 46 |
| Audit Service | [17_audit_service.md](17_audit_service.md) | 40 |
| Cleanup Service | [18_cleanup_service.md](18_cleanup_service.md) | 36 |
| Notes Service | [19_notes_service.md](19_notes_service.md) | 47 |

Not yet built (no tests to catalog): Email Drafting logic itself (Email Draft Service has only a
health check so far — see its own catalog entry), Reports Service, Client Portal Service,
Regional/Office Management Service, OTP Forwarding Module.

**These 210 integration tests also physically live in this repo now**, under
`../tests/service_integration/<service>/` — verbatim copies of the same files listed in each
catalog above, runnable **dual-mode** (real Gateway/real Sheets by default, or fast in-memory)
via `python run_local_integration_tests.py` — see `../README.md`/`../TESTING_GUIDE.md` section
8.5. Every definition in the tables below and in `integration_tests_index.md` applies unchanged
to both the original in-memory-only location and this dual-mode copy: each test only ever talks
to `TestClient(app)` and has no idea which Gateway backend is behind it, so the story a test
tells doesn't change based on which one actually receives the write.

**Running these for the first time against the real Gateway found 4 more real, previously-invisible
bugs**, in addition to the four already listed above — the same category of bug the true
cross-service tests exist to catch, just surfaced here instead because these copies are the first
time these particular 210 tests ever ran against anything but the in-memory stand-in:
- **User Service's `Contact` repository read an unset optional field as `""` instead of `None`**
  (real Sheets has no native null; the in-memory stand-in does), which made
  `ContactService.link_sponsor`'s "already linked?" guard misfire on a completely fresh contact.
  Fixed in `gateway_contact_repository.py`; same issue and fix in Graphics Service's
  `gateway_content_request_file_repository.py` for `duration_seconds`.
- **Graphics Service's `FileUploadService` called the Gateway client's generic `create()`
  instead of `create_document()` for raw/deliverable file uploads** — silently worked against the
  in-memory mock (no serialization), threw `TypeError: Object of type bytes is not JSON
  serializable` against the real HTTP client. Fixed in `file_upload_service.py`.
- **Admin Module's `DiscountCoupon` config registry let one malformed row crash every coupon
  lookup** — `get_all()` never guarded per-row parsing, so a single bad `type`/`discount_value`
  value taints the entire list. Fixed in `gateway_discount_coupon_repository.py` to skip and log
  instead of raising.
- **Data Import Service's core "import into any target entity type" feature cannot write into a
  tab it doesn't own** (e.g. `Contact`, owned by user-service) — a real, already-anticipated
  Gateway ownership rejection (see that service's own `ImportJobService._process_job` comment),
  not a bug, but the original tests only ever ran in-memory and never actually exercised it; the
  dual-mode copies assert the real "failed" outcome explicitly instead of the in-memory-only
  "completed" one.

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
