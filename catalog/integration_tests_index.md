# Per-Service Integration Tests — Consolidated Index

This is a consolidated, at-a-glance index of the 210 per-service integration tests spread across this project's 15 backend services. Each test hits its own service's real HTTP routes through FastAPI's `TestClient`, but against an in-memory Data Gateway stand-in rather than real Google Sheets or Kafka — so every row below proves that one service's own HTTP + business-logic + repository layers work together correctly, NOT anything about cross-service behavior. The 11 tests that do prove genuine cross-process, cross-service behavior (real subprocesses, real Kafka, real Sheets) are documented separately in `README.md`. Full 50-60-word detail for any test below still lives in that service's own `catalog/<n>.md` file under its `## Integration tests` section.

**These 210 tests also physically live in this repo now**, under `../tests/service_integration/<service>/`, and are **dual-mode**: run in-memory (as this page describes) or against the real Data Gateway Service/real Sheets, via `python run_local_integration_tests.py` (real is the default; `--gateway-mode=memory` opts into the fast, in-memory behavior this page documents) — see `../TESTING_GUIDE.md` section 8.5. Every definition below applies unchanged to both: the test only ever talks to `TestClient(app)`, never the Gateway backend directly, so the assertions and their meaning don't change based on which one is actually behind it. See `README.md`'s own note on this for the 4 real bugs that running these for the first time against the real Gateway found.

## User Service

| Test | Proves |
|---|---|
| `test_contacts_flow.py::test_create_enquiry_defaults_to_cold_rating` | A brand-new walk-in enquiry is created with 201, a "CT-" ID, defaults to "Cold" rating, and starts in "Enquiry" stage. |
| `test_contacts_flow.py::test_create_enquiry_accepts_social_media_source` | An enquiry tagged with a "Social Media" source is accepted and echoes that exact source back. |
| `test_contacts_flow.py::test_get_contact_returns_what_was_created` | A created contact is fetched back by ID and its name matches what was submitted. |
| `test_contacts_flow.py::test_get_unknown_contact_returns_404` | Requesting a nonexistent contact ID returns 404 instead of empty or broken data. |
| `test_contacts_flow.py::test_lifecycle_transition_enquiry_to_prospect` | A fresh enquiry advances to "Prospect" via the transition endpoint with a 200 and updated state. |
| `test_contacts_flow.py::test_list_contacts_filters_by_rating` | Filtering the contact list by rating=Hot returns only the one contact actually marked Hot. |
| `test_contacts_flow.py::test_skipping_a_lifecycle_stage_returns_409` | Jumping a new Enquiry straight to "Client" is rejected with 409 for skipping the required Prospect stage. |
| `test_contacts_flow.py::test_assign_rating_outside_the_active_ladder_returns_422` | Assigning a rating not in the configured ladder is rejected with 422. |
| `test_contacts_flow.py::test_assign_rating_within_the_active_ladder_succeeds` | Assigning a valid rating ("Hot") succeeds with 200 and the rating is updated. |
| `test_contacts_flow.py::test_set_enquiry_category_with_a_valid_category` | Tagging a contact with a configured enquiry category succeeds and the category is stored. |
| `test_contacts_flow.py::test_set_enquiry_category_with_an_invalid_category_returns_422` | Tagging a contact with a made-up category is rejected with 422. |
| `test_contacts_flow.py::test_link_sponsor_between_two_contacts` | Linking one contact as another's sponsor correctly reflects the sponsor's ID in the response. |
| `test_contacts_flow.py::test_link_sponsor_to_self_returns_409` | Linking a contact as its own sponsor is blocked with 409. |
| `test_contacts_flow.py::test_appointment_intake_and_conversion_to_contact` | A phone-enquiry appointment ("APT-" ID) converts into a full contact ("CT-" ID) carrying over the same phone number. |
| `test_health.py::test_health` | The health endpoint returns 200 with `{"status": "ok"}`. |
| `test_staff_ops_flow.py::test_check_in_then_check_out` | A staff check-in and same-day check-out are captured as one continuous attendance record. |
| `test_staff_ops_flow.py::test_get_attendance_range` | Querying attendance for a one-day range returns exactly the one record recorded on that date. |
| `test_staff_ops_flow.py::test_submit_leave_request_routes_to_the_office_director` | A Consultant's leave request auto-routes to the office Director and is marked "Requested." |
| `test_staff_ops_flow.py::test_submit_leave_request_with_bad_date_range_returns_422` | A leave request with an end date before its start date is rejected with 422. |
| `test_staff_ops_flow.py::test_decide_leave_request` | The assigned Director approving a leave request with a note records status "Approved" and preserves the note. |
| `test_staff_ops_flow.py::test_get_salary_with_no_attendance_data_returns_zero` | Salary for a period with no attendance data returns 0.0 with an explanatory note. |

