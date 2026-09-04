# Email Draft Service — Test Catalog

The Email Draft Service manages email drafts against a polymorphic target record (source-classified, templated, with cc recipients, a re-check status, and a staff-approval step before sending), storing everything through the shared Data Gateway; the current automated suite contains exactly one test, a single integration health check (0 unit tests exist yet).

## Integration tests

### tests/integration/test_health.py

- **test_health** — Confirms that the Email Draft microservice starts up cleanly and its liveness endpoint responds correctly, which is the most basic proof of life a service can offer. The test calls `GET /health` and checks that it returns an HTTP 200 status together with the exact body `{"status": "ok"}`. In a live demo this is the check to run first: if it fails, the service isn't reachable at all, so nothing about drafting, templating, cc recipients, or the approval workflow can be trusted or shown until this passes.

## Note for the demo

Only the health check exists today for this service — there are no tests yet covering draft creation, source classification, templating, cc recipients, the re-check status, or the staff-approval-before-send workflow described in the service's design. This is worth calling out explicitly in the demo as a coverage gap rather than a proven behavior.
