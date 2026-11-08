# Cumulative scoped review — AUD-426, AUD-231, and AUD-449 — 2026-11-06

Dated checkpoint, superseded by the current totals in [the audit index](INDEX.md).

This cumulative review preserves the prior scoped AUD-426 acceptance and
records separate criterion-specific acceptances for AUD-231 and AUD-449.
Together they account for 452 accepted / 512 (88.3%), with 60 open: 13
source-fixed/proof-pending, 35 partial, 9 unfixed, and 3
unverified/original-cause-unproven. These decisions do not imply overall CI or
release readiness.

## Prior scoped decision — AUD-426

The earlier November 6 decision accepted AUD-426 for its original MFA
challenge database-atomicity criterion. It preserved 449 earlier accepted IDs
and added only AUD-426, producing 450 accepted / 512 (87.9%) and 62 open at
that dated checkpoint. This cumulative review retains all 450 decisions and
adds only the separate AUD-231 and AUD-449 criteria below.

The finding describes MFA race tests that substituted an asyncio.Lock for
database atomicity. The [original finding inventory](AUDIT-2026-10.md) names
that criterion at AUD-426. The [November 1 review](AUDIT-2026-11-01-review.md)
kept it partial because both owned PostgreSQL race tests had skipped. The
hosted results below supersede only that execution gap.

## AUD-426 source and hosted job