## Application Service

| Test | Proves |
|---|---|
| `test_health.py::test_health` | Health endpoint returns 200 with `{"status": "ok"}`. |
| `test_art_review_flow.py::test_initiate_and_decide_art_review` | An ART review is created with no decision, then recorded as "Refused" with appeal initiated and a decided-at timestamp. |
| `test_art_review_flow.py::test_list_reviews_for_application` | Listing reviews for an application after one is initiated returns exactly that one review. |
| `test_art_review_flow.py::test_initiate_review_on_missing_application_returns_404` | Starting an ART review against a nonexistent application returns 404 instead of creating orphaned data. |
| `test_client_registration_gate_flow.py::test_full_gate_flow_advances_application_to_stage_two` | The full client-registration gate (signatures + paid invoice) advances the application to stage 2, promoting the contact to Prospect on open and Client once both documents are signed. |
| `test_client_registration_gate_flow.py::test_signature_request_and_invoice_creation_each_schedule_a_followup_reminder` | Requesting a signature and raising an invoice each fire a "reminder.schedule_requested" event with an email channel and future fire time. |
| `test_client_registration_gate_flow.py::test_redelivered_signature_webhook_is_idempotent` | A signature-completion webhook delivered twice only creates the document record once. |
| `test_client_registration_gate_flow.py::test_handle_signature_completed_resumes_after_a_partial_failure` | Replaying a signature-completion event after a partial failure resumes and completes the interrupted work without duplicating the document. |
| `test_client_registration_gate_flow.py::test_redelivered_payment_webhook_is_idempotent` | A payment-confirmation webhook delivered twice doesn't double-process the payment against the invoice. |
| `test_client_registration_gate_flow.py::test_invalid_coupon_code_is_rejected` | Raising an invoice with a nonexistent coupon code is rejected with 400. |
| `test_client_registration_gate_flow.py::test_valid_coupon_applies_discount_and_gets_redeemed` | A valid 10%-off coupon correctly discounts a $500 invoice to $450 and is marked redeemed afterward. |
| `test_application_flow.py::test_create_application_with_valid_dynamic_fields` | A new application is created with an "AP-" ID at stage 1, storing its submitted dynamic field exactly. |
| `test_application_flow.py::test_create_application_rejects_unknown_visa_type` | Creating an application for an unconfigured visa type is rejected with 422. |
| `test_application_flow.py::test_create_application_rejects_unknown_dynamic_field` | Submitting a dynamic field not on the visa type's schema is rejected with 422. |
| `test_application_flow.py::test_get_application_returns_what_was_created` | Fetching a created application by ID returns the matching record. |
| `test_application_flow.py::test_get_unknown_application_returns_404` | Requesting a nonexistent application ID returns 404. |
| `test_application_flow.py::test_update_dynamic_fields_merges_into_existing` | Updating dynamic fields merges the new field in alongside the original one rather than overwriting it. |
| `test_application_flow.py::test_record_trn` | A Transaction Reference Number recorded against an application is saved and returned exactly as submitted. |
| `test_application_flow.py::test_record_outcome` | Recording a final outcome ("Grant") against an application is stored and returned correctly. |
| `test_application_flow.py::test_compliance_status_reflects_active_checklist_items` | A fresh application's compliance status surfaces an active checklist item ("Form 956") as not yet completed. |
| `test_application_flow.py::test_assign_case_officer` | Assigning a named case officer returns a "CO-" prefixed assignment ID with the officer's name. |
| `test_application_flow.py::test_advance_stage_beyond_client_registration_gate_is_rejected` | Calling the internal pipeline service directly to skip the registration gate still raises InvalidStageTransitionError. |
| `test_inbound_document_flow.py::test_process_matches_by_trn_and_creates_rfi_request` | An inbound document carrying a matching TRN auto-links to the right application and creates an RFI request. |
| `test_inbound_document_flow.py::test_process_with_no_trn_match_lands_in_manual_review_queue` | An inbound document with no matching TRN is logged "unmatched" and surfaced in the manual-review queue instead of being discarded. |
| `test_inbound_document_flow.py::test_resolve_manually_marks_log_matched` | Manually resolving an unmatched document log links it to the correct application and records who resolved it. |
| `test_inbound_document_flow.py::test_resolve_manually_on_missing_log_returns_404` | Manually resolving a nonexistent document log entry returns 404. |
| `test_rfi_and_notification_flow.py::test_create_rfi_computes_reminder_date_from_lead_days` | Creating an RFI with a September 15 deadline auto-computes a September 12 reminder date, three days ahead. |
| `test_rfi_and_notification_flow.py::test_create_rfi_with_unknown_type_returns_422` | Creating an RFI with an unconfigured request type is rejected with 422. |
| `test_rfi_and_notification_flow.py::test_mark_rfi_handled_excludes_it_from_open_list` | Marking an RFI as handled flips its handled flag and drops it from the open-RFI list. |
| `test_rfi_and_notification_flow.py::test_create_notification_with_unknown_type_returns_422` | Creating a notification with an unconfigured type is rejected with 422. |
| `test_rfi_and_notification_flow.py::test_create_and_mark_notification_handled` | A "bridging visa" notification's details are stored exactly, and marking it handled flips that flag while it stays visible in the notification list. |

