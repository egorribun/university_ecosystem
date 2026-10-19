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

Hosted RED was observed on e585: eight expected fragment/log assertions failed while all 37 analytics contracts passed. The minimal sanitizer correction is included and its focused GREEN is verified on dd17; full-source acceptance remains pending on the CI report transport failure. Synthetic credentials are generated in tests; no actual reset URL is used. Existing harmless #section1 and query-only behavior remain required.

## Execution record

- Tests-first c740 published the eight synthetic cases and bounded focused command without application changes. Fast pre-commit job 117926625749 stopped on Ruff joining adjacent f-strings; no backend assertion RED occurred. Apply only the exact hosted formatter output (blob f4e9fc02bd8c050c953821c0b7e8828528eecf2a) and rerun. Preserve all assertions and wait for genuine RED before implementing sanitizer changes.

- E585 job 117936457124 at 07:20:08 UTC: eight expected assertions failed, 37 analytics passed in 12.90 seconds; no setup errors. Full unit shard skipped after early RED; stop containers succeeded. Implementation was written only after inspecting this log. It parses/redacts fragment token/code pairs and preserves the original fragment when no value changes. No SMTP/runtime retry/configuration change is included.

- Independent static review found no code-level blocker. Three supplemental exact-output cases preserve harmless anchors, encoded anchor text and ordinary fragment parameters byte-for-byte. These are compatibility invariants added after the eight-case RED, not three more independently observed failures. The focused file now contains eleven cases.

- DD17 functional GREEN is verified: focused 48 (37 analytics plus eleven redaction/compatibility), Python 16446/174, frontend 9355/772, PostgreSQL 202/9 including 61-day history, zero uncovered frontend arms. Quality job 117960670190 passed with Python diff-cover 4527/0/100; exact-tree owned-live 20/2 cleanup artifact 12170756608 succeeded. Full acceptance remains open: one unchanged-source build retry passed after RSS failure, but CI Success twice failed its unscoped jobs API call (HTTP 502). The diagnostic request must be attempt-bound with tests first; no threshold relaxation or structural memory-fix claim. Existing browser smoke is not all Activity scenarios or 59 full-smoke specs.
