# Reset-link fragment log redaction

Date: 2026-10-19. Source reviewed: 895a7c46a709bbbaef8fb82d0c90832191abe134.
Scope: a narrowly related credential-log boundary discovered while reconciling AUD-471. This does not close the missing-production-SMTP finding or add another ID to the original 512-ID audit denominator.

## Evidence and outcome

AuthService now builds password-reset URLs with the credential in the fragment, /reset-password#token=. The shared email diagnostic sanitizer only parses query parameters and preserves the fragment. Both synchronous reset email and async task fallback/error diagnostics pass the link through that sanitizer. The structured log bridge masks token-named fields and email/phone values, but does not remove credentials embedded in the link field. This establishes a source-level exposure path, not evidence of an actual deployed incident.

Remove token/code values from both query and fragment diagnostics. Preserve existing harmless query values, harmless anchors, event names, email-body links and authentication behavior. Do not alter SMTP delivery/fallback policy in this patch; AUD-471 remains separate. No credentials, access changes, dependency or logging-suppression additions.

## Tests-first sequence

1. Publish tests/test_email_reset_fragment_redaction.py and add it to the existing bounded shard-zero focused regression command, preserving both analytics files, every full shard, coverage/provenance gates, timeout and exact temporary cleanup.
2. Observe hosted assertion RED for fragment credentials, including case-insensitive/encoded keys, duplicate/blank values, combined query+fragment, and real stdlib log records from synchronous/async development fallback. No production change before that evidence.
3. Correct only app/utils/email.py::_redact_sensitive_query after RED. Keep existing query-only behavior and harmless-anchor tests. Add any supplemental helper cases honestly as supplemental rather than independently observed pre-implementation RED.
4. Require focused GREEN, existing email tests, full backend/frontend/security/quality gates and own-source hosted live cleanup receipt. Verify baseline identity and required-context invariants. No merge/deploy.

## Current status

Tests and workflow extension prepared; application code unchanged. Hosted RED and acceptance are pending. Synthetic credentials are generated in tests; no actual reset URL is used. Existing tests preserve harmless #section1 and must keep passing.