## Task Service

| Test | Proves |
|---|---|
| `test_health.py::test_health` | Health endpoint returns 200 with `{"status": "ok"}`. |
| `test_tasks_flow.py::test_create_task_against_a_contact` | A task created against a Contact returns 201 with a "TK-" ID, the contact's name as its label, and "open" status. |
| `test_tasks_flow.py::test_create_task_against_an_application` | A task created against an Application labels itself with the visa type plus application ID (e.g. "Skilled Migration (AP-000001)"). |
| `test_tasks_flow.py::test_create_task_against_a_missing_target_returns_404` | Creating a task against a nonexistent Contact ID returns 404. |
| `test_tasks_flow.py::test_create_task_with_an_unsupported_target_type_returns_422` | Creating a task against an unsupported target type ("Ticket") is rejected with 422. |
| `test_tasks_flow.py::test_get_task_returns_what_was_created` | Fetching a created task by ID returns the matching record. |
| `test_tasks_flow.py::test_get_unknown_task_returns_404` | Requesting a nonexistent task ID returns 404. |
| `test_tasks_flow.py::test_list_tasks_filters_by_assigned_staff_id` | Filtering the task list by assigned staff ID returns only that staff member's tasks. |
| `test_tasks_flow.py::test_update_task_status_to_done` | Marking a task "done" through its status endpoint returns 200 with the status genuinely persisted. |
| `test_tasks_flow.py::test_reassign_task` | Reassigning a task to a different staff member returns the new assignee in the response. |

## Reminder Service

| Test | Proves |
|---|---|
| `test_health.py::test_health` | Health endpoint returns 200 with `{"status": "ok"}`. |
| `test_reminders_flow.py::test_create_manual_reminder_against_a_contact` | A manual reminder against a Contact with a future fire time returns 201 with an "RM-" ID, source "manual," and status "pending." |
| `test_reminders_flow.py::test_list_reminders_filters_by_target` | Filtering the reminder list by one specific target returns only the reminder tied to that target. |
| `test_reminders_flow.py::test_create_manual_reminder_against_a_task_is_rejected` | Manually creating a reminder against a Task is rejected with 422, since Task reminders must be system-generated. |
| `test_reminders_flow.py::test_create_manual_reminder_with_a_past_fire_at_is_rejected` | Scheduling a manual reminder with a past fire time is rejected with 422. |
| `test_reminders_flow.py::test_get_reminder_returns_what_was_created` | Fetching a created reminder by ID returns the matching record. |
| `test_reminders_flow.py::test_get_unknown_reminder_returns_404` | Requesting a nonexistent reminder ID returns 404. |
| `test_reminders_flow.py::test_cancel_reminder_returns_204_and_removes_it` | Cancelling a reminder returns 204 and it's no longer fetchable afterward (404). |
| `test_reminders_flow.py::test_cancelling_an_unknown_reminder_is_a_no_op_not_an_error` | Cancelling a nonexistent reminder ID still returns success (204) rather than an error. |
| `test_reminders_flow.py::test_firing_sweep_fires_a_due_reminder_end_to_end` | Triggering the periodic sweep after a reminder's fire time fires it and removes it from the pending list. |

## Email Draft Service

| Test | Proves |
|---|---|
| `test_health.py::test_health` | The service's `/health` endpoint returns 200 with the exact body `{"status": "ok"}` — the only automated test that exists for this service so far; draft creation, templating, cc recipients, and the approval workflow have no coverage yet. |

## Graphics Service