The evidence is from PR #1343, source commit
[b8dbffd](https://github.com/egorribun/university_ecosystem/commit/b8dbffd),
tested in merge checkout
[0fee48b](https://github.com/egorribun/university_ecosystem/commit/0fee48b)
against base
[b85516e](https://github.com/egorribun/university_ecosystem/commit/b85516e).
The exact direct test and production-code pins match between the source and
merge checkout: test module blob 17ce0b97, challenge module blob 7cbcfdc8,
login route blob 4a495986, and merge workflow blob 7bcaa506. Full source and
receipt hashes are retained in the private evidence receipt at
.git/ue-audit-work/2026-11-06/max64/luna_ci_postgres/aud426_hosted_receipt.md.

The source-bound hosted run is [Actions run 42265996095, job
128059490030](https://github.com/egorribun/university_ecosystem/actions/runs/42265996095/job/128059490030),
“Backend Tests (Python 3.14-shard-0) / Integration Tests
(All-Python 3.14-shard-0).” PostgreSQL service health succeeded. The named
step “Run PostgreSQL proofs (AUD-426, AUD-447) without skips” collected six
tests and logged these two AUD-426 results as PASS, not SKIP:

- tests/security/test_mfa_race.py::test_mfa_challenge_race_condition
- tests/security/test_mfa_race.py::test_mfa_step_up_challenge_verification_race

The [pinned test module](https://github.com/egorribun/university_ecosystem/blob/b8dbffd/tests/security/test_mfa_race.py#L30-L160)
uses ten concurrent requests per race through a loopback Uvicorn server and
HTTP client. The normal application request dependency opens a separate
AsyncSession for each request, so competing verifications contend through
PostgreSQL instead of sharing a Python session. Each case expects exactly one
successful verification and nine rejections. The step-up case creates one
challenge through the HTTP endpoint,
verifies that same challenge concurrently, and checks that exactly one
step-up challenge was consumed. Its skip marker requires a PostgreSQL
DATABASE_URL; the hosted log records PASS for both cases after PostgreSQL
service health succeeded.

Production challenge consumption uses PostgreSQL row locks and a post-lock
challenge re-read in
[challenge.py](https://github.com/egorribun/university_ecosystem/blob/b8dbffd/app/auth/mfa/challenge.py#L477-L595).
The login route calls that consumer for MFA verification in
[login.py](https://github.com/egorribun/university_ecosystem/blob/b8dbffd/app/api/auth/login.py#L284-L295).
The test requests are concurrent at the HTTP boundary; there is no
Python-level lock serializing any of the ten competing verifications in either race.

## AUD-426 limits retained

The next test in the same step was an AUD-447 PostgreSQL case, which failed.
Therefore the whole job and named step remain failed. The shell's fail-fast
behavior prevented its following six-case XML validator from running.
Although the command generated pg-proofs.xml, the workflow did not upload it.
The saved hosted job log is the direct result evidence for these two named
tests; no complete six-case proof or AUD-447 acceptance is claimed.

This scoped acceptance does not turn the job or overall CI GREEN, waive any
of the 78 required context/app pairs, establish release readiness, or change
policy and quality thresholds. The dated November 1 63-finding matrix remains
available as a historical snapshot at its preserved
[preserved 63-finding anchor](AUDIT-2026-10-30-reconciliation.md#current-63-finding-reconciliation--2026-11-01).


## AUD-231 — compiled SSR CSP and nonce proof in Chromium

The accepted scope is the compiled production SSR login response: the server
composes CSP and its nonce with the SSR bootstrap, the application hydrates,
and an untrusted inline script without a nonce is blocked by the enforced
policy. A paired stripped-policy control proves the same probe executes when
response policies are removed.

### Source pins

The reviewed source is b8dbffd. The critical SSR/CSP/login/config/spec chain
below matched that source and the current tree; the later published integration
at fff85be leaves those relevant source and test blobs unchanged. Full pins and
private receipts are retained in the evidence package under
.git/ue-audit-work/2026-11-06/max64/luna_a164/frontend-build-current-001 and
.git/ue-audit-work/2026-11-06/max64/luna_browser_csp.

| Critical input | SHA-256 prefix |
|---|---|
| frontend/src/server.ts | e7f46bcc9044 |
| frontend/src/routes/_public/login.tsx | f522614500e5 |
| frontend/src/routes/__root.tsx | 73ceeef90c11 |
| frontend/src/routeTree.gen.ts | 10fde53d4792 |
| frontend/vite.config.mts | 81ff287ea0d8 |
| frontend/scripts/server-prod.mjs | 2194ff195510 |
| frontend/scripts/server-csp.mjs | f33c4bbc54fc |
| frontend/playwright.ssr.config.ts | e558c67d37ab |
| frontend/playwright.config.ts | 19c48d6daee7 |
| frontend/tests/e2e-live/production/ssr-csp-browser-negative.spec.ts | 183c54aceb8b |
| frontend/scripts/post-build-shell.mjs | 0d10e1f295f5 |

The prior broad source-input map covered 2,238 files. A later comparison with
the then-current worktree found six changed inputs: frontend/.gitignore,
frontend/scripts/live-e2e-security.test.mjs,
frontend/src/api/__tests__/client.etag-retry.test.ts,
frontend/src/test/__tests__/wasmFuzzer.artifact.test.ts,
frontend/src/utils/scheduleExport.ts, and
frontend/tests/e2e-live/zzz-aud174-prehydration-caddy-log.contract.test.mjs.
The scheduleExport module is production code, so this evidence is not
described as a build of the complete current frontend tree. The critical chain
in the table above remains the source-bound subject of these browser results.

### Browser results

Two independent headless Chromium runs used the existing
frontend/tests/e2e-live/production/ssr-csp-browser-negative.spec.ts spec with
the canonical SSR Playwright configuration. Each run passed both named cases
(2/2); receipt SHA-256 prefixes are af1285ed08f0 and 4acf90423e95:

- SSR document CSP in a browser: blocks untrusted inline script while the
  server bootstrap hydrates.
- SSR document CSP in a browser: the untrusted probe executes when the
  response policies are removed.

The first case requests the compiled production /login document. It verifies
the login form is present in the original server bytes, the CSP nonce equals
the nonce meta value and the nonce-bearing $_TSR bootstrap value, and the
bootstrap hydrates the page. A nonce-less inline probe does not execute; the
browser observes an enforced script-src violation. The test also checks
Trusted Types enforcement, the allowed wasm-unsafe-eval capability, and that
raw eval and untrusted string sinks remain blocked.

The paired control removes the response CSP policies while serving the same
login document and confirms that the untrusted probe executes. Each compiled
snapshot contained 676 inventoried artifacts, but behavioral evidence covers
the /login SSR response and this browser probe only.

### Limits retained

The browser harness talks directly to the compiled frontend server and bypasses
Caddy. Static Caddy configuration inspection found no CSP header mutator, but
there is no live through-Caddy result. The frontend-only run has no backend:
CSP report POSTs returned 404, so no backend report-ingestion result is claimed.
The broad source map also contains later differences, including production
scheduleExport code; no full-current-tree build, all-page CSP claim,
Compose/deployment result, or overall CI GREEN is implied. The full receipt
hashes and build pins remain in the private evidence package.


## AUD-449 — Caddy and Gunicorn access-log redaction

The accepted scope is the original Spotify OAuth code access-log criterion for
the checked-in TLS Caddy edge configuration and plain development Caddy
configuration, together with the production Gunicorn command on the Spotify
callback path. The source-bound PR run used source b8dbffd and tested merge
0fee48b; their trees matched. The later published integration at fff85be left
the relevant source blobs unchanged. The overall PR run concluded failure in
another job, while the named [Caddy emitted-log redaction job
128059488644](https://github.com/egorribun/university_ecosystem/actions/runs/42265996095/job/128059488644)
completed successfully.

The Caddy job passed four named cases: three TLS edge configurations
(`None`, an empty list, and `ops@example.invalid`) and the plain development
edge configuration. The TLS cases sent a long Spotify-shaped `AQ` code to
`/api/v1/spotify/callback` and checked actual container logs: the raw code was
absent while the redacted code marker and callback URI were present. The
Gunicorn proof
`tests/aud178_449_gunicorn_proof.py::test_real_gunicorn_worker_emitted_logs_exclude_reset_and_oauth_targets`
completed without skips, and its JUnit receipt was validated by the job. It
runs a real worker using the command read from backend.Dockerfile, exercises
the callback with a synthetic code, confirms an intentionally unsafe command
logs that marker, and confirms the production command does not. The private
scoped-review receipt SHA-256 prefix is 33cdf0365fdd.

| Reviewed input | Git blob prefix |
|---|---|
| services/caddy/Caddyfile | 330c365d |
| infrastructure/Caddyfile | faed29cb |
| tests/test_caddy_emitted_log_redaction_docker.py | 11c67109 |
| tests/aud178_449_gunicorn_proof.py | 9962748d |
| backend.Dockerfile | c6637758 |
| .github/workflows/ci.yml | ba7e5a3a |
| .github/scripts/ci/verify_aud178_449_gunicorn_receipt.py | 1f3d4879 |

This is evidence for the checked-in edge configurations and production worker
command with synthetic request values. It does not prove absence from
unrelated application logs, exercise app.main or the full backend image, or
show a live Spotify callback. It does not change the failed conclusion of the
overall hosted run or establish overall CI or release readiness.
