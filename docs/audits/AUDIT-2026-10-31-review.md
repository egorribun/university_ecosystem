# Post-pause review: 2026-10-31

## Scope and evidence boundary

This review covers the complete [adb5c91f to 112efb38 comparison](https://github.com/egorribun/university_ecosystem/compare/adb5c91f0f2e4fdcd976641ddbb8f25810662883...112efb38055caa8ce46717e3d6c23333bc07be4d), not an arbitrary sample or only failing checks.
The range contains one direct-child commit, published at 2026-10-31 04:45:57 UTC: `fix(security): close CI regressions and continue audit hardening (checkpoint)`.
Both recursive Git trees were non-truncated. Their exact file/blob/mode difference matches the complete comparison: **98 paths, 87 modified and 11 added, no deleted or renamed paths**. There are no additional intermediate commits or hidden reverted paths in this range.

Every changed hunk, all new code, and relevant surrounding producers, consumers and controls were reviewed. This does **not** claim line-by-line rereview of unrelated unchanged code in all repository files. The partition was backend 16, frontend 22, realtime 19, infrastructure 17 and cross-cutting workflows/policy 24 paths. The complete manifest appears below.

The reviewed head tree is `47ff2d083a9e8f57e4dfddd8fae96bb86b969ba5`. Relevant hosted jobs checked out PR merge `a0314c8854715c76400a24c114fdb3ba90b4f540`, whose complete tree was independently matched to the head. Receipts are therefore source-equivalent; they are not described as literal direct-head checkouts or proof of a production deployment.

At the reviewed head the published cumulative registry is **437 accepted / 75 open / 512 total**. AUD-350 is still accepted; AUD-244, AUD-399, AUD-400, AUD-477 and AUD-489 are still open. Candidate acceptance and the AUD-350 correction below are not publication.
The current baseline is **315 identities**: exact comparison confirms only the four authorized retired Secret Keyword identities were removed, with no additions; other record changes are two chart line numbers and the generation timestamp. The 494 finite dispositions and 26 historical Gitleaks fingerprints are unchanged.

## Confirmed observations and remaining causes

### Workflow results and execution

- **Nuclei native JSON mismatch:** the pinned 3.11.1 exporter writes an array, including `[]`. The new `jq -s` consumer wraps that array again, rejects valid clean exports and accepts a zero-byte existing file as zero findings. Existing source-string assertions do not execute this parser. Eight executable cases are prepared separately; until their own run, this is source-confirmed, not observed semantic RED. [Pinned exporter](https://github.com/projectdiscovery/nuclei/blob/v3.11.1/pkg/reporting/exporters/jsonexporter/jsonexporter.go).
- **SQLMap retained-result/completion gap:** a per-host log exists before connection testing; its existence does not prove completion. With `--flush-session`, a later same-host target opens the log in write mode and can erase an earlier injection finding. Multi-target CSV records techniques but not the phrase searched by the workflow. Requiring a nonempty log alone would incorrectly reject legitimate clean scans. These are pinned-source findings, not executed scan fixtures.
- **Nightly artifact recovery gap:** cache save precedes artifact publication. A successful cache save followed by failed upload leaves a same-run cache hit that skips both execution and upload, while the aggregator reads artifacts only. Exact run/SHA/shard lineage and completeness checks remain strict; this is a recovery failure, not permission to relax them.
- **Zizmor suppression removal:** `rules: {}` removes the fifteen disabled audit rules. Actual SARIF contains **115 findings: 92 note, 1 warning and 22 error across eight rules**. The action uploaded it and returned success. Success is not a clean scan and does not dispose of those findings.
- **Catalog drift:** the immutable Dependabot-author guard and new SQLMap artifact metadata were not reflected in the catalog. No required-check, profile or timeout change is needed.
- **Checkov setup failure:** its generated staging profile lacks the backend proxy list now required by the chart. Scanner execution never starts; missing reports are cascades, not IaC findings. The repair must retain the fail-closed guard and use the already-existing finite documentation-address fixture.
- **Other current contract failures:** the frozen full-backend source contract and OSV custom-manager cardinality need exact reconciliation rather than blanket hash refreshes or weaker expectations. Two additional Helm tests omit the new backend proxy prerequisite; actual renderer support through `HELM_VALUES_FILE` is retained.

### Application and security boundaries

- **AUD-375 remains partial:** CSRF forwarding and genuine terminal 401/403 deletion are repaired. A batch retains credentials across delayed writes; same-session CSRF rotation or an account transition can produce an unsafe stale second request and destructive 403 cleanup. Retry bookkeeping does not itself schedule a later attempt. No-Web-Locks fallback is instance-local, not proven cross-worker exclusion. New controlled regressions are prepared off-branch and unexecuted; they are tests-first, not browser/backend integration proof.
- **AUD-478 remains partial:** bounded revocation replay does not gate startup readiness/admission until retained invalidations have cleared shared Redis L2 allows. Seven-day stream retention also cannot cover accepted token/replay configurations exceeding seven days. Existing integration-package success is not the missing readiness/L2 proof.
- **Password inventory false negative:** the image-gate reader has no authorized RLS-bypass role, while the CLI sets only the now-inert ordinary bypass GUC. The seeded active bcrypt sentinel is hidden and the CLI returns zero instead of the required nonzero result. Fix authorization checks without restoring user-settable GUC bypass or silently granting production privileges.
- **AUD-258 fixture mismatch:** the participant probe lacks a matching tenant. A visible count of zero after membership restoration is not evidence of physical message deletion. Existing large-page/locking cases pass; the authentic repair must retain tenant and membership negatives, committed-row preservation, 403 and no-cleanup-event controls.
- **DND tests do not reach their bodies:** current ancestry already preserves four legacy columns, but the fixture blindly adds them and raises DuplicateColumn. Replacing that reconstruction with exact parent catalog assertions is separate from migration changes. The fixture is historically source-pinned; editing it must not silently refresh or waive that binding.
- **AUD-350 acceptance is narrower than its original criterion:** two real PostgreSQL passes establish the target-column naive-UTC conversion. They do not eliminate the original populated-table rewrite/locking risk. The new selected-AST comparison also no longer binds the entire candidate migration. Preserve the UTC receipt but correct the unsupported full acceptance.
- **Owned reset replay remains unresolved:** the URL-cleanliness poll fails on reopening the used link before replay form submission. The composite failure does not distinguish a wrong route from retained token material and does not establish a backend replay-rejection regression. Any diagnostic must use only fixed Boolean fields, retain the original assertion and never print URLs or tokens.

### Dependencies

The new Caddy graph is real, locked and built with readonly resolution; image scanning also executes against a Go binary. It nevertheless contains required `go-jose/v3 v3.0.5`, flagged by Dependency Review under [GHSA-mgcc-cww5-fp2q](https://github.com/advisories/GHSA-mgcc-cww5-fp2q). The advisory has no verified released v3 fix. Caddy's v4 override does not fix v3, and a filtered Trivy success with `ignore-unfixed` is not proof of absence. Smallstep crypto 0.91.1 retains v3 and is not a narrow remedy.

The existing, unchanged frontend lock contains `follow-redirects 1.16.1`, flagged under [GHSA-mrwp-f3q8-3g9p](https://github.com/advisories/GHSA-mrwp-f3q8-3g9p); 1.16.2 is the approved targeted update. The advisory reports that Axios 1.20.0 did not reproduce its cross-realm case; no application credential leak is asserted. The separate approved go-jose/v4 4.1.7 update must preserve other pins and validate its 32-signature/recipient and malformed-key compatibility changes. Neither update is claimed published by this report.

## Hosted receipts at the reviewed source

- [Frontend Matrix](https://github.com/egorribun/university_ecosystem/actions/runs/41169911427): **10,647 tests pass in 846 files**; all 14 changed test files contribute 252 cases. Changed-line aggregate reports 100%. These are unit/mocked-boundary receipts, not all coverage metrics or real worker lifecycle.
- All four backend unit shards are terminal: **22,662 pass / 27 fail / 430 skip**. Shards 0/1/2/3 report respectively **4,338/6,210/5,034/7,080 passes**, **7/0/6/14 failures**, and **113/85/127/105 skips**. Matrix has **91 jobs: 60 success, 15 failure and 16 skipped**, with none running or cancelled. Across all 23 source workflows, 17 succeed, 4 fail and 2 skip. No full backend or aggregate policy GREEN is claimed.
- [Owned Core](https://github.com/egorribun/university_ecosystem/actions/runs/41169911345): **46 pass / 2 fail / 2 skip**, plus 338 Node contract passes and one adapter pass. Both live failures precede reset replay submission; outage proof is skipped.
- [Migration gate](https://github.com/egorribun/university_ecosystem/actions/runs/41169911427/job/124446292301): 91 focused migration tests and two target-column UTC PostgreSQL tests pass; the later password-image preflight fails.
- [Alembic](https://github.com/egorribun/university_ecosystem/actions/runs/41169911427/job/124446292354): **127 pass / 2 fail / 3 setup errors**. The three DND preservation tests are not passes.
- [ws-hub race](https://github.com/egorribun/university_ecosystem/actions/runs/41169911427/job/124446688465): named pre-ACK oversize, deliverable ACK, marshal-failure and authorized-join fence controls pass; metrics lifecycle controls pass with 100% reported statement coverage. Separate integration job passes four packages but is nonverbose.
- [Production audit service](https://github.com/egorribun/university_ecosystem/actions/runs/41169911427/job/124445430190): 57 named cases pass, including 29 key/signer/status controls and independent fixed-wire tamper fixtures. The overall Contract job still fails for other reasons.
- [Zizmor](https://github.com/egorribun/university_ecosystem/actions/runs/41169911262/job/124445428100): SARIF publication succeeds with the 115 findings stated above.


AUD-311 and AUD-490 remain S without requiring a particular report format. The four terminal main-run selections sum to 23,119 cases, exactly matching 22,662 passes, 27 failures and 430 skips. Both target modules are absent from all reported failure and skip lists. However, the existing collection-manifest verifier, which checks equal collected universes and a disjoint complete selected union, was skipped with Coverage & Quality Policy. The four and seven target cases therefore have conditional cohort-pass inference, not established actual selection.

## All 75 open findings reconciled

Classes: **U** unfixed; **P** partial; **S** source-fixed but applicable proof not established here; **C** original criterion confirmed within the stated boundary, still unpublished; **N** not verified or original cause unproven.
Counts: **12 U, 37 P, 18 S, 5 C, 3 N**. For paths unchanged by this range, the prior immutable review's disposition is carried forward explicitly; it is not new execution or inherited GREEN. Source changes and current receipts supersede obsolete objections where noted. AUD-350 is an accepted-entry correction outside this 75-ID complement.

| Finding | Class | Evidence boundary or remaining condition |
|---|---|---|
| AUD-073 | S | Fresh 7 numerical/source tests pass; 101 gradient samples do not establish browser cascade/compositing contrast. |
| AUD-154 | S | Renderer markers repaired; actual realtime E2E locator/response chain unproved. |
| AUD-164 | P | Mandatory proxy configuration and Helm wiring retained; real two-client spoof-resistant limiter composition unproved. |
| AUD-167 | P | Trusted-proxy and rate-limit composition requires real topology proof. |
| AUD-169 | P | Declaration repairs retained; actual Secret URL, endpoints, DNAT and dependencies remain owner-proof hold. |
| AUD-178 | P | Fragment/referrer/redaction repairs retained; legacy URL CSP/Referer/emitted-log chain unproved. |
| AUD-188 | P | JWKS policy declarations improved; actual endpoint/refresh topology unproved. |
| AUD-189 | P | Tighter egress declarations retained; actual topology unproved. |
| AUD-208 | P | Raw warning gate remains strict; finite Squawk admission is prepared-inactive. |
| AUD-226 | P | Real-UTC expiry enforcement retained; finite 131-file exception and complete migration coverage remain. |
| AUD-231 | S | Helpers/stubs do not prove compiled SSR CSP/nonce composition and untrusted-script negatives. |
| AUD-244 | C | Fifteen disabled Zizmor audits removed; actual SARIF upload has 115 findings, not a clean scan. |
| AUD-245 | U | Global SPIRE Trivy suppressions still lack bounded path/expiry disposition. |
| AUD-251 | P | List/watch removed; cluster-wide nodes/proxy GET and live RBAC proof remain. |
| AUD-269 | S | Eight non-equivalent indexes preserved in source; applicable populated-chain proof unestablished. |
| AUD-270 | S | Source refuses instead of truncating; populated-chain proof unestablished. |
| AUD-272 | U | attempted_at/nullable uniqueness weakness remains. |
| AUD-274 | S | Parent preserves DND/timezone columns; three current preservation tests error before bodies on DuplicateColumn. |
| AUD-275 | P | Concurrent reply index added; interrupted/invalid-index recovery and users-index scope remain. |
| AUD-277 | N | Original USING(true) bypass cause was not established independently of restrictive policies; assess NULL/GUC separately. |
| AUD-278 | S | Events GIN restoration moved into upgrade; applicable PostgreSQL proof unestablished. |
| AUD-309 | U | Generic live-stand subprocess and POSIX/Windows lock waits remain unbounded. |
| AUD-311 | S | Filename Tier0 ownership rules added; four cases have only conditional cohort-pass inference because actual collection-union verification was skipped. |
| AUD-313 | U | Owned-stand environment/host checks and existing-admin password reconciliation remain. |
| AUD-321 | S | Conditional E2E handling repaired; affected fixtures/oracles unexecuted in reviewed evidence. |
| AUD-322 | P | Selected event CRUD proof does not establish active chaos execution. |
| AUD-327 | U | Legacy-role enum addition/use in one transaction remains; empty-chain success is insufficient. |
| AUD-332 | U | Windows symlink tests still lack native privilege probe. |
| AUD-334 | P | Named admission-refusal controls pass; blocked-writer and current/superseded replay composition remain. |
| AUD-346 | U | Nightly chaos dry-run does not execute recovery. |
| AUD-347 | S | MinIO source selection repaired; non-skipped ToxiProxy/MinIO execution unestablished. |
| AUD-348 | P | Backfill precedes DROP; existing empty destination rows may still exclude legacy Spotify values. |
| AUD-351 | S | Source handles incompatible queue IDs; authentic populated-row PostgreSQL preservation unproved. |
| AUD-360 | P | NULL rows hidden and INSERT triggers stamp tenants; all ordinary API producers remain unproved. |
| AUD-373 | U | Token-bearing backend HTTP hop remains unencrypted; Temporal JWKS HTTPS is another boundary. |
| AUD-375 | P | CSRF forwarding and genuine terminal 403 deletion repaired; cross-worker fallback and stale batch credentials remain. |
| AUD-378 | U | Version/ci.yml checks are not SLSA attestation verification. |
| AUD-380 | U | Promised Semgrep CI job remains absent. |
| AUD-381 | P | Scanner gates added, but Nuclei native-array parser and SQLMap completion/result retention are defective. |
| AUD-384 | S | Slack if now consumes step output; configured/unconfigured actual notification execution unproved. |
| AUD-392 | P | Nonlocal HIBP requirement repaired; original merged weak-password-default criterion remains. |
| AUD-393 | P | Specific DDL/module cleanup improved; complete historical behavior/proof remains incomplete. |
| AUD-399 | C | Original dead Vite test/unloaded setup removed; 4 current canonicalTestConfig PASS bind actual config import, configured setup presence and old setup absence. |
| AUD-400 | C | Original dead/wrong-path runtimeCaching removed; 4 current canonicalTestConfig PASS and actual injectManifest/SW consumers confirm the bounded criterion. |
| AUD-414 | P | Scrypt floor raised; PBKDF2 permits one iteration. Approved RFC-vector scope unchanged. |
| AUD-416 | P | Fresh 9 fail-closed harness controls pass; actual selected fuzz campaign unproved. |
| AUD-420 | N | Private rescue inventory/location unverified; no private access authorized by this review. |
| AUD-422 | P | Additional settings documented; original timeout/poll/retention documentation remains incomplete. |
| AUD-423 | P | Baseline count and selected settings aligned; full cross-document consistency unproved. |
| AUD-426 | P | PostgreSQL work does not prove same-challenge HTTP step-up concurrency; old Lock shim remains. |
| AUD-428 | P | Individual tests improved; complete cross-language assertion census incomplete. |
| AUD-429 | P | Realtime environment selection and manual-only visual execution remain. |
| AUD-432 | P | Owned-core selected specs do not prove broader lockout/full-SSR/registration contracts. |
| AUD-433 | U | Fixture-created notification partitions do not repair historical migrations. |
| AUD-434 | P | Topics model/default inventory improved; compare_server_default remains absent. |
| AUD-436 | S | System32 whoami resolution repaired; native Windows execution unproved. |
| AUD-438 | P | Private metrics listener/lifecycle tests pass with 100% reported statement coverage; deployment isolation unproved. |
| AUD-447 | P | DLQ privacy tombstones improved; stale-overwrite races, historical errors and forged/escaped markers remain. |
| AUD-449 | S | Caddy filters repaired; actual production Caddy/Gunicorn emitted-log negatives unproved. |
| AUD-450 | S | Ordinary GUC bypass removed; applicable current ordinary-role negatives not established here. |
| AUD-454 | P | Fresh-DB fail-closed broadcast repair retained; borrowed-session/in-flight/live boundary remains. |
| AUD-455 | P | Cache-hit upload suppression avoids duplicates but cache-before-publication leaves failed-upload retries artifactless. |
| AUD-456 | U | LHCI MODE=test oracle remains nondiscriminating. |
| AUD-474 | S | Cookie observation reordered before cleanup; actual sequence/negative-reorder proof unestablished. |
| AUD-477 | C | Fresh named race tests prove pre-ACK oversize/marshal checks, deliverable ACK and in-flight join fence. |
| AUD-478 | P | Bounded revocation replay added; startup/shared-L2 admission barrier and retention>7 days remain. |
| AUD-480 | P | Dev dependency scan added; medium/low and ignore-unfixed/node_modules scope gaps remain. |
| AUD-482 | P | Caddy graph locked and built/scanned; govulncheck coverage and actual v3 advisory remain. |
| AUD-483 | P | Recursive read-only PR OSV inventory added; full applicable OSV/stdlib result validation unestablished. |
| AUD-484 | N | Current alert-specific remote security state not inspected; scan success is insufficient. |
| AUD-489 | C | Dead signer/mirror files absent; 57 named production audit-service PASS, including 29 signer/key/status controls and independent fixed-wire tamper checks. |
| AUD-490 | S | Mandatory nonlocal idempotency secret retained; seven cases have only conditional cohort-pass inference because actual collection-union verification was skipped. |
| AUD-501 | S | Hidden-tab assertion/negative handler repaired; real hidden-clock/RAF execution unproved. |
| AUD-503 | P | ICS ownership corrected; WebSocket ownership still disagrees with actual consumers. |
| AUD-506 | P | Temporal HTTPS/default authorizer repaired; service-token producer still lacks required permissions. |

## Complete changed-path review manifest

Each link resolves the reviewed file at the immutable head. M = modified; A = added. The full Git tree/compare reconciliation establishes that this list is complete.

| Path | Change | Review partition |
|---|---|---|
| [`.github/workflows/auto-merge-patches.yml`](https://github.com/egorribun/university_ecosystem/blob/112efb38055caa8ce46717e3d6c23333bc07be4d/.github/workflows/auto-merge-patches.yml) | M | main |
| [`.github/workflows/chromatic.yml`](https://github.com/egorribun/university_ecosystem/blob/112efb38055caa8ce46717e3d6c23333bc07be4d/.github/workflows/chromatic.yml) | M | main |
| [`.github/workflows/contract-validation.yml`](https://github.com/egorribun/university_ecosystem/blob/112efb38055caa8ce46717e3d6c23333bc07be4d/.github/workflows/contract-validation.yml) | M | main |
| [`.github/workflows/dast.yml`](https://github.com/egorribun/university_ecosystem/blob/112efb38055caa8ce46717e3d6c23333bc07be4d/.github/workflows/dast.yml) | M | main |
| [`.github/workflows/deploy.yml`](https://github.com/egorribun/university_ecosystem/blob/112efb38055caa8ce46717e3d6c23333bc07be4d/.github/workflows/deploy.yml) | M | main |
| [`.github/workflows/go-lint.yml`](https://github.com/egorribun/university_ecosystem/blob/112efb38055caa8ce46717e3d6c23333bc07be4d/.github/workflows/go-lint.yml) | M | main |
| [`.github/workflows/lhci-linux.yml`](https://github.com/egorribun/university_ecosystem/blob/112efb38055caa8ce46717e3d6c23333bc07be4d/.github/workflows/lhci-linux.yml) | M | main |
| [`.github/workflows/nightly-full-gate.yml`](https://github.com/egorribun/university_ecosystem/blob/112efb38055caa8ce46717e3d6c23333bc07be4d/.github/workflows/nightly-full-gate.yml) | M | main |
| [`.github/workflows/quality-promotion-check.yml`](https://github.com/egorribun/university_ecosystem/blob/112efb38055caa8ce46717e3d6c23333bc07be4d/.github/workflows/quality-promotion-check.yml) | M | main |
| [`.github/workflows/reusable-full-backend-mutation.yml`](https://github.com/egorribun/university_ecosystem/blob/112efb38055caa8ce46717e3d6c23333bc07be4d/.github/workflows/reusable-full-backend-mutation.yml) | M | main |
| [`.github/workflows/reusable-helm-dependencies.yml`](https://github.com/egorribun/university_ecosystem/blob/112efb38055caa8ce46717e3d6c23333bc07be4d/.github/workflows/reusable-helm-dependencies.yml) | M | main |
| [`.github/workflows/sbom.yml`](https://github.com/egorribun/university_ecosystem/blob/112efb38055caa8ce46717e3d6c23333bc07be4d/.github/workflows/sbom.yml) | M | main |
| [`.github/workflows/scorecard.yml`](https://github.com/egorribun/university_ecosystem/blob/112efb38055caa8ce46717e3d6c23333bc07be4d/.github/workflows/scorecard.yml) | M | main |
| [`.github/workflows/sonar.yml`](https://github.com/egorribun/university_ecosystem/blob/112efb38055caa8ce46717e3d6c23333bc07be4d/.github/workflows/sonar.yml) | M | main |
| [`.github/workflows/sqlmap.yml`](https://github.com/egorribun/university_ecosystem/blob/112efb38055caa8ce46717e3d6c23333bc07be4d/.github/workflows/sqlmap.yml) | M | main |
| [`.github/workflows/trufflehog.yml`](https://github.com/egorribun/university_ecosystem/blob/112efb38055caa8ce46717e3d6c23333bc07be4d/.github/workflows/trufflehog.yml) | M | main |
| [`.secrets.baseline`](https://github.com/egorribun/university_ecosystem/blob/112efb38055caa8ce46717e3d6c23333bc07be4d/.secrets.baseline) | M | main |
| [`AGENTS.md`](https://github.com/egorribun/university_ecosystem/blob/112efb38055caa8ce46717e3d6c23333bc07be4d/AGENTS.md) | M | main |
| [`alembic/versions/202607230001_multi_tenant_rls.py`](https://github.com/egorribun/university_ecosystem/blob/112efb38055caa8ce46717e3d6c23333bc07be4d/alembic/versions/202607230001_multi_tenant_rls.py) | M | backend |
| [`app/core/config/__init__.py`](https://github.com/egorribun/university_ecosystem/blob/112efb38055caa8ce46717e3d6c23333bc07be4d/app/core/config/__init__.py) | M | backend |
| [`app/core/nats_broker.py`](https://github.com/egorribun/university_ecosystem/blob/112efb38055caa8ce46717e3d6c23333bc07be4d/app/core/nats_broker.py) | M | realtime |
| [`app/services/ws_hub_client.py`](https://github.com/egorribun/university_ecosystem/blob/112efb38055caa8ce46717e3d6c23333bc07be4d/app/services/ws_hub_client.py) | M | realtime |
| [`charts/university-ecosystem/templates/backend-deployment.yaml`](https://github.com/egorribun/university_ecosystem/blob/112efb38055caa8ce46717e3d6c23333bc07be4d/charts/university-ecosystem/templates/backend-deployment.yaml) | M | infra |
| [`charts/university-ecosystem/templates/validate-config.yaml`](https://github.com/egorribun/university_ecosystem/blob/112efb38055caa8ce46717e3d6c23333bc07be4d/charts/university-ecosystem/templates/validate-config.yaml) | M | infra |
| [`charts/university-ecosystem/templates/ws-hub-deployment.yaml`](https://github.com/egorribun/university_ecosystem/blob/112efb38055caa8ce46717e3d6c23333bc07be4d/charts/university-ecosystem/templates/ws-hub-deployment.yaml) | M | infra |
| [`charts/university-ecosystem/values.schema.json`](https://github.com/egorribun/university_ecosystem/blob/112efb38055caa8ce46717e3d6c23333bc07be4d/charts/university-ecosystem/values.schema.json) | M | infra |
| [`charts/university-ecosystem/values.yaml`](https://github.com/egorribun/university_ecosystem/blob/112efb38055caa8ce46717e3d6c23333bc07be4d/charts/university-ecosystem/values.yaml) | M | infra |
| [`CONFIGURATION.md`](https://github.com/egorribun/university_ecosystem/blob/112efb38055caa8ce46717e3d6c23333bc07be4d/CONFIGURATION.md) | M | infra |
| [`docker-compose.live.yml`](https://github.com/egorribun/university_ecosystem/blob/112efb38055caa8ce46717e3d6c23333bc07be4d/docker-compose.live.yml) | M | infra |
| [`docs/adr/ADR-036-sqlalchemy-dual-default-migration-policy.md`](https://github.com/egorribun/university_ecosystem/blob/112efb38055caa8ce46717e3d6c23333bc07be4d/docs/adr/ADR-036-sqlalchemy-dual-default-migration-policy.md) | M | main |
| [`frontend/src/api/__tests__/offlineMutationQueue.closure.test.ts`](https://github.com/egorribun/university_ecosystem/blob/112efb38055caa8ce46717e3d6c23333bc07be4d/frontend/src/api/__tests__/offlineMutationQueue.closure.test.ts) | M | frontend |
| [`frontend/src/api/offlineMutationQueue.ts`](https://github.com/egorribun/university_ecosystem/blob/112efb38055caa8ce46717e3d6c23333bc07be4d/frontend/src/api/offlineMutationQueue.ts) | M | frontend |
| [`frontend/src/hooks/__tests__/messengerProjection.clear-reconciliation.test.ts`](https://github.com/egorribun/university_ecosystem/blob/112efb38055caa8ce46717e3d6c23333bc07be4d/frontend/src/hooks/__tests__/messengerProjection.clear-reconciliation.test.ts) | M | frontend |
| [`frontend/src/hooks/messengerProjection.ts`](https://github.com/egorribun/university_ecosystem/blob/112efb38055caa8ce46717e3d6c23333bc07be4d/frontend/src/hooks/messengerProjection.ts) | M | frontend |
| [`frontend/src/push/__tests__/registerSw.test.ts`](https://github.com/egorribun/university_ecosystem/blob/112efb38055caa8ce46717e3d6c23333bc07be4d/frontend/src/push/__tests__/registerSw.test.ts) | M | frontend |
| [`frontend/src/push/register-sw.ts`](https://github.com/egorribun/university_ecosystem/blob/112efb38055caa8ce46717e3d6c23333bc07be4d/frontend/src/push/register-sw.ts) | M | frontend |
| [`frontend/src/sw/__tests__/audit375.legacy-safety.test.ts`](https://github.com/egorribun/university_ecosystem/blob/112efb38055caa8ce46717e3d6c23333bc07be4d/frontend/src/sw/__tests__/audit375.legacy-safety.test.ts) | M | frontend |
| [`frontend/src/sw/__tests__/audit375.lifecycle-hold.test.ts`](https://github.com/egorribun/university_ecosystem/blob/112efb38055caa8ce46717e3d6c23333bc07be4d/frontend/src/sw/__tests__/audit375.lifecycle-hold.test.ts) | M | frontend |
| [`frontend/src/sw/__tests__/audit375.queue-serialization.test.ts`](https://github.com/egorribun/university_ecosystem/blob/112efb38055caa8ce46717e3d6c23333bc07be4d/frontend/src/sw/__tests__/audit375.queue-serialization.test.ts) | M | frontend |
| [`frontend/src/sw/__tests__/audit375.replay.test.ts`](https://github.com/egorribun/university_ecosystem/blob/112efb38055caa8ce46717e3d6c23333bc07be4d/frontend/src/sw/__tests__/audit375.replay.test.ts) | A | frontend |
| [`frontend/src/sw/__tests__/offline.test.ts`](https://github.com/egorribun/university_ecosystem/blob/112efb38055caa8ce46717e3d6c23333bc07be4d/frontend/src/sw/__tests__/offline.test.ts) | M | frontend |
| [`frontend/src/sw/__tests__/push-navigation-queue.test.ts`](https://github.com/egorribun/university_ecosystem/blob/112efb38055caa8ce46717e3d6c23333bc07be4d/frontend/src/sw/__tests__/push-navigation-queue.test.ts) | M | frontend |
| [`frontend/src/sw/__tests__/push.test.ts`](https://github.com/egorribun/university_ecosystem/blob/112efb38055caa8ce46717e3d6c23333bc07be4d/frontend/src/sw/__tests__/push.test.ts) | M | frontend |
| [`frontend/src/sw/__tests__/replayCredentialResponder.test.ts`](https://github.com/egorribun/university_ecosystem/blob/112efb38055caa8ce46717e3d6c23333bc07be4d/frontend/src/sw/__tests__/replayCredentialResponder.test.ts) | A | frontend |
| [`frontend/src/sw/__tests__/replayCredentials.test.ts`](https://github.com/egorribun/university_ecosystem/blob/112efb38055caa8ce46717e3d6c23333bc07be4d/frontend/src/sw/__tests__/replayCredentials.test.ts) | A | frontend |
| [`frontend/src/sw/__tests__/replayPolicy.test.ts`](https://github.com/egorribun/university_ecosystem/blob/112efb38055caa8ce46717e3d6c23333bc07be4d/frontend/src/sw/__tests__/replayPolicy.test.ts) | A | frontend |
| [`frontend/src/sw/offline.ts`](https://github.com/egorribun/university_ecosystem/blob/112efb38055caa8ce46717e3d6c23333bc07be4d/frontend/src/sw/offline.ts) | M | frontend |
| [`frontend/src/sw/push.ts`](https://github.com/egorribun/university_ecosystem/blob/112efb38055caa8ce46717e3d6c23333bc07be4d/frontend/src/sw/push.ts) | M | frontend |
| [`frontend/src/sw/replayCredentialResponder.ts`](https://github.com/egorribun/university_ecosystem/blob/112efb38055caa8ce46717e3d6c23333bc07be4d/frontend/src/sw/replayCredentialResponder.ts) | A | frontend |
| [`frontend/src/sw/replayCredentials.ts`](https://github.com/egorribun/university_ecosystem/blob/112efb38055caa8ce46717e3d6c23333bc07be4d/frontend/src/sw/replayCredentials.ts) | A | frontend |
| [`frontend/src/sw/replayPolicy.ts`](https://github.com/egorribun/university_ecosystem/blob/112efb38055caa8ce46717e3d6c23333bc07be4d/frontend/src/sw/replayPolicy.ts) | A | frontend |
| [`frontend/src/tests/sw.test.ts`](https://github.com/egorribun/university_ecosystem/blob/112efb38055caa8ce46717e3d6c23333bc07be4d/frontend/src/tests/sw.test.ts) | M | frontend |
| [`quality/model-default-policy.json`](https://github.com/egorribun/university_ecosystem/blob/112efb38055caa8ce46717e3d6c23333bc07be4d/quality/model-default-policy.json) | M | main |
| [`services/caddy/Dockerfile`](https://github.com/egorribun/university_ecosystem/blob/112efb38055caa8ce46717e3d6c23333bc07be4d/services/caddy/Dockerfile) | M | infra |
| [`services/caddy/go.mod`](https://github.com/egorribun/university_ecosystem/blob/112efb38055caa8ce46717e3d6c23333bc07be4d/services/caddy/go.mod) | A | infra |
| [`services/caddy/go.sum`](https://github.com/egorribun/university_ecosystem/blob/112efb38055caa8ce46717e3d6c23333bc07be4d/services/caddy/go.sum) | A | infra |
| [`services/caddy/main.go`](https://github.com/egorribun/university_ecosystem/blob/112efb38055caa8ce46717e3d6c23333bc07be4d/services/caddy/main.go) | A | infra |
| [`services/ws-hub/main_test.go`](https://github.com/egorribun/university_ecosystem/blob/112efb38055caa8ce46717e3d6c23333bc07be4d/services/ws-hub/main_test.go) | M | realtime |
| [`services/ws-hub/pkg/config/config_test.go`](https://github.com/egorribun/university_ecosystem/blob/112efb38055caa8ce46717e3d6c23333bc07be4d/services/ws-hub/pkg/config/config_test.go) | M | realtime |
| [`services/ws-hub/pkg/config/config.go`](https://github.com/egorribun/university_ecosystem/blob/112efb38055caa8ce46717e3d6c23333bc07be4d/services/ws-hub/pkg/config/config.go) | M | realtime |
| [`services/ws-hub/pkg/hub/aud320_python_contract_test.go`](https://github.com/egorribun/university_ecosystem/blob/112efb38055caa8ce46717e3d6c23333bc07be4d/services/ws-hub/pkg/hub/aud320_python_contract_test.go) | M | realtime |
| [`services/ws-hub/pkg/hub/aud478_cache_invalidation_consumer_test.go`](https://github.com/egorribun/university_ecosystem/blob/112efb38055caa8ce46717e3d6c23333bc07be4d/services/ws-hub/pkg/hub/aud478_cache_invalidation_consumer_test.go) | M | realtime |
| [`services/ws-hub/pkg/hub/aud511_512_revocation_marker_test.go`](https://github.com/egorribun/university_ecosystem/blob/112efb38055caa8ce46717e3d6c23333bc07be4d/services/ws-hub/pkg/hub/aud511_512_revocation_marker_test.go) | M | realtime |
| [`services/ws-hub/pkg/hub/aud512_panic_delivery_test.go`](https://github.com/egorribun/university_ecosystem/blob/112efb38055caa8ce46717e3d6c23333bc07be4d/services/ws-hub/pkg/hub/aud512_panic_delivery_test.go) | M | realtime |
| [`services/ws-hub/pkg/hub/hub_integration_test.go`](https://github.com/egorribun/university_ecosystem/blob/112efb38055caa8ce46717e3d6c23333bc07be4d/services/ws-hub/pkg/hub/hub_integration_test.go) | M | realtime |
| [`services/ws-hub/pkg/hub/hub_jetstream_integration_test.go`](https://github.com/egorribun/university_ecosystem/blob/112efb38055caa8ce46717e3d6c23333bc07be4d/services/ws-hub/pkg/hub/hub_jetstream_integration_test.go) | M | realtime |
| [`services/ws-hub/pkg/hub/hub_nats_test.go`](https://github.com/egorribun/university_ecosystem/blob/112efb38055caa8ce46717e3d6c23333bc07be4d/services/ws-hub/pkg/hub/hub_nats_test.go) | M | realtime |
| [`services/ws-hub/pkg/hub/hub.go`](https://github.com/egorribun/university_ecosystem/blob/112efb38055caa8ce46717e3d6c23333bc07be4d/services/ws-hub/pkg/hub/hub.go) | M | realtime |
| [`services/ws-hub/pkg/hub/replay_security_adversarial_test.go`](https://github.com/egorribun/university_ecosystem/blob/112efb38055caa8ce46717e3d6c23333bc07be4d/services/ws-hub/pkg/hub/replay_security_adversarial_test.go) | M | realtime |
| [`tests/contracts/test_ws_hub_contract.py`](https://github.com/egorribun/university_ecosystem/blob/112efb38055caa8ce46717e3d6c23333bc07be4d/tests/contracts/test_ws_hub_contract.py) | M | realtime |
| [`tests/integration/test_aud197_198_notification_outbox_postgres.py`](https://github.com/egorribun/university_ecosystem/blob/112efb38055caa8ce46717e3d6c23333bc07be4d/tests/integration/test_aud197_198_notification_outbox_postgres.py) | M | backend |
| [`tests/integration/test_aud350_stored_event_timestamp_migration.py`](https://github.com/egorribun/university_ecosystem/blob/112efb38055caa8ce46717e3d6c23333bc07be4d/tests/integration/test_aud350_stored_event_timestamp_migration.py) | M | backend |
| [`tests/integration/test_nats_jetstream.py`](https://github.com/egorribun/university_ecosystem/blob/112efb38055caa8ce46717e3d6c23333bc07be4d/tests/integration/test_nats_jetstream.py) | M | realtime |
| [`tests/test_alembic_graph_metadata.py`](https://github.com/egorribun/university_ecosystem/blob/112efb38055caa8ce46717e3d6c23333bc07be4d/tests/test_alembic_graph_metadata.py) | M | backend |
| [`tests/test_aud164_trusted_proxy_production_guard.py`](https://github.com/egorribun/university_ecosystem/blob/112efb38055caa8ce46717e3d6c23333bc07be4d/tests/test_aud164_trusted_proxy_production_guard.py) | M | backend |
| [`tests/test_aud277_360_450_tenant_rls_contract.py`](https://github.com/egorribun/university_ecosystem/blob/112efb38055caa8ce46717e3d6c23333bc07be4d/tests/test_aud277_360_450_tenant_rls_contract.py) | M | backend |
| [`tests/test_aud350_reconcile_migration_coverage.py`](https://github.com/egorribun/university_ecosystem/blob/112efb38055caa8ce46717e3d6c23333bc07be4d/tests/test_aud350_reconcile_migration_coverage.py) | M | backend |
| [`tests/test_aud482_go_binary_inventory.py`](https://github.com/egorribun/university_ecosystem/blob/112efb38055caa8ce46717e3d6c23333bc07be4d/tests/test_aud482_go_binary_inventory.py) | M | infra |
| [`tests/test_aud490_idempotency_secret_required.py`](https://github.com/egorribun/university_ecosystem/blob/112efb38055caa8ce46717e3d6c23333bc07be4d/tests/test_aud490_idempotency_secret_required.py) | M | backend |
| [`tests/test_be02_semantic_defaults_migration.py`](https://github.com/egorribun/university_ecosystem/blob/112efb38055caa8ce46717e3d6c23333bc07be4d/tests/test_be02_semantic_defaults_migration.py) | M | backend |
| [`tests/test_caddy_security_dependency_pins.py`](https://github.com/egorribun/university_ecosystem/blob/112efb38055caa8ce46717e3d6c23333bc07be4d/tests/test_caddy_security_dependency_pins.py) | M | infra |
| [`tests/test_config_init_extra.py`](https://github.com/egorribun/university_ecosystem/blob/112efb38055caa8ce46717e3d6c23333bc07be4d/tests/test_config_init_extra.py) | M | backend |
| [`tests/test_core_config.py`](https://github.com/egorribun/university_ecosystem/blob/112efb38055caa8ce46717e3d6c23333bc07be4d/tests/test_core_config.py) | M | backend |
| [`tests/test_cwv_rum_security.py`](https://github.com/egorribun/university_ecosystem/blob/112efb38055caa8ce46717e3d6c23333bc07be4d/tests/test_cwv_rum_security.py) | M | backend |
| [`tests/test_docker_startup_contracts.py`](https://github.com/egorribun/university_ecosystem/blob/112efb38055caa8ce46717e3d6c23333bc07be4d/tests/test_docker_startup_contracts.py) | M | infra |
| [`tests/test_encryption.py`](https://github.com/egorribun/university_ecosystem/blob/112efb38055caa8ce46717e3d6c23333bc07be4d/tests/test_encryption.py) | M | backend |
| [`tests/test_helm_aud168_169_followup.py`](https://github.com/egorribun/university_ecosystem/blob/112efb38055caa8ce46717e3d6c23333bc07be4d/tests/test_helm_aud168_169_followup.py) | M | infra |
| [`tests/test_helm_staging_contract.py`](https://github.com/egorribun/university_ecosystem/blob/112efb38055caa8ce46717e3d6c23333bc07be4d/tests/test_helm_staging_contract.py) | M | infra |
| [`tests/test_live_stand.py`](https://github.com/egorribun/university_ecosystem/blob/112efb38055caa8ce46717e3d6c23333bc07be4d/tests/test_live_stand.py) | M | infra |
| [`tests/test_migration_downgrade_policy.py`](https://github.com/egorribun/university_ecosystem/blob/112efb38055caa8ce46717e3d6c23333bc07be4d/tests/test_migration_downgrade_policy.py) | M | backend |
| [`tests/test_nats_broker_closure.py`](https://github.com/egorribun/university_ecosystem/blob/112efb38055caa8ce46717e3d6c23333bc07be4d/tests/test_nats_broker_closure.py) | M | realtime |
| [`tests/test_nats_files_process_stream.py`](https://github.com/egorribun/university_ecosystem/blob/112efb38055caa8ce46717e3d6c23333bc07be4d/tests/test_nats_files_process_stream.py) | M | realtime |
| [`tests/test_non_auth_quality_closure.py`](https://github.com/egorribun/university_ecosystem/blob/112efb38055caa8ce46717e3d6c23333bc07be4d/tests/test_non_auth_quality_closure.py) | M | backend |
| [`tests/test_quality_workflow_contract.py`](https://github.com/egorribun/university_ecosystem/blob/112efb38055caa8ce46717e3d6c23333bc07be4d/tests/test_quality_workflow_contract.py) | M | main |
| [`tests/test_stryker_progress_workflow_contract.py`](https://github.com/egorribun/university_ecosystem/blob/112efb38055caa8ce46717e3d6c23333bc07be4d/tests/test_stryker_progress_workflow_contract.py) | M | main |
| [`tests/test_workflow_gate_hardening_contract.py`](https://github.com/egorribun/university_ecosystem/blob/112efb38055caa8ce46717e3d6c23333bc07be4d/tests/test_workflow_gate_hardening_contract.py) | A | main |
| [`tests/test_ws_hub_client.py`](https://github.com/egorribun/university_ecosystem/blob/112efb38055caa8ce46717e3d6c23333bc07be4d/tests/test_ws_hub_client.py) | M | realtime |
| [`zizmor.yml`](https://github.com/egorribun/university_ecosystem/blob/112efb38055caa8ce46717e3d6c23333bc07be4d/zizmor.yml) | M | main |