| Test | Proves |
|---|---|
| `test_ai_generation_flow.py::test_poster_without_pii_masking_is_rejected_but_still_created` | A poster request submitted without PII-masking confirmation is rejected for AI summarization but still saved as "pending." |
| `test_ai_generation_flow.py::test_poster_with_pii_masking_triggers_generation_and_completes_on_callback` | A PII-masked poster request auto-queues AI summarization and completes to "generated" once the vendor stand-in finishes. |
| `test_ai_generation_flow.py::test_video_generation_triggers_on_raw_upload_not_at_creation` | Video AI generation stays "not applicable" until raw footage is actually uploaded, only then moving to "pending" then "generated." |
| `test_ai_generation_flow.py::test_non_ai_request_type_never_enters_generation_pipeline` | A banner request (no AI component) stays "not applicable" for generation forever. |
| `test_comment_flow.py::test_add_and_list_comments` | A comment posted on a story request is saved and immediately shows up when comments for that request are listed. |
| `test_comment_flow.py::test_comment_on_unknown_request_returns_404` | Posting a comment against a nonexistent content request returns 404 rather than creating an orphaned comment. |
| `test_content_request_flow.py::test_create_request_defaults_to_pending` | A new content request gets a "GRX-" ID, starts "pending" with no designer assigned. |
| `test_content_request_flow.py::test_get_request_returns_what_was_created` | Fetching a created request by ID returns the matching record. |
| `test_content_request_flow.py::test_get_unknown_request_returns_404` | Looking up a nonexistent request ID returns 404. |
| `test_content_request_flow.py::test_list_requests_filters_by_status` | Filtering the request list to "pending" includes a newly created request. |
| `test_content_request_flow.py::test_accept_request_assigns_designer_and_moves_to_in_progress` | A designer accepting a request flips it to "in_progress" and permanently attaches the designer's staff ID. |
| `test_content_request_flow.py::test_update_request_applies_partial_fields` | A partial update changes only the submitted fields (title, priority), leaving the untouched description intact. |
| `test_content_request_flow.py::test_update_request_after_cancellation_is_rejected` | Editing a cancelled request's title is blocked with 409. |
| `test_content_request_flow.py::test_cancel_request_twice_is_rejected` | Cancelling an already-cancelled request a second time is rejected with 409. |
| `test_file_upload_flow.py::test_upload_raw_files_updates_stats_and_timestamp` | Uploading a raw file to a reel request tags it "raw" and updates the raw file count and raw-uploaded timestamp. |
| `test_file_upload_flow.py::test_deliverables_upload_rejected_before_designer_accepts` | Uploading a deliverable to a still-"pending" request is blocked with 409 until a designer has accepted it. |
| `test_file_upload_flow.py::test_deliverables_upload_allowed_once_in_progress` | Once a banner request moves to "in_progress," uploading a deliverable succeeds and increments the deliverable file count. |
| `test_file_upload_flow.py::test_upload_rejected_once_cancelled` | Uploading a raw file to a cancelled reel request is rejected with 409. |
| `test_file_upload_flow.py::test_multiple_files_in_one_upload_all_saved` | Two files uploaded together in one batch both land as saved files and the raw file count reflects both. |
| `test_health.py::test_health` | The health endpoint returns 200 with a clean `{"status": "ok"}` payload. |
| `test_kpi_flow.py::test_kpi_summary_reflects_a_completed_request` | Running a full request lifecycle to completion is reflected in the KPI summary's completed and total counts for that requester. |
| `test_kpi_flow.py::test_kpi_summary_filters_by_designer` | Querying the KPI summary for a made-up designer ID returns a clean zero total rather than leaking other designers' stats. |
| `test_publishing_flow.py::test_publish_completed_request_to_multiple_platforms` | Publishing a completed request to Instagram and Facebook stand-ins both succeed and are recorded as published. |
| `test_publishing_flow.py::test_publish_rejected_for_non_completed_request` | Publishing a request that hasn't been completed through approval is rejected with a conflict error. |
| `test_publishing_flow.py::test_publish_to_unknown_platform_returns_400` | Publishing to a made-up platform ("myspace") returns a clean 400 rather than a server error. |
| `test_review_and_approval_flow.py::test_submit_for_review_requires_in_progress_or_changes_requested` | Submitting an accepted request for review moves it from "in_progress" to "review." |
| `test_review_and_approval_flow.py::test_approve_by_creator_completes_the_request` | The original requester approving a submitted-for-review request moves it to "completed." |
| `test_review_and_approval_flow.py::test_approve_by_wrong_actor_is_rejected` | An uninvolved staff member trying to approve a request in review is blocked with 403. |
| `test_review_and_approval_flow.py::test_request_changes_then_resubmit_and_approve` | After changes are requested, the designer can upload a revised deliverable, resubmit, and get approved normally in a full revision loop. |
| `test_review_and_approval_flow.py::test_video_request_routes_approval_to_client_not_creator` | For a video request with a designated client approver, the internal creator is forbidden from approving while the named client contact can. |

