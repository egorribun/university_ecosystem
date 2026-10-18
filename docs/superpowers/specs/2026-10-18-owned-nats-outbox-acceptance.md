# Owned NATS send-message acceptance

Date: 2026-10-18. Scope: owner-approved, single NATS-only outage in the existing disposable PR Core stand. Design source: [7444e5c](https://github.com/egorribun/university_ecosystem/commit/7444e5c298ae769abe0b75a25248f2fd71ad1686). Implementation and hosted acceptance remain separate requirements.

## Outcome and boundaries

Demonstrate that one committed message remains retryable while the stand's NATS is stopped, and that the same outbox event drains and the exact message reaches the existing CHAT_EVENTS broker stream after restoration. This is broker-storage evidence, not a ws-hub/browser consumer acknowledgement.

Preserve the original send-message scenario. Do not substitute a different event because it already retries. No new service, container, account, credential, exposed port, production target, main dispatch, scanner exception, skip identity or required-check change is permitted. Do not run the ordinary pytest database fixtures against this stand.

## Current defect and prerequisite

The durable message-sent outbox handler invokes ChatNotificationService with the broadcaster's best-effort NATS default. A disconnected publisher can return normally, allowing persistent notification work and the outbox processed timestamp despite no NATS delivery.

Add a keyword option with a false default to the notification service and forward it to the existing broadcaster's propagate_nats_failure option. Only the durable handle_message_sent handler opts in. Disconnected strict publishing must raise before persistent notification writes and the handler commit. Keep the existing notification transaction lock and exact message/reply deduplication keys for retries after later failures. Other callers retain their existing default behavior.

The existing in-process WebSocket fan-out happens before the NATS publish and may repeat on ambiguous failures. This change does not promise exactly-once frames. Preserve current durable message/refetch recovery and do not claim a recipient acknowledgement.

## Admission and identity

The live_stand wrapper holds its lifecycle lock and verifies the signed owner, daemon fingerprint, Compose resource fingerprint, Core service selection, and exactly one container for every selected service. Postgres/MinIO, backend, outbox worker and NATS must meet their existing healthy/running contracts. Every Compose operation uses the explicit owner project, generated overlay and control environment.

Read, but never create or rotate, the same project-bound generated admin credential. Fixed read-only database queries verify the active existing administrator and the reserved demo peer's exact email/seed identity. Require absence of a DM for that exact pair; never adopt a first/arbitrary/pre-existing chat.

Use the normal CSRF-cookie/login flow and an in-memory HTTP cookie jar, retaining the HttpOnly access cookie rather than assuming a JSON bearer token. Create one DM through the supported API, then verify its returned ID, type and exact participant set against the same owned database. Keep all identities private in memory. No one-off seed container is needed.

## Outage and exact correlation

Set restoration as required before attempting to stop NATS, so a partial stop error still enters restoration. Stop only the existing owned nats service. Send one short synthetic message through the supported multipart/form content endpoint.

Validate returned identifiers, then require the exact Message row and exactly one StoredEvent matching event type, aggregate identity and payload message/chat/sender identifiers. Retain that event ID for every subsequent query. Never select the latest row merely by event type.

Wait for a retryable outage attempt: processed_at is NULL, error_count is positive, and no failed_outbox_events row references that exact event ID. Restore immediately after observing the first retryable attempt, rather than waiting for a fixed outage period. The current worker's finite retry budget is five; terminal/DLQ state, absence of an attempt, malformed data and timeout all fail acceptance.

## Restoration and delivery receipt

Always start the same NATS service in finally. Start failure, health timeout, ownership drift, changed container identities or changed non-NATS runtime state fails acceptance. Revalidate the signed complete inventory before accepting a result. The workflow's existing always-run owner-scoped cleanup remains mandatory.

After healthy restoration, require that the same event has processed_at set, retains a positive error_count proving the outage attempt, and has no exact DLQ entry. Do not require status='processed': current success and DLQ paths do not maintain that status, and both stamp processed_at.

Independently confirm broker storage. CHAT_EVENTS already captures chat.* with file-backed retention. In the existing backend container, a bounded static Python stdin probe loads the existing NATS URL/token privately and uses locked nats-py to read get_last_msg for the exact chat subject. Never call the production broker connect helper, which reconciles streams, or add/update/delete a stream. Verify subject, envelope room, new_message payload type, chat ID and message ID against the retained HTTP/database identities. Only not-found is pollable; authentication, malformed payload and stream errors fail. No additional container, published port or public diagnostic endpoint is introduced.

The publish_core docstring's assertion that no chat stream exists is stale and must be reconciled with current stream provisioning. A successful Core publish or processed timestamp alone is not the broker receipt.

## Bounded execution and redaction

Use fixed read-only SQL through the existing postgres container, psql -X and ON_ERROR_STOP, validated UUID variables, read-only transactions and statement deadlines. Supply SQL through stdin, not interpolation into shell code or psql -c. Keep captured output private and bounded.

Set explicit HTTP, subprocess, first-attempt, restoration and drain/receipt deadlines. No indefinite reconnect loop or sleep-based success. Restore and close clients on every path.

Emit only closed stage/outcome labels and bounded boolean/count metadata. Never log passwords, tokens, cookies, UUIDs, message text, SQL rows, request/response bodies, DSNs or raw exception/subprocess output. Extend the metadata-only Core receipt with the acceptance outcome; preserve existing cleanup outcomes.

## Tests and publication order

1. Before production changes, obtain hosted RED for strict notification-service failure propagation, default-false compatibility and exact durable-handler opt-in. Preserve existing NATS strict-mode and outbox retry tests.
2. Apply only the scoped service/handler correction, retaining notification deduplication.
3. Add deterministic acceptance-helper tests for ownership admission, exact correlation, non-pollable errors, retry/DLQ distinctions, timeouts, restoration after partial stop and failures, and redaction. Review the live_stand adapter and fixed probe scripts separately.
4. Invoke the direct CLI after successful Core browser E2E and before existing always-run cleanup. Preserve the PR guard, full/frozen/nightly main-only boundaries, service closure and security controls.
5. Run the original send-message scenario in hosted PR Core and accept only exact pending/retry, restoration/health, drained/no-DLQ and broker-storage evidence on the published source. Keep any unexecuted or failed stage explicit.

## Verified probe API and privilege boundaries

The locked nats-py 2.16.0 [manager implementation](https://github.com/nats-io/nats.py/blob/v2.16.0/nats/src/nats/js/manager.py) implements get_last_msg through the non-direct STREAM.MSG.GET request with last_by_subj. It returns decoded RawStreamMsg data and does not create or alter streams or consumers. Keep direct=False. The [client error mapping](https://github.com/nats-io/nats.py/blob/v2.16.0/nats/src/nats/js/errors.py) preserves code and err_code; the pinned NATS 2.15.0 [server error registry](https://github.com/nats-io/nats-server/blob/v2.15.0/server/jetstream_errors_generated.go) defines 404/10037 as no message and 404/10059 as no stream. Only the exact missing-message error may be polled; missing-stream, unknown 404, authorization, transport and parse failures must fail closed.

Use the existing owner-pinned PostgreSQL bootstrap principal, not a new role. A read-only pg_roles query must confirm the current principal and its existing superuser visibility before relying on it; otherwise fail closed. Do not set app.bypass_rls, disable RLS, alter roles, or create credentials. Keep all probe queries read-only, with bounded statement time and deterministic transaction termination. Inspected partition migrations do not target these probe tables; verify actual relation identity/catalog shape rather than assuming an arbitrary database matches the fixtures.

Bound both ends of container exec: killing a local Docker client on timeout is not proof that its remote process exited. The backend Python probe needs its own asyncio deadline including connection, read and bounded close; psql needs a transaction-local statement timeout. Give the outer process budget enough margin for that bounded cleanup and do not report successful cleanup from a local timeout alone.

The seeded DM pairs the primary student with the reserved peer, not the administrator with the peer. Inspected browser fixtures do not deterministically create the proposed pair, but runtime absence is mandatory. Never silently reuse a pre-existing chat or widen account selection to make the proof pass.