## Support Service

| Test | Proves |
|---|---|
| `test_health.py::test_health` | Health endpoint returns 200 with `{"status": "ok"}`. |
| `test_ticket_flow.py::test_create_ticket` | A new ticket with just customer ID, subject, and description gets a "TCK-" ID and starts "open" with the subject stored exactly. |
| `test_ticket_flow.py::test_create_ticket_with_target` | A ticket explicitly linked to an Application target echoes back the same target_type and target_id. |
| `test_ticket_flow.py::test_create_ticket_with_target_type_but_no_target_id_returns_400` | Submitting a target_type without a target_id is rejected with 400. |
| `test_ticket_flow.py::test_get_ticket_returns_what_was_created` | Fetching a created ticket by ID returns the matching record. |
| `test_ticket_flow.py::test_get_unknown_ticket_returns_404` | Requesting a nonexistent ticket ID returns 404. |
| `test_ticket_flow.py::test_list_tickets_filters_by_raised_by_id` | Filtering the ticket list by raised-by customer ID returns that customer's ticket. |
| `test_ticket_flow.py::test_list_for_target` | Querying the by-target endpoint for a Contact returns every ticket raised against that Contact. |
| `test_ticket_flow.py::test_full_lifecycle_open_to_closed` | A ticket walks its full lifecycle from open through in_progress, resolved, to closed, with a 200 and correct status at each step. |
| `test_ticket_flow.py::test_illegal_transition_returns_409_with_allowed_states` | Pushing a resolved ticket back to in_progress is rejected with 409, reporting current status and legal next states. |
| `test_ticket_flow.py::test_reopen_from_resolved_is_allowed` | Reopening a resolved ticket with a reason returns it to "open" with 200. |
| `test_ticket_flow.py::test_reopen_from_closed_is_rejected` | Reopening a closed ticket is rejected with 409, since closed is truly final. |
| `test_ticket_flow.py::test_reassign_ticket` | Reassigning a ticket to a different staff member returns the new assigned_staff_id with 200. |

## Data-Import Service

| Test | Proves |
|---|---|
| `test_health.py::test_health` | Health endpoint returns 200 with `{"status": "ok"}`. |
| `test_import_flow.py::test_submit_job_returns_202_with_the_job_queued` | Submitting a CSV import job is accepted immediately (202) with an "IMP-" job ID and "queued" status. |
| `test_import_flow.py::test_job_completes_synchronously_under_the_test_inline_runner_and_report_is_correct` | Under the test's inline runner, a submitted job completes immediately and its report correctly counts one imported, zero duplicates, zero failures. |
| `test_import_flow.py::test_submit_job_with_an_unrecognized_source_type_returns_422_and_creates_no_job` | Submitting a job with an unsupported source type ("sharepoint") is rejected with 422 and creates no job record. |
| `test_import_flow.py::test_submit_job_with_empty_raw_input_returns_422` | Submitting a job with a blank raw-input field is rejected with 422. |
| `test_import_flow.py::test_get_status_for_an_unknown_job_returns_404` | Requesting status for a nonexistent job ID returns 404. |
| `test_import_flow.py::test_get_report_for_an_unknown_job_returns_404` | Requesting the report for a nonexistent job ID returns 404. |
| `test_import_flow.py::test_a_second_submission_of_the_same_row_is_skipped_as_a_duplicate` | Submitting the identical contact row in two separate jobs imports it once and skips the second as a duplicate. |
| `test_import_flow.py::test_unparseable_raw_input_marks_the_job_failed` | A "google" source job supplied with plain text instead of JSON cleanly ends up marked "failed" rather than crashing or hanging. |

## Data Gateway Service

| Test | Proves |
|---|---|
| `test_health.py::test_health` | Health returns 200 "ok" and confirms the in-memory row-index has finished building and is ready. |
| `test_records_flow.py::test_create_record_allocates_a_gateway_id` | Creating a Task record as its owning caller gets a system-generated "TK-" ID rather than a caller-supplied one. |
| `test_records_flow.py::test_get_record_returns_what_was_created` | Fetching a created Task record by ID returns exactly what was stored. |
| `test_records_flow.py::test_get_unknown_record_returns_404` | Requesting a nonexistent Task record ID returns 404. |
| `test_records_flow.py::test_get_record_is_not_restricted_to_the_owning_caller` | Reading a Task record while identifying as a non-owning caller still succeeds with 200. |
| `test_records_flow.py::test_create_with_wrong_caller_returns_403` | Creating a Task record while identifying as a non-owning caller is blocked with 403. |
| `test_records_flow.py::test_unregistered_tab_returns_404` | Creating a record in a tab name the gateway never registered returns 404 rather than silently accepting it. |
| `test_records_flow.py::test_update_record_overwrites_fields` | Updating a Task's status through the owning caller correctly applies the field change end-to-end. |
| `test_records_flow.py::test_batch_get_preserves_requested_order` | Batch-fetching two records in a specific order returns them in that same requested order. |
| `test_records_flow.py::test_query_records_with_no_filters_returns_everything_in_the_tab` | Querying with no filter criteria returns every record in the tab. |
| `test_records_flow.py::test_query_records_filters_by_field` | Querying filtered by a distinctive status value returns exactly the one matching record. |
| `test_records_flow.py::test_query_records_is_not_restricted_to_the_owning_caller` | Querying the Task tab while identifying as a non-owning caller still returns 200. |
| `test_records_flow.py::test_delete_record_soft_deletes_by_default` | Deleting a Contact record without requesting hard delete still leaves it readable but flagged is_deleted true. |
| `test_records_flow.py::test_delete_record_hard_deletes_when_requested` | Deleting a Task record with hard=true makes a follow-up read return 404 instead of a soft-deleted stub. |
| `test_documents_flow.py::test_upload_document_returns_a_file_ref` | Uploading a base64 PDF into the Drive-backed ClientDocuments tab returns 201 with a file ID and shareable link. |
| `test_documents_flow.py::test_get_document_returns_the_uploaded_file` | Fetching an uploaded document back by its file ID returns the matching record. |
| `test_documents_flow.py::test_get_document_is_not_restricted_to_the_owning_caller` | Reading an uploaded document while identifying as an unrelated caller still succeeds with 200. |
| `test_documents_flow.py::test_upload_document_with_wrong_caller_returns_403` | Uploading a document while identifying as a non-owning caller is rejected with 403. |
| `test_documents_flow.py::test_delete_document_hard_delete_removes_it` | Hard-deleting an uploaded document makes a follow-up fetch for that file ID return 404. |

## Auth Service

| Test | Proves |
|---|---|
| `test_health.py::test_health` | Health endpoint returns 200 with `{"status": "ok"}`. |
| `test_auth_flow.py::test_password_login_succeeds_with_the_right_password` | Logging in with the correct identifier and password returns 200 with the staff ID, "Staff" account type, and an issued token. |
| `test_auth_flow.py::test_password_login_fails_with_the_wrong_password` | Logging in with the wrong password against a seeded account returns 401. |
| `test_auth_flow.py::test_login_with_neither_shape_returns_400` | Posting an empty login body with neither SSO token nor identifier/password returns 400. |
| `test_auth_flow.py::test_sso_login_with_a_fake_token_for_a_known_staff_identity` | Logging in via SSO with a token for an existing staff credentials record returns 200 with the matching staff ID. |
| `test_auth_flow.py::test_sso_login_for_a_first_seen_client_is_denied_by_default` | SSO login for a never-before-seen client identity is denied with 403 under the default deny-provisioning policy. |
| `test_auth_flow.py::test_validate_token_round_trip` | Validating a real session token obtained at login reports it valid and returns the matching staff ID. |
| `test_auth_flow.py::test_validate_token_rejects_garbage` | Validating a nonsense token string still returns 200 with `valid: false` rather than erroring. |
| `test_auth_flow.py::test_password_reset_full_flow` | The full self-service reset journey (request, confirm with OTP, re-login with new password) succeeds end to end. |
| `test_auth_flow.py::test_password_reset_confirm_with_wrong_otp_returns_400` | Confirming a password reset with a deliberately wrong OTP returns 400. |

## Admin Module

| Test | Proves |
|---|---|
| `test_health.py::test_health` | Health endpoint returns 200 with `{"status": "ok"}`. |
| `test_admin_config_controller.py::test_create_role_hierarchy_then_read_it_back` | Creating a Role_Hierarchy entry returns 201 with data echoed, and reading it back by tier name confirms the hierarchy level persisted. |
| `test_admin_config_controller.py::test_create_role_hierarchy_rejects_a_duplicate_role_tier` | Creating a second role tier under an already-used name is rejected with 409. |
| `test_admin_config_controller.py::test_get_config_for_a_missing_key_returns_404` | Looking up a Role_Hierarchy record for a nonexistent key returns 404. |
| `test_admin_config_controller.py::test_deactivate_role_hierarchy_returns_409_since_it_has_no_active_or_is_deleted_column` | Deactivating a Role_Hierarchy record is rejected with 409 since that config type has no active/deleted flag to toggle. |
| `test_admin_config_controller.py::test_create_update_deactivate_and_relist_an_rfi_type_config` | An RFI type config walks its full lifecycle: create, rename via update, deactivate, then shows as inactive (not deleted) when refetched. |
| `test_admin_config_controller.py::test_list_config_returns_every_row_for_that_config_type` | Listing NotificationTypeConfig rows after creating two returns both keys. |
| `test_admin_config_controller.py::test_create_config_for_an_unsupported_config_type_returns_400` | Creating a config record for an unrecognized config type name is rejected with 400. |
| `test_admin_config_controller.py::test_create_discount_coupon_auto_generates_the_coupon_id` | Creating a discount coupon without a supplied ID returns 201 with an auto-generated "CPN-" coupon_id. |
| `test_admin_config_controller.py::test_deactivate_discount_coupon_expires_it_instead_of_soft_deleting` | Deleting a discount coupon flips its status to "expired" rather than removing or soft-flagging the record. |
| `test_admin_config_controller.py::test_list_counters_returns_the_read_only_counters_tab` | The counters listing endpoint returns 200 with a list even with no counters explicitly created. |
| `test_admin_config_controller.py::test_get_counter_for_a_missing_prefix_returns_404` | Requesting a counter for a never-registered prefix returns 404. |
| `test_config_lookup_controller.py::test_get_role_hierarchy_reflects_rows_created_via_the_admin_surface` | A role tier created via the admin endpoint is visible with matching data through the separate read-focused role-hierarchy lookup route. |
| `test_config_lookup_controller.py::test_get_system_config_value_returns_the_stored_value` | A SystemConfig value set via the admin endpoint comes back unchanged through the dedicated system-config lookup route. |
| `test_config_lookup_controller.py::test_get_system_config_value_for_a_missing_key_returns_404` | Looking up a system-config value for a never-set key returns 404 rather than a null or default. |
| `test_config_lookup_controller.py::test_get_application_type_field_schema_returns_the_stored_schema` | An ApplicationTypeFieldSchema's dynamic fields are retrievable through the visa-type schema lookup route exactly as configured. |
| `test_config_lookup_controller.py::test_get_active_rfi_types_excludes_deactivated_rows` | The active-RFI-types lookup returns only the still-active RFI type, filtering out a deactivated one. |
| `test_config_lookup_controller.py::test_get_active_notification_types_excludes_deactivated_rows` | The active-notification-types lookup returns only the still-active notification type, filtering out a deactivated one. |
| `test_config_lookup_controller.py::test_get_active_compliance_checklist_filters_by_active_and_applies_to` | The compliance checklist lookup scoped to one visa type returns only the item both active and tagged for that visa type. |
| `test_config_lookup_controller.py::test_get_discount_coupon_looks_up_by_code_not_by_coupon_id` | Looking up a discount coupon by its human-readable code returns both the code and the generated "CPN-" ID correctly. |
| `test_config_lookup_controller.py::test_get_discount_coupon_for_a_missing_code_returns_404` | Looking up a discount coupon by a never-issued code returns 404. |

## Backup & Restore Service

| Test | Proves |
|---|---|
| `test_health.py::test_health` | Health endpoint responds successfully with an "ok" status. |
| `test_backup_flow.py::test_is_backed_up_false_before_any_backup_has_run` | With no backup history, asking whether data is backed up correctly answers false. |
| `test_backup_flow.py::test_is_backed_up_true_after_a_successful_backup` | After a real backup run succeeds, asking whether an earlier date's data is backed up now answers true. |
| `test_backup_flow.py::test_trigger_backup_succeeds` | Triggering a manual full backup returns 201 with a "BK-" run ID, status "succeeded," and run type "full." |
| `test_backup_flow.py::test_trigger_backup_while_one_is_in_progress_returns_409` | Starting a backup while one is already in progress is rejected with 409. |
| `test_backup_flow.py::test_trigger_filtered_export_succeeds` | Requesting a filtered CSV export of one report returns 201 tagged as a successful "filtered_export" run. |
| `test_backup_flow.py::test_trigger_filtered_export_with_an_unsupported_format_returns_422` | Requesting an export in an unsupported format ("xlsx") is rejected with 422. |
| `test_backup_flow.py::test_trigger_filtered_export_with_an_empty_report_name_returns_422` | Requesting an export with a blank report name is rejected with 422. |
| `test_backup_flow.py::test_initiate_restore_succeeds` | Restoring the "Contact" scope to a point in time returns 200 with a "partial" restore status and matching details. |
| `test_backup_flow.py::test_initiate_restore_with_missing_scope_returns_422` | Requesting a restore with an empty target scope is rejected with 422. |

## Audit Service

| Test | Proves |
|---|---|
| `test_health.py::test_health` | Health endpoint returns 200 with status "ok." |
| `test_audit_flow.py::test_ingest_event_returns_202` | Submitting a single audit event to the ingestion endpoint is accepted immediately with 202. |
| `test_audit_flow.py::test_ingested_event_appears_in_the_audit_trail_after_force_flush` | After forcing a buffer flush, querying that contact's audit trail returns the just-ingested event with the correct action. |
| `test_audit_flow.py::test_audit_trail_missing_target_type_returns_400` | Querying the audit trail without a target type parameter returns 400. |
| `test_audit_flow.py::test_audit_trail_missing_target_id_returns_400` | Querying the audit trail without a target ID parameter returns 400. |
| `test_audit_flow.py::test_malformed_ingested_event_is_dead_lettered_and_never_flushed` | An audit event missing its required actor_id is rejected outright with 422 before ever reaching the processing pipeline. |
| `test_audit_flow.py::test_multiple_events_batch_and_flush_together` | Three events submitted for the same contact and force-flushed once all appear together in that contact's audit trail. |

## Cleanup Service

| Test | Proves |
|---|---|
| `test_health.py::test_health` | Health endpoint returns 200 with status "ok." |
| `test_cleanup_flow.py::test_full_cycle_purges_old_rows_once_backup_is_confirmed` | With backup approval granted, a full cleanup cycle actually deletes old Audit_Log and Reminder History rows and reports them purged. |
| `test_cleanup_flow.py::test_full_cycle_skips_old_rows_when_backup_is_not_confirmed` | With backup confirmation denied, an old Audit_Log row is reported "skipped" and confirmed to still exist afterward. |
| `test_cleanup_flow.py::test_full_cycle_leaves_recent_rows_alone` | A recent (not-yet-aged) Audit_Log row is left untouched by a cleanup cycle even with backup approval granted. |

## Notes Service

| Test | Proves |
|---|---|
| `test_health.py::test_health` | Health endpoint returns success with a simple confirmation message. |
| `test_notes_flow.py::test_create_note_against_a_contact` | A note created against a Contact gets an "NT-" ID and is automatically marked staff-only visibility. |
| `test_notes_flow.py::test_create_note_against_an_application` | A "follow_up" note created against an Application correctly echoes Application as its stored target type. |
| `test_notes_flow.py::test_create_note_with_an_illegal_target_type_returns_422` | Creating a note against an unsupported target type ("Ticket") is rejected with a client error. |
| `test_notes_flow.py::test_create_note_with_an_unconfigured_note_type_returns_422` | Creating a note with a made-up, unregistered note_type is rejected with a client error. |
| `test_notes_flow.py::test_get_note_returns_what_was_created` | Fetching a created note by ID returns the matching record. |
| `test_notes_flow.py::test_get_unknown_note_returns_404` | Requesting a nonexistent note ID returns 404. |
| `test_notes_flow.py::test_list_notes_filters_by_author_id` | Filtering the notes list by author ID returns the note that author wrote. |
| `test_notes_flow.py::test_author_can_update_their_own_note` | The original author updating their own note's content succeeds and the new text is reflected. |
| `test_notes_flow.py::test_a_different_staff_member_cannot_update_someone_elses_note` | A different staff member trying to update someone else's note is blocked with 403. |
| `test_notes_flow.py::test_an_admin_identity_still_cannot_update_someone_elses_note` | Even an admin-role identity trying to update someone else's note is blocked with 403 — no admin override exists. |
| `test_notes_flow.py::test_author_can_delete_their_own_note` | The original author deleting their own note succeeds with 204. |
| `test_notes_flow.py::test_a_different_staff_member_cannot_delete_someone_elses_note` | A different staff member trying to delete someone else's note is blocked with 403. |
| `test_notes_flow.py::test_attach_review_does_not_change_content_or_author` | Attaching an admin review to a note records the review status and reviewer while leaving the original content and author untouched. |
