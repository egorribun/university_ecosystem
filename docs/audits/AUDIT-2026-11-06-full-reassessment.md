# Full audit reassessment — 2026-11-07 UTC

## Current scoped supplement — 2026-11-07

The current formal total is **484/512 (94.5%) accepted or resolved, 28 open**:
**16S / 12P / 0U / 0N**. The six additional scoped decisions are AUD-208,
AUD-334, AUD-416, AUD-420, AUD-478 and AUD-480. The prior **478/34** and
**476/36** checkpoints and their earlier current-status wording remain below
as dated history; this supplement supersedes their totals.

[Decision scopes and evidence limits](AUDIT-2026-11-06-full-reassessment.md#current-scoped-supplement--2026-11-07).
The reviewed supplemental evidence is bound to its individual source pins,
including earlier 20d4/13693/ea381 evidence snapshots. The supplemental v4
packet was captured at index tree 8ba3ea986595; the first 484 documentation
draft was prepared after staged-tree capture 6dd3cc904fff. That draft tree is
historical, not a current-index or coverage assertion; the working index has
since advanced, and no checks are claimed for the later index or these doc
updates. At draft capture, local HEAD was 9c566fa906a6 and the observed
remote-tracking ref was 067b922f10cb; local and remote were not synchronized. A later 2026-11-07 UTC observation recorded normal merge commit fbddf32f04f0 and tree 74c0c0c38f94, pushed at 04:43:56 UTC with local and remote refs matching then; applicable hooks, full SAST, and pre-push typecheck passed. A final-source guard run on that tree reported 1,180 PASS and 5 FAIL across 1,185 nodes, with no errors, skips, or warnings; the five failures remain tied to the known whole-file guard-pin approval issue. The later terminal snapshot on the same source recorded 98 successful, 23 failed, and 25 skipped checks. Full CI GREEN, all required checks passing, and release readiness are not established.
Inventory remains **497 dispositions / 242 baseline identities / 27 Gitleaks
fingerprints / 15 Semgrep rows**, not a passing scan. All 78 required context/app
pairs, blocking CodeQL, hooks and quality floors remain in force.

### Six additional scoped decisions

These decisions extend the dated 478/34 public checkpoint. The original
Russian audit wording and the normalized English descriptions in the frozen
matrix are separate sources; the English AUD-420 wording below is not a
verbatim quotation. The matrix keeps its 478/34 class and primary-report fields
as historical inputs, labels the six former Open statuses as accepted in this
484 overlay, and preserves their old remaining-action text as historical.

| ID | Current scoped decision and evidence boundary |
| --- | --- |
| AUD-208 | The finding-specific SQL rendering/DDL criterion is accepted from 13/13 owned PostgreSQL tests, three native Squawk inputs with zero issues, and offline positive/negative controls. The five explicit baseline exclusions are the complete exclusion set: no guard or SELECT path was excluded, and the global exclusion list was empty. The recorded phase still failed its immediate and 15-second loopback-release checks; later exact container/volume absence and port release were verified after 249.059 seconds. No hosted result, actual cron execution, or timely-cleanup success is claimed. |
| AUD-334 | The named real-JetStream case proves rate-limited reconnect rejection followed by missed-sequence delivery after retry, with signed resume-cursor and replay-enabled-flag assertions. The enclosing attempt retained a separate AUD-478 observer failure. The replay-disabled branch was not dynamically exercised, and a complete current-tree build is not claimed. |
| AUD-416 | Static source pins verify caller, workflow-step, and catalog wiring; the real-WASM campaign completed two iterations and 31 calls. Zero-iteration, missing-WASM, and corrupt-WASM controls failed closed. The configured hosted 100,000-iteration result remains unproved. |
| AUD-420 | The literal dated Russian criterion says the rescue bundle and archive inventory were absent. The frozen matrix uses a normalized English description, not a literal translation claim. The owner-authorized one-time replacement bundle and 120-row metadata CSV were independently checked for restrictive access and absence of reparse traversal. This does not restore the missing historical files, hashes, transfer fields, or cause, and grants no general backup or distribution authorization. |
| AUD-478 | The named real-JetStream ConsumerInfo checks cover both subscriptions and 60-second and 1-second test windows: cache.invalidate uses DeliverNew; cache.revoke uses DeliverByStartTime; AckWait is 60 seconds, MaxDeliver is 20, and InactiveThreshold is 300 seconds. Exact owned resources were absent after cleanup. Two nonfatal stream-not-found cleanup diagnostics remain preserved with origin unproved. No seven-day backlog fixture, whole-index build, warning-free run, or hosted result is claimed. |
| AUD-480 | The supplement records five passed local npm CLI cases using a loopback synthetic registry; no separate raw local pytest receipt was located. The cited frontend PR gate covers npm info visibility and production, development, optional, and peer dependencies. Its named hosted steps Verify npm audit scope with a local registry and Block moderate and low npm advisories passed. The repository-root Trivy filesystem gate scans HIGH/CRITICAL with unfixed findings enabled, fails on findings, and reasserts the captured result; the named hosted steps Run Trivy vulnerability scanner (filesystem) and Re-assert Trivy filesystem and configuration gates passed. The earlier Round 5 negative-control note names an unfixed HIGH finding and exact disposition but contains no Trivy binary hash, database digest, or current-source raw receipt. No fresh full-tree scan, live advisory inventory, global scan clearance, or root release-tooling medium/low coverage is claimed. |

The immutable private supplemental-six v4 manifest, its metadata-correction
addendum, six adjudications and independent reviews bind the detailed receipts.
Two stale packet labels are explicitly corrected by that addendum without
rewriting the preserved evidence. AUD-420's frozen primary-report hash differs
from the later preserved report and is disclosed rather than reconstructed.

---

<a id="decision-summary"></a>
<a id="previous-public-checkpoint--2026-11-07"></a>

## Dated 478/34 public checkpoint — 2026-11-07 (superseded)

This review preserves the prior 452 accepted IDs and adds 25 criterion-specific scoped acceptances plus the AUD-384 false-positive retraction: **478 / 512 (93.4%) accepted or resolved, with 34 open**. AUD-384 corrects the original causal finding; it does not accept live notification delivery. The 2026-11-06 23:59 UTC checkpoint at 476 / 512 and 36 open is preserved below as dated history.

The 60-row input complement preserves the primary reports and their November 6 classes; those reports and most associated evidence bind to audit tree `20d4a080aeb0`. The current reviewed index snapshot is tree `ea381c19bda1`, with local checkout HEAD `8a4367b3599a`. No local/remote synchronization or overall gate result is claimed. The current inventory contains **497** security dispositions, baseline **242**, Gitleaks **27**, and Semgrep **15**. These are inventory counts, not scan results. The previous 476/36 documentation checkpoint was based on index tree `13693bbf3d16`; this report records the subsequent AUD-422/AUD-423 adjudications and AUD-346 class change.

The scoped receipts do not establish full CI GREEN, release readiness, all 78 required context/app pairs, or hosted validation for the new documentation postimages. The 497-record security inventory is not a passing scan.

## Previous cohort checkpoint — 2026-11-06 23:59 UTC

The earlier source-bound documentation checkpoint recorded **476 / 512 (93.0%) accepted or resolved, 36 open**, with classes **19S / 15P / 1U / 1N**. Its current class lists were:

- **S (19):** AUD-154, AUD-164, AUD-169, AUD-178, AUD-188, AUD-208, AUD-226, AUD-272, AUD-321, AUD-334, AUD-347, AUD-375, AUD-378, AUD-416, AUD-429, AUD-438, AUD-454, AUD-478, AUD-501.
- **P (15):** AUD-167, AUD-189, AUD-251, AUD-313, AUD-322, AUD-360, AUD-373, AUD-381, AUD-422, AUD-423, AUD-428, AUD-432, AUD-480, AUD-483, AUD-484.
- **U (1):** AUD-346.
- **N (1):** AUD-420.

That dated checkpoint described AUD-422 and AUD-423 as open (P), and AUD-346 as open (U). The current update accepts AUD-422 only for its configuration-documentation and inventory-contract criterion, accepts AUD-423 for the updated documentation/source-alignment surfaces, and moves AUD-346 from U to S because the source correction is integrated while live Kind proof remains pending. The previous classification is retained here and in the private matrix; primary-report implementation/proof fields are not rewritten.

<a id="current-34-finding-complement"></a>

## Dated 34-finding complement — previous 478/34 checkpoint

The classes at the dated 478/34 checkpoint were **20S / 13P / 0U / 1N = 34**. S means source fixed with criterion proof still pending; P partial; U unfixed; N unproven. This is the explicit current-tree assessment, not a mechanical mapping from implementation fields or the dated primary-report classes.

At this 478/34 checkpoint, AUD-422 and AUD-423 had left the open set by scoped acceptance and AUD-346 had moved U→S; live Kind injection/degradation/recovery proof remained unrun. AUD-208 was still open before its later PostgreSQL/Squawk supplement. AUD-484 remained P on partial alert inventory evidence; exact-snapshot Trivy analysis and a fresh Dependabot comparison remained open.

The 478/34 checkpoint's indexed source pins included the AUD-208 renderer/test and AUD-378 verifier/tests carried forward from the prior review; their criterion proof was pending at that time. Its AUD-346 workflow/test and AUD-423 documentation/source-alignment pointers were pinned to tree `ea381c19bda1` in the private matrix. The exact source and receipt hashes remain in the private package manifest.

- **S (20):** AUD-154, AUD-164, AUD-169, AUD-178, AUD-188, AUD-208, AUD-226, AUD-272, AUD-321, AUD-334, AUD-346, AUD-347, AUD-375, AUD-378, AUD-416, AUD-429, AUD-438, AUD-454, AUD-478, AUD-501.
- **P (13):** AUD-167, AUD-189, AUD-251, AUD-313, AUD-322, AUD-360, AUD-373, AUD-381, AUD-428, AUD-432, AUD-480, AUD-483, AUD-484.
- **U (0):** none.
- **N (1):** AUD-420.

That dated checkpoint accepted AUD-422 for its configuration-documentation/inventory-contract criterion and AUD-423 for source alignment across updated documentation surfaces; AUD-346 moved U→S after its source correction was integrated. AUD-346 remained open until live Kind proof demonstrates injection, measured degradation, cleanup and recovery. AUD-208's PostgreSQL/Squawk proof was unproven at that checkpoint and is addressed only within the current supplement above; AUD-484 remained open. AUD-269 and AUD-474 retain only the narrow scopes described below. The expanded HNSW/index catalog flags and full live-stand behavior are not accepted; private proposals are not counted as applied changes.

## Complete 60-row reassessment matrix (478/34 baseline with 484 overlay)

The Nov 6 class and primary-proof columns preserve the dated baseline. Current outcome reflects the 484/512 overlay. For AUD-208, AUD-334, AUD-416, AUD-420, AUD-478 and AUD-480, the prior Open status is labelled as such and the original remaining-action text is retained only as the historical 478/34 action. Historical migration paths are not asserted as current files.

| ID | Original criterion | Nov 6 class | Primary implementation / proof | Current outcome | Current source pointer | Remaining action |
| --- | --- | --- | --- | --- | --- | --- |
| AUD-073 | White text on sent messages has insufficient contrast on the light violet gradient. The source contract measures adequate normal-text contrast at WCAG AA 4.5:1. | S | fixed / sufficient | Scoped acceptance; see decision section | `frontend/src/components/messenger/ChatWindow.tsx:746` (snapshot, blob `91c4f11d2b5d`); `frontend/src/styles/tokens/messenger.css:95` (snapshot, blob `2425bc81977c`) | No additional action for this finding-specific scope; limitations below remain. |
| AUD-154 | frontend/tests/e2e/chat-realtime.spec.ts:127-128; frontend/src/components/messenger/ChatWindow.tsx:986-994 — the delivery test waits for a marker the status renderer does not produce. | S | fixed / partial | Open (S) | `frontend/tests/e2e/chat-realtime.spec.ts:125` (snapshot, blob `b568a66b29ac`); `frontend/src/components/messenger/ChatWindow.tsx:1008` (snapshot, blob `91c4f11d2b5d`) | Run the named delivery case with REALTIME_E2E=true against the real backend/WebSocket stack on this source tree, and retain the case-level Playwright result and source/test blob binding; confirm the case was not skipped. |
| AUD-164 | The backend sees the gateway IP, causing anonymous login, registration, MFA, and password-reset requests from different clients to share rate-limit buckets (docs/audits/AUDIT-2026-10.md:191). | P | fixed / partial | Open (S) | `docs/audits/AUDIT-2026-10.md:191` (snapshot, blob `ce20147fdbee`); `app/core/ratelimit/utils.py:172` (snapshot, blob `afef0bb756c3`) | Source-bind an invocation path for the existing no-mount probe, then perform one owner-leased run against actual Docker-inspected Caddy, gateway, and backend peers. Record named per-route results for two distinct clients plus X-Forwarded-For, X-Real-IP, Forwarded, and direct-backend spoof negatives; bind the observation to this source tree and verify before/after topology witnesses and exact probe cleanup. |
| AUD-167 | AUDIT-2026-10.md:194 — “Rate-limit gateway and ws-hub collapses to one proxy IP.” Distinct clients behind the same explicitly trusted proxy must receive distinct IP rate-limit buckets; untrusted forwarded headers must not allow bucket rotation. | P | partial / partial | Open (P) | `docs/audits/AUDIT-2026-10.md:194` (snapshot, blob `ce20147fdbee`); `services/gateway/cmd/gateway/main.go:604` (snapshot, blob `87d471f684ea`) | With owner-selected trusted proxy peer CIDRs and target topology, run a bounded two-client and forged-forwarded-header check through the actual Caddy-to-Gateway and Caddy-to-ws-hub paths; record source/config-bound results. The previous Compose binder must first satisfy its Docker IpcMode precondition. |
| AUD-169 | file-processor fails to start in staging/production because NetworkPolicy blocks its connection to revocation Redis (docs/audits/AUDIT-2026-10.md:196). | P | fixed / missing | Open (S) | `charts/university-ecosystem/templates/network-policy.yaml:709` (snapshot, blob `2c11ef6f7464`); `charts/university-ecosystem/templates/file-processor-deployment.yaml:35` (snapshot, blob `f5b8bdc8aee7`) | When an owner-authorized staging/production-equivalent namespace is available, run the AUD-169 portion of the prepared harness against the actual file-processor and dedicated Redis at this source/image digest. Privately confirm their namespace/release identity and the Secret URL host; record same-release TCP/6379 reachability through Pod IP and Service, startup and authenticated PING, plus cross-release/unrelated-source denial with same-destination controls and attributable CNI verdicts. Keep credentials out of the receipt. |
| AUD-178 | Prevent reset-password bearer tokens in legacy query/path URLs from appearing in access logs via Referer or in CSP reports. | P | fixed / partial | Open (S) | `services/caddy/Caddyfile:24` (snapshot, blob `330c365dcc73`); `frontend/src/server.ts:126` (snapshot, blob `e7992cd94b47`) | Run the current AUD-178 live Playwright spec through the owned Caddy/SSR stand with synthetic query and path tokens before hydration. Require the browser Referer and CSP assertions plus the current correlated Caddy-log verifier to pass, and retain value-free receipts. A local stand result would not attest a production deployment. |
| AUD-188 | The file-processor JWKS endpoint is denied by NetworkPolicy, causing RS256 tokens to be rejected after roughly 24 hours (docs/audits/AUDIT-2026-10.md:276). | P | fixed / partial | Open (S) | `charts/university-ecosystem/templates/file-processor-deployment.yaml:2` (snapshot, blob `f5b8bdc8aee7`); `charts/university-ecosystem/templates/network-policy.yaml:515` (snapshot, blob `2c11ef6f7464`) | In an owner-authorized isolated environment matching each target cluster's CNI and resolved chart values, execute the documented AUD-188 protocol: prove direct Pod IP and Service reachability to the actual JWKS URL with HTTP 200 and no redirect from the file-processor namespace; prove same-release allowance and sibling/unrelated denial with same-destination controls and CNI verdicts; then demonstrate per-replica key B refresh without restart using the authentication boundary. Record endpoint, effective policy, CIDR, and DNAT observations. |
| AUD-189 | The chart NetworkPolicy permits TCP/443 and DNS egress to any destination, including in-cluster services (AUDIT-2026-10.md:277; original source pointer network-policy.yaml:146-148). | P | partial / partial | Open (P) | `docs/audits/AUDIT-2026-10.md:277` (snapshot, blob `ce20147fdbee`); `charts/university-ecosystem/templates/network-policy.yaml:734` (snapshot, blob `2c11ef6f7464`) | For the target deployment and source SHA, bind resolved chart values and all additive NetworkPolicies to actual Pod/Service CIDRs and the CNI, then execute the documented same-destination-controlled probes for TCP/443 to private PodIP, ClusterIP, link-local, and approved public listeners, plus UDP/TCP DNS to the real resolver and a controlled non-resolver; retain correlated CNI verdicts. |
| AUD-208 | The Squawk gate must not pass guard migrations with no lintable SQL and must not be weakened by rule exclusions. | P | partial / partial | Scoped acceptance at 484/512 (was Open at 478/512) | `.github/workflows/ci.yml:1553` (snapshot, blob `f6ecac56cbf6`); `scripts/quality/render_live_alembic_sql.py:234` (snapshot, blob `27febaf0f99c`) | Historical 478/512 remaining action: Run a named PostgreSQL+Squawk guard case bound to this tree that proves DO/SELECT guard SQL is retained or causes a fail-closed result when no lintable DDL is captured; include an empty/no-op negative control and confirm only the exact documented baseline exclusions apply. Current evidence and its scope limits are in the supplement above. |
| AUD-226 | Tier-0 migration sources under alembic/versions/** must participate in the 100% coverage requirement; each tracked Tier-0 migration must be evidenced and meet 100% line, statement, branch, and function coverage. | P | fixed / missing | Open (S) | `docs/audits/AUDIT-2026-10.md:313` (snapshot, blob `ce20147fdbee`); `quality/quality-contract.json:268` (snapshot, blob `93d57cd21d2e`) | Run the source-bound Coverage & Quality Policy Gate for snapshot tree 20d4/current source after the Python and PostgreSQL migration coverage artifacts are produced; retain its valid merged manifest and per-file Tier-0 output showing every tracked alembic/versions migration at 100% for all four metrics with no exception. |
| AUD-245 | The KSV Trivy ignore entries reported at .trivyignore:17-26 were global, lacked manifest path scope, and had an expired review period. | U | fixed / sufficient | Scoped acceptance; see decision section | `.trivyignore:7` (snapshot, blob `03c6c6fad623`); `.trivyignore.yaml:6` (snapshot, blob `9c12f93dbdca`) | No additional action for this finding-specific scope; limitations below remain. |
| AUD-251 | The SPIRE agent receives cluster-wide nodes/proxy get/list/watch permissions. | P | partial / partial | Open (P) | `k8s/spire/spire-rbac.yaml:91` (snapshot, blob `5d871c81f229`); `k8s/spire/README.md:62` (snapshot, blob `8b730d4fa69f`) | Obtain an explicit owner decision on the SPIRE kubelet compatibility/profile and lifecycle policy; the narrow-role patch and ADR-054 remain private proposals. If least-privilege closure is chosen, integrate the approved nodes/pods-only role and fail-closed all-node gate, then capture a target-cluster effective-RBAC matrix (including nodes/proxy get/list/watch) plus real agent/workload SVID and mTLS success and negative controls. |
| AUD-269 | Reconcile 202603280001 removes approximately 15 hot-path indexes without restoring them. | P | fixed / sufficient | Scoped acceptance; see decision section | `docs/audits/AUDIT-2026-10.md:465` (snapshot, blob `ce20147fdbee`); `alembic/versions/202611020000_mvp_baseline.py:2060` (snapshot, blob `e4e0679260e8`) | No additional action for this finding-specific scope; limitations below remain. |
| AUD-272 | UNIQUE «delivery once» включает attempted_at и не препятствует повторным пушам | U | fixed / missing | Open (S) | `app/models/notifications.py:269` (snapshot, blob `630d7f513cd3`); `app/services/notifications/delivery.py:367` (snapshot, blob `39f0e548f5e0`) | Run the named owned-PostgreSQL cases and the sender-count replay case against this snapshot, capturing per-case results and source/test blob identities; do not infer success from the aggregate hosted shard. |
| AUD-275 | The historical migration builds indexes on messages and users without CONCURRENTLY while its docstring promises concurrent creation. | P | fixed / sufficient | Scoped acceptance; see decision section | `docs/adr/ADR-051-mvp-migration-baseline-squash.md:185` (snapshot, blob `905f99cd4ff5`); `alembic/versions/202611020000_mvp_baseline.py:30` (snapshot, blob `e4e0679260e8`) | No additional action for this finding-specific scope; limitations below remain. |
| AUD-277 | The AUDIT-2026-10 entry alleges that the historical migration's permissive USING (true) policy on eight tables prevents tenant isolation. Assess whether that unconditional policy itself bypassed the concurrent restrictive tenant policy; NULL-tenant visibility and the user-settable app.bypass_rls GUC are separate concerns under AUD-360/AUD-450. | N | fixed / partial | Scoped acceptance; see decision section | `alembic/versions/202607230001_multi_tenant_rls.py @ historical commit b011221c2:134` (historical, blob `2260227d65fe`); `alembic/versions/202607230001_multi_tenant_rls.py @ historical commit b011221c2:145` (historical, blob `2260227d65fe`) | No additional action for this finding-specific scope; limitations below remain. |
| AUD-278 | The upgrade chain drops the GIN index on events.search_vector and does not leave it restored. | P | fixed / sufficient | Scoped acceptance; see decision section | `docs/audits/AUDIT-2026-10.md:474` (snapshot, blob `ce20147fdbee`); `alembic/versions/202611020000_mvp_baseline.py:1531` (snapshot, blob `e4e0679260e8`) | No additional action for this finding-specific scope; limitations below remain. |
| AUD-309 | scripts/live_stand.py subprocess calls lack timeouts and lifecycle lock acquisition can wait indefinitely. | S | fixed / sufficient | Scoped acceptance; see decision section | `scripts/live_stand.py:1302` (snapshot, blob `aa4733565860`); `scripts/live_stand.py:3421` (snapshot, blob `aa4733565860`) | No additional action for this finding-specific scope; limitations below remain. |
| AUD-313 | Owned-stand seeding must not be authorized by environment variables alone, and reseeding must not overwrite the existing administrator password (original audit row: 'Гейт owned-stand основан на переменных окружения; сид переписывает пароль администратора'). | U | partial / partial | Open (P) | `scripts/seed_target.py:85` (snapshot, blob `e8b0d8a7c9cc`); `scripts/live_stand.py:5176` (snapshot, blob `aa4733565860`) | Require the seed-side record to prove an exact read-only owner bind mount or equivalent authenticated ownership, with a negative control showing that a matching ordinary file is refused. Run one source-bound seed through live_stand on an isolated owner-controlled Compose stand to verify the generated record is mounted read-only and cleaned up; keep the result scoped to seed/owner behavior rather than browser or broad full-stack acceptance. |
| AUD-321 | The E2E test has conditional checks with an annotation branch that lets the test pass green. | S | fixed / partial | Open (S) | `docs/audits/AUDIT-2026-10.md:517` (snapshot, blob `ce20147fdbee`); `frontend/tests/e2e/rate-limit-ux.spec.ts:45` (snapshot, blob `7e8c154ec902`) | Run the two named Playwright cases from frontend/tests/e2e/rate-limit-ux.spec.ts against this exact snapshot and retain per-case output plus the retry-after-timing attachment and source-tree preflight; confirm the persistent-429 case observes routed rejections and the retry case records statuses [429, 200] with the asserted delay. |
| AUD-322 | The original AUD-322 finding is that the event CRUD integration test and nightly chaos resilience cases can silently skip after authentication or chaos-user/chat precondition failures. In the configured integration run, those cases must fail visibly rather than count as skipped, and the nightly selector must include the named resilience cases. The criterion does not establish live SpiceDB authorization. | S | partial / partial | Open (P) | `docs/audits/AUDIT-2026-10.md:518` (snapshot, blob `ce20147fdbee`); `tests/integration/test_full_stack_flow.py:140` (snapshot, blob `e4fd08f4dad0`) | Add or identify a seed for the owned chaos account and one visible chat in nightly setup, then execute the five named test_resilience cases on this exact tree against the real owned Compose stack and retain JUnit that the validator accepts (five passed, zero skips/failures). |
| AUD-327 | The October audit reports that upgrading through historical revision 148642dd1207 fails on a legacy database with users whose role values are uppercase (original citation: alembic/versions/148642dd1207_fix_missing_tables.py:782-794). | U | fixed / sufficient | Scoped acceptance; see decision section | `docs/audits/AUDIT-2026-10.md:523` (snapshot, blob `ce20147fdbee`); `docs/adr/ADR-051-mvp-migration-baseline-squash.md:39` (snapshot, blob `905f99cd4ff5`) | No additional action for this finding-specific scope; limitations below remain. |
| AUD-332 | The October audit marked tests/test_start_docker_live_owner_key_paths.py:170-177 because the when_supported symlink tests created symlinks without checking whether native symlink creation was supported. Scope: gate those test cases on actual symlink capability. | S | fixed / sufficient | Scoped acceptance; see decision section | `tests/symlink_support.py:28` (snapshot, blob `05b184a700fd`); `tests/test_start_docker_live_owner_key_paths.py:172` (snapshot, blob `75c812b698c7`) | No additional action for this finding-specific scope; limitations below remain. |
| AUD-334 | Replay пропускается при rate limit или выключенном replay, пропуск не досылается (replay is skipped on rate limit or when replay is disabled; the missed replay is not sent later). | P | fixed / partial | Scoped acceptance at 484/512 (was Open at 478/512) | `services/ws-hub/pkg/hub/client.go:529` (snapshot, blob `68b0ae5e1a01`); `frontend/src/hooks/useChatWebSocket.ts:767` (snapshot, blob `d6d4568bcefa`) | Historical 478/512 remaining action: Execute the optional JetStream integration tests on this snapshot, including TestIntegrationAUD334RejectedResumeReconnectsAndReplaysFromJetStream, and record the named assertion that the previously missed sequence is delivered after resume recovery. Current evidence and its scope limits are in the supplement above. |
| AUD-346 | AUD-346: the nightly chaos-loadtest job must evaluate recovery; invoking the runner only with --dry-run lets valid manifests exit 0 without target traffic, fault injection, or recovery validation, so the job can be green without testing resilience. | U | unfixed / missing | Open (S) | `.github/workflows/nightly-full-gate.yml` (tree `ea381c19bda1`); `scripts/chaos/run_chaos_loadtest.py`; `tests/test_aud346_candidate_workflow.py`; `tests/test_aud346_live_fault_impact.py` | Run the owner-authorized live nested-cgroup Kind proof with confirmed injection, measured target degradation, guarded cleanup and recovery; retain a named receipt bound to this source tree. The current 43 focused tests are not a live runtime proof.
| AUD-347 | The nightly MinIO chaos suite never executes because the workflow supplies environment variable names the tests do not consume (docs/audits/AUDIT-2026-10.md:543). | S | fixed / missing | Open (S) | `docs/audits/AUDIT-2026-10.md:543` (snapshot, blob `ce20147fdbee`); `docs/audits/AUDIT-2026-10-31-review.md:95` (snapshot, blob `5d89d423c58f`) | After the snapshot source is on main, inspect the existing nightly Chaos Engineering (ToxiProxy) job and retain a source-bound JUnit receipt showing the two current S3 case names exactly once with no skips, failures or errors. If an unrelated chaos case blocks artifact upload, retain the exact named-case JUnit/log results and bind them to the same source SHA. |
| AUD-348 | AUDIT-2026-10.md:544: Upgrade 148642dd1207 removes Spotify tokens from users without transferring them. The dated reconciliation narrows the remaining historical loss case to an existing spotify_integrations row that blocks backfill before the legacy user columns are dropped. | P | fixed / sufficient | Scoped acceptance; see decision section | `docs/audits/AUDIT-2026-10.md:544` (snapshot, blob `ce20147fdbee`); `docs/audits/AUDIT-2026-10-30-reconciliation.md:369` (snapshot, blob `6c8637f0bb3d`) | No additional action for this finding-specific scope; limitations below remain. |
| AUD-350 | The historical 202603280001 migration changes stored_events.created_at to TIMESTAMPTZ by altering the existing column, rewriting the outbox table. | P | fixed / sufficient | Scoped acceptance; see decision section | `docs/audits/AUDIT-2026-10.md:546` (snapshot, blob `ce20147fdbee`); `alembic/versions/202603280001_reconcile_post_uuid_migration_drift.py:622` (historical, blob `f71934a46e83`) | No additional action for this finding-specific scope; limitations below remain. |
| AUD-360 | RLS rows with tenant_id IS NULL are visible to all tenants, and the application does not write tenant_id. | P | partial / missing | Open (P) | `docs/audits/AUDIT-2026-10.md:579` (snapshot, blob `ce20147fdbee`); `alembic/versions/202611020000_mvp_baseline.py:103` (snapshot, blob `e4e0679260e8`) | Run the snapshot-bound owned-PostgreSQL AUD-360 cases for NULL-row visibility, the actual NewsService and notification producers, and the bypass scheduler with cross-tenant/NULL negative controls. Confirm every remaining ordinary API insert path has transaction tenant context and every bypass producer supplies tenant ownership explicitly. |
| AUD-373 | Internal HTTP requests to the backend carry tokens and identity without TLS (original target: gateway-deployment.yaml). | U | partial / partial | Open (P) | `docs/audits/AUDIT-2026-10.md:592` (snapshot, blob `ce20147fdbee`); `charts/university-ecosystem/templates/gateway-deployment.yaml:95` (snapshot, blob `995929b7e065`) | Obtain owner acceptance of ADR-052 or record the replacement decision; the snapshot still marks this transport proposal unaccepted. Run the hosted Kind proof against the reviewed current source, require A/B/C/D to pass, and retain B's exact certificate-required TLS rejection diagnostic. Do not treat contract tests or a B failure with missing output as that proof. |
| AUD-375 | Service-worker queue replay can omit the CSRF header, retain a record after HTTP 403, and run without mutual exclusion across replay passes. | P | fixed / partial | Open (S) | `frontend/src/sw/offline.ts:432` (snapshot, blob `13205676d3ee`); `frontend/src/sw/offline.ts:782` (snapshot, blob `13205676d3ee`) | Execute both cases in the snapshot's frontend/tests/e2e/audit375-service-worker.spec.ts in Chromium and archive a receipt bound to this source tree and test blob; this is the smallest discriminating check for actual cookie/header forwarding, 403 removal, worker contention, and takeover recovery. |
| AUD-378 | The SLSA Provenance Dry-Run included in CI Success checked only whether ci.yml existed; it must verify provenance rather than accept file presence. | U | partial / partial | Open (S) | `docs/audits/AUDIT-2026-10.md:597` (snapshot, blob `ce20147fdbee`); `.github/workflows/ci.yml:1019` (snapshot, blob `f6ecac56cbf6`) | Make the verifier handle multiple gh verification results by selecting the unique result matching the exact current run invocation and artifact claims; add a two-valid-result regression and an ambiguity negative control. Obtain one passing hosted push run from the final reviewed source showing the exact frontend-dist archive digest and verified certificate/run claims, with provenance-check and CI Success passing. |
| AUD-380 | The October audit says .semgrep.yml claims Semgrep runs in CI, but no Semgrep scanner job exists (.semgrep.yml:20-21). | U | fixed / sufficient | Scoped acceptance; see decision section | `docs/audits/AUDIT-2026-10.md:599` (snapshot, blob `ce20147fdbee`); `.semgrep.yml:1` (snapshot, blob `94a21ff83822`) | No additional action for this finding-specific scope; limitations below remain. |
| AUD-381 | AUD-381: DAST, Scorecard и sqlmap не блокируют и не публикуют находки (scorecard.yml:77). | P | partial / missing | Open (P) | `.github/workflows/dast.yml:188` (snapshot, blob `cf8f833a6be2`); `scripts/quality/nuclei_findings_gate.py:42` (snapshot, blob `5921cf6c4f57`) | Add a real ZAP SARIF producer from the JSON report (or use a pinned producer that emits SARIF) and apply an owner-approved alert threshold; the current pinned action neither emits the expected SARIF file nor fails on alerts by default. Obtain an owner decision on the Scorecard Vulnerabilities floor; value 0 currently allows every valid vulnerability score. After source changes, run the current-source Nuclei, Scorecard, ZAP, and SQLMap flows with clean and known-finding controls, then retain named job outcomes, uploaded reports, and source/workflow SHA bindings. |
| AUD-384 | AUDIT-2026-10.md says the nightly Slack notification is not sent because the send step reads its own step-level env in if (.github/workflows/nightly-full-gate.yml:1066-1074). | S | fixed / sufficient | Original causal finding retracted as false positive | `docs/audits/AUDIT-2026-10.md:603` (snapshot, blob `ce20147fdbee`); `.github/workflows/nightly-full-gate.yml:1078` (snapshot, blob `d4a5c83ea53d`) | Keep the current output-gate rewrite and any live delivery claim distinct. |
| AUD-392 | The original AUD-392 entry says HIBP leaked-password screening is off by default and not required in production (docs/audits/AUDIT-2026-10.md:611). Its merged companion says password-policy defaults are weaker than a reasonable minimum and are not overridden in production (line 734). The fix scope is deployed-default HIBP screening with explicit production disable rejected, plus stronger password defaults; it does not require live HIBP service availability. | S | fixed / sufficient | Scoped acceptance; see decision section | `docs/audits/AUDIT-2026-10.md:611` (snapshot, blob `ce20147fdbee`); `docs/audits/AUDIT-2026-10.md:734` (snapshot, blob `ce20147fdbee`) | No additional action for this finding-specific scope; limitations below remain. |
| AUD-393 | The specific migration alembic/versions/202602010004_drop_legacy_columns.py (originally cited at lines 117-140) swallows DDL errors and mutates module state. | P | fixed / sufficient | Scoped acceptance; see decision section | `docs/audits/AUDIT-2026-10.md:612` (snapshot, blob `ce20147fdbee`); `docs/adr/ADR-051-mvp-migration-baseline-squash.md:39` (snapshot, blob `905f99cd4ff5`) | No additional action for this finding-specific scope; limitations below remain. |
| AUD-414 | The Rust crypto APIs accept scrypt N=1 and PBKDF2 iterations=1. | P | fixed / sufficient | Scoped acceptance; see decision section | `docs/audits/AUDIT-2026-10.md:633` (snapshot, blob `ce20147fdbee`); `frontend/rust-crypto/src/lib.rs:65` (snapshot, blob `b13a1e4e61dd`) | No additional action for this finding-specific scope; limitations below remain. |
| AUD-416 | AUDIT-2026-10 exact criterion: «wasm-fuzzer завершается с кодом 0 без фаззинга и нигде не подключён» (frontend/scripts/wasm-fuzzer.mjs:14-26). | P | fixed / partial | Scoped acceptance at 484/512 (was Open at 478/512) | `frontend/scripts/wasm-fuzzer.mjs:66` (snapshot, blob `df804f11cddf`); `frontend/scripts/wasm-fuzzer.mjs:448` (snapshot, blob `df804f11cddf`) | Historical 478/512 remaining action: Run the named seeded WASM campaign step in the Frontend Tests / WASM Contract Tests hosted job on this exact source tree and retain its successful step log with source-tree provenance. Current evidence and its scope limits are in the supplement above. |
| AUD-420 | The rescue bundle and archive inventory referenced by docs/audits/INDEX.md and the MVP plan were absent on disk at the documented local paths. | N | unproven / partial | Scoped acceptance at 484/512 (was Open at 478/512) | `docs/audits/AUDIT-2026-10.md:639` (snapshot, blob `ce20147fdbee`); `docs/audits/INDEX.md:288` (snapshot, blob `96d9ab020205`) | Historical 478/512 remaining action: Root owner decides whether the current repository object store plus the incremental branch-cleanup bundle satisfies the private-retention requirement, and chooses a durable private location before any copy or move. The branch-cleanup bundle alone is not a standalone full-history backup because it requires two prerequisite commits. Current evidence and its scope limits are in the supplement above. |
| AUD-422 | CONFIGURATION.md covered only 95 of 290 typed Settings fields and omitted some environment variables read outside Settings (docs/audits/AUDIT-2026-10.md:641). | P | fixed / partial | Scoped acceptance; see decision section | `CONFIGURATION.md`; `tests/test_configuration_settings_inventory.py`; `tests/test_configuration_reference.py`; `tests/test_configuration_outside_settings_drift.py` (tree `ea381c19bda1`) | No additional action for this documentation and inventory-contract criterion; limits below remain.
| AUD-423 | Correct documented numbers, paths, and defaults in README.md, README.ru.md, SECURITY.md, DEPLOY.md, and AGENTS.md that disagree with code; the original finding cites README.md:228 and README.ru.md:226. | P | partial / partial | Scoped acceptance; see decision section | `README.md`; `README.ru.md`; `SECURITY.md`; `AGENTS.md`; `docs/DEPLOY.md`; `docs/DEPLOY.en.md`; `app/auth/security.py`; `tests/test_docs_source_alignment_static.py`; `tests/test_argon2id_variant_enforcement.py` (tree `ea381c19bda1`) | No additional action for the documented source-alignment criterion; limits below remain.
| AUD-428 | Approximately 140 Python, 17 Go, and about 30 TypeScript test blocks lacked result checks. The criterion is a complete cross-language census and correction of test blocks that do not check results. | P | partial / partial | Open (P) | `docs/audits/AUDIT-2026-10.md:647` (snapshot, blob `ce20147fdbee`); `docs/audits/AUDIT-2026-10-30-reconciliation.md:877` (snapshot, blob `6c8637f0bb3d`) | Produce and preserve a reproducible Python and Go test-block census against this tree, with assertion-free negative controls; enumerate and correct all remaining resultless blocks, then record named runs. Add frontend negative controls for assertion-shaped no-ops and expect calls without matchers, and refine the classifier where they pass. |
| AUD-429 | E2E realtime suite and visual tests are not executed in CI (frontend/tests/e2e/chat-realtime.spec.ts:21, 24). | P | fixed / missing | Open (S) | `frontend/tests/e2e/chat-realtime.spec.ts:21` (snapshot, blob `b568a66b29ac`); `.github/workflows/reusable-e2e-tests.yml:420` (snapshot, blob `3d7f580f7641`) | Obtain a successful run of the existing required live-realtime-visual job bound to the exact reviewed source tree, with full-stand startup, 16/16 realtime passes and the complete authenticated visual matrix passing. |
| AUD-432 | E2E-live contract tests check spec-file text with regular expressions (docs/audits/AUDIT-2026-10.md:651, citing auth-login-lockout.contract.test.mjs:15-60). The dated scoped follow-on work names behavior-level evidence for lockout, full SSR, and registration (docs/superpowers/plans/2026-11-03-audit-evidence/l6.md:20,33-35); those boundaries define what the regex-only checks fail to establish. | P | partial / partial | Open (P) | `docs/audits/AUDIT-2026-10.md:651` (snapshot, blob `ce20147fdbee`); `frontend/tests/e2e-live/auth-login-lockout.contract.test.mjs:133` (snapshot, blob `aea09f60fe11`) | Run the current-source auth-login-lockout.live.spec.ts on desktop and mobile against the owned backend/database; retain named results showing the expected pre-threshold 401s, threshold 423, bounded Retry-After, no rate-limit 429 masking, and cleanup. Run register-double-submit.live.spec.ts on desktop and mobile against the owned real stack; retain named results proving two physical inputs produce exactly one real registration request/account and verified cleanup. Run the production SSR suite with playwright.ssr.config.ts and PRODUCTION_SERVER_E2E=true against the managed production server; retain results for login/register in both locales and the wrong-locale negative. Run the hydration scenarios if that behavior remains in the accepted scope. |
| AUD-433 | Fresh-chain intermediate state: notifications has no child partitions and writes fail before migration 202607020001. | U | fixed / sufficient | Scoped acceptance; see decision section | `alembic/versions/202611020000_mvp_baseline.py:31` (snapshot, blob `e4e0679260e8`); `alembic/versions/202611020000_mvp_baseline.py:584` (snapshot, blob `e4e0679260e8`) | No additional action for this finding-specific scope; limitations below remain. |
| AUD-434 | The original AUD-434 entry says that alembic check did not compare server defaults and that push_subscriptions.topics diverged from the model. This review tests that named PostgreSQL JSON default against the model and baseline; it does not broaden the finding to every schema object or database workflow. | P | fixed / sufficient | Scoped acceptance; see decision section | `docs/audits/AUDIT-2026-10.md:653` (snapshot, blob `ce20147fdbee`); `alembic/env.py:199` (snapshot, blob `16edeb9ffd9c`) | No additional action for this finding-specific scope; limitations below remain. |
| AUD-436 | live_stand Windows SID resolution searches whoami through PATH, so Git Bash may select its GNU whoami instead of the native Windows utility. | S | fixed / sufficient | Scoped acceptance; see decision section | `scripts/live_stand.py:584` (snapshot, blob `aa4733565860`); `scripts/live_stand.py:608` (snapshot, blob `aa4733565860`) | No additional action for this finding-specific scope; limitations below remain. |
| AUD-438 | ws-hub /metrics is reachable without authentication, unlike backend and gateway (services/ws-hub/main.go:485). | P | fixed / partial | Open (S) | `services/ws-hub/pkg/config/config.go:297` (snapshot, blob `718a7c9d736b`); `services/ws-hub/main.go:509` (snapshot, blob `78b12804300a`) | Run a narrowly scoped check on a policy-enforcing test cluster with the chart from this tree: unauthenticated GET /metrics succeeds from monitoring and is denied from an unselected namespace and public ingress; record rendered chart, policy, CNI and source-tree identity. |
| AUD-447 | Токен сброса пароля хранится открытым текстом в dead_letter_jobs (app/services/auth_service.py:166-176). | P | fixed / sufficient | Scoped acceptance; see decision section | `app/services/auth_service.py:170` (snapshot, blob `425cc1317c51`); `app/tasks/email.py:78` (snapshot, blob `972f7b00d40c`) | No additional action for this finding-specific scope; limitations below remain. |
| AUD-450 | Tenant RLS could be bypassed by an ordinary caller setting the user-settable app.bypass_rls GUC to on (latent database-boundary issue), originally cited at alembic/versions/202607230001_multi_tenant_rls.py:156-163. | S | fixed / sufficient | Scoped acceptance; see decision section | `alembic/versions/202611020000_mvp_baseline.py:2681` (snapshot, blob `e4e0679260e8`); `infrastructure/postgres-roles/bootstrap-app-roles.sql:64` (snapshot, blob `fc1c83a10809`) | No additional action for this finding-specific scope; limitations below remain. |
| AUD-454 | A race in the chat participant cache can leave a removed participant in the broadcast roster and deliver local WebSocket frames for up to one hour (app/api/ws/connection_manager.py:283-338). | P | fixed / partial | Open (S) | `app/api/ws/connection_manager.py:313` (snapshot, blob `6d7d7e81322e`); `app/api/ws/connection_manager.py:354` (snapshot, blob `6d7d7e81322e`) | Run the four skipped source-bound borrowed-session PostgreSQL cases against the owned AUD-363 disposable PostgreSQL fixture and retain their named results. For an end-to-end browser-frame claim, obtain a separate current-source receipt for backend removal through JetStream cache.revoke to Go ws-hub eviction and absence of a subsequent frame; current frontend and Go code do not prove a live subscriber or rollout. |
| AUD-474 | The live profile CSRF rejection check must not report that no csrf_token remains by deleting the cookie before it is observed; inspect the browser cookie state after the rejected request and before cleanup. | S | partial / partial | Scoped acceptance; see decision section | `frontend/tests/e2e-live/profile-csrf.live.spec.ts:187` (snapshot, blob `ceb50c39816a`); `frontend/tests/e2e-live/profile-csrf.live.spec.ts:202` (snapshot, blob `ceb50c39816a`) | No additional action for this finding-specific scope; limitations below remain. |
| AUD-478 | Configured NATS JetStream consumer settings were not applied, and cache.invalidate replayed the seven-day retained backlog on startup. | P | fixed / partial | Scoped acceptance at 484/512 (was Open at 478/512) | `services/ws-hub/pkg/hub/hub.go:730` (snapshot, blob `da7c6dcbf53c`); `services/ws-hub/pkg/hub/hub.go:1584` (snapshot, blob `da7c6dcbf53c`) | Historical 478/512 remaining action: Run the existing AUD-478 integration case on the snapshot source against real JetStream and inspect ConsumerInfo for both subscriptions, confirming DeliverNew on cache.invalidate, bounded cache.revoke replay, and the configured ack_wait, max_deliver, and inactive_threshold values. Current evidence and its scope limits are in the supplement above. |
| AUD-480 | PR-гейты не покрывают medium/low npm, dev-зависимости и unfixed (Trivy FS) | P | partial / partial | Scoped acceptance at 484/512 (was Open at 478/512) | `docs/audits/AUDIT-2026-10.md:564` (snapshot, blob `ce20147fdbee`); `.github/workflows/reusable-security-audit.yml:535` (snapshot, blob `8082923e1ebb`) | Historical 478/512 remaining action: Resolve the node_modules/frontend/node_modules Trivy scope gap retained from the prior P review, using a pinned Trivy 0.75.0 negative-control fixture with an unfixed HIGH or CRITICAL dependency and verifying that the scan surfaces it and the re-assert gate fails; bind the result to the final source tree. Current evidence and its scope limits are in the supplement above. |
| AUD-482 | The Caddy image resolves Go dependencies during build, has no committed lock, and is outside govulncheck and OSV scanning. | P | fixed / sufficient | Scoped acceptance; see decision section | `services/caddy/Dockerfile:28` (snapshot, blob `8ebb02df163d`); `services/caddy/go.mod:1` (snapshot, blob `5f03608a8324`) | No additional action for this finding-specific scope; limitations below remain. |
| AUD-483 | `sbom.yml` job `Go SBOM`: osv-scanner (Go) runs only on main; 75 open alerts (12 IDs); standard-library findings are based on the `go 1.26.4` directive, per CI reports. | P | partial / stale | Open (P) | `docs/audits/AUDIT-2026-10.md:567` (snapshot, blob `ce20147fdbee`); `.github/workflows/sbom.yml:90` (snapshot, blob `70c1828f464d`) | Obtain a completed hosted OSV/stdlib run bound to tree 20d4a080aeb0, retain the scanner result/package identities, and refresh the current-ref alert inventory to reconcile the historical 75 alerts/12 IDs. Confirm whether root go.mod and gen/go/go.mod are within the original Go scan scope; include them in the scan/reconciliation if they are. |
| AUD-484 | Stale open code-scanning and Dependabot alerts do not reflect current lock files (AUDIT-2026-10 reports 8 Trivy alerts on code-scanning, refs/heads/egorribun). | N | partial / partial | Open (P) | `docs/audits/AUDIT-2026-10.md:568` (snapshot, blob `ce20147fdbee`); `uv.lock:111` (snapshot, blob `8e1296d8b407`) | Obtain a Trivy analysis bound to the exact reviewed source SHA/tree and record whether each of IDs 2995-3002 becomes fixed or needs another explicit disposition; preserve the gap that the original audit row omitted IDs unless its original CI artifact supplies them. Requery the current Dependabot alert inventory and compare every relevant open advisory/package version to the exact reviewed lockfiles, then record an item-by-item disposition. The 2026-11-05 Dependabot inventory is historical, not current proof. |
| AUD-501 | The hidden-tab pause live test must assert that story progress stays frozen during the hidden interval, not merely check the story after returning to the visible tab (AUD-501; frontend/tests/e2e-live/story-viewer-keyboard.live.spec.ts:84, 90-100). | S | fixed / partial | Open (S) | `frontend/tests/e2e-live/story-viewer-keyboard.live.spec.ts:97` (snapshot, blob `4aebb26ff391`); `frontend/tests/e2e-live/story-viewer-keyboard.live.spec.ts:114` (snapshot, blob `4aebb26ff391`) | Run the clock-controlled hidden-tab Playwright case against the owned full live stand on the frozen source in both desktop and mobile projects; capture each named result and verify the hidden-visibility negative control executes. |
| AUD-506 | Temporal used HTTP for JWKS key discovery and the noop authorizer, allowing forged or unauthorized JWTs to reach Temporal operations (services/temporal/config.yaml:100-107). | P | fixed / sufficient | Scoped acceptance; see decision section | `services/temporal/config.yaml:104` (snapshot, blob `f8e130aba3aa`); `services/temporal/entrypoint.sh:36` (snapshot, blob `4c1c5e552e7f`) | No additional action for this finding-specific scope; limitations below remain. |

## 25 prior scoped acceptance decisions at the 478/34 checkpoint

### AUD-073 — scoped acceptance

**Original criterion:** White text on sent messages has insufficient contrast on the light violet gradient. The source contract measures adequate normal-text contrast at WCAG AA 4.5:1.

**Evidence:** The real ChatWindow Playwright contrast suite passed 6/6: light and dark desktop/mobile renderings plus the original-gradient and translucent-text negative controls. The source-pinned run took 21.71 seconds on the cached matching Chromium headless shell.

**Source pointers:** `frontend/src/components/messenger/ChatWindow.tsx:746` (snapshot, blob `91c4f11d2b5d`); `frontend/src/styles/tokens/messenger.css:95` (snapshot, blob `2425bc81977c`); `frontend/src/styles/tokens/primitives.css:79` (snapshot, blob `bac31979836f`); `frontend/tests/e2e/sent-bubble-contrast.spec.ts:18` (snapshot, blob `fe5f55db8548`)

**Boundary:** The first full-Chrome launch failed before assertions and is not counted. This proves the named ChatWindow contrast behavior, not the full app, through-Caddy behavior, or all final-source checks.

**Receipt bindings:** run-result SHA-256 prefix 77318B9BB075; verification-summary SHA-256 prefix 67BCA22B153D.

### AUD-245 — scoped acceptance

**Original criterion:** The KSV Trivy ignore entries reported at .trivyignore:17-26 were global, lacked manifest path scope, and had an expired review period.

**Evidence:** The exact Trivy path-scope test passed as part of 13 tests with Trivy 0.75.0; the IaC scanner step also passed. The negative control kept an identical finding visible in a file outside the exception path.

**Source pointers:** `.trivyignore:7` (snapshot, blob `03c6c6fad623`); `.trivyignore.yaml:6` (snapshot, blob `9c12f93dbdca`); `scripts/quality/prove_aud245_trivy_path_scope.py:55` (snapshot, blob `2a7b6d65fb55`); `scripts/quality/prove_aud245_trivy_path_scope.py:183` (snapshot, blob `2a7b6d65fb55`)

**Boundary:** Acceptance is limited to exact path-scoped exceptions and their negative control. This is not a whole-repository vulnerability-clearance claim; unrelated failures in the surrounding Actions run remain separate.

**Receipt bindings:** Source-bound primary report SHA-256 prefix 1862da6b5419.

### AUD-269 — scoped acceptance

**Original criterion:** Reconcile 202603280001 removes approximately 15 hot-path indexes without restoring them.

**Evidence:** The 19-name crosswalk was reconciled as eight identities retained in both schemas, eight approved parent-index additions in the baseline, two HNSW aliases, and the approved lower-email unique-index replacement. The source-matched owned-PG schema-delta suite passed 10/10. A dedicated native PostgreSQL 17.11/pgvector 0.8.7 case passed and observed the current news HNSW tuple 1/1536/16/64; a real 1/1536/8/32 alternate index was rejected. The independent review ACCEPTs this narrow original criterion.

**Source pointers:** `docs/audits/AUDIT-2026-10.md:465` (snapshot, blob `ce20147fdbee`); `alembic/versions/202611020000_mvp_baseline.py:2060` (snapshot, blob `e4e0679260e8`); `alembic/versions/202611020000_mvp_baseline.py:1709` (snapshot, blob `e4e0679260e8`); `alembic/versions/202611020000_mvp_baseline.py:2879` (snapshot, blob `e4e0679260e8`)

**Boundary:** The 19 candidates are not 19 independently lost indexes. The extra 19-row catalog patch was compile-only, so this does not establish indisvalid/indisready/indislive for every mapped row. Raw relation-page bytes were not retained; no performance benchmark, deployed-catalog inspection, or hosted check is claimed. The PostgreSQL proof emitted a pytest record_property/xunit2 compatibility warning; this is not a zero-warning gate result.

**Receipt bindings:** Schema-equivalence receipt SHA-256 prefix 64DAE77AC77D; native HNSW receipt SHA-256 prefix 07295E035D66; independent review SHA-256 prefix B7A45BD5B912.

### AUD-275 — scoped acceptance

**Original criterion:** The historical migration builds indexes on messages and users without CONCURRENTLY while its docstring promises concurrent creation.

**Evidence:** Owned PostgreSQL 17 fresh-schema equivalence/refusal proof passed 10/10. The exact schema-delta and catalog tests passed, including nonempty-schema and populated-pgx refusal controls.

**Source pointers:** `docs/adr/ADR-051-mvp-migration-baseline-squash.md:185` (snapshot, blob `905f99cd4ff5`); `alembic/versions/202611020000_mvp_baseline.py:30` (snapshot, blob `e4e0679260e8`); `alembic/versions/202611020000_mvp_baseline.py:2843` (snapshot, blob `e4e0679260e8`); `alembic/versions/202611020000_mvp_baseline.py:1600` (snapshot, blob `e4e0679260e8`)

**Boundary:** ADR-051 retires the populated pre-squash upgrade criterion. This establishes fresh empty-schema creation/equivalence; it does not claim a populated-table lock measurement or concurrent index build.

**Receipt bindings:** Shared owned-PG receipt SHA-256 prefix 64DAE77AC77D; JUnit SHA-256 prefix 7AF45095C3CF.

### AUD-277 — scoped acceptance

**Original criterion:** The AUDIT-2026-10 entry alleges that the historical migration's permissive USING (true) policy on eight tables prevents tenant isolation. Assess whether that unconditional policy itself bypassed the concurrent restrictive tenant policy; NULL-tenant visibility and the user-settable app.bypass_rls GUC are separate concerns under AUD-360/AUD-450.

**Evidence:** The current canonical baseline has no unconditional `USING (true)` policy on the checked RLS tables. The source-matched owned-PostgreSQL equivalence/catalog run passed 10/10 and included the current catalog assertion.

**Source pointers:** `alembic/versions/202607230001_multi_tenant_rls.py @ historical commit b011221c2:134` (historical, blob `2260227d65fe`); `alembic/versions/202607230001_multi_tenant_rls.py @ historical commit b011221c2:145` (historical, blob `2260227d65fe`); `docs/audits/AUDIT-2026-10.md:473` (snapshot, blob `ce20147fdbee`); `alembic/versions/202611020000_mvp_baseline.py:2641` (snapshot, blob `e4e0679260e8`)

**Boundary:** Acceptance is limited to the current-baseline source closure under ADR-051. The test does not prove that the historical permissive policy bypassed the contemporaneous restrictive tenant predicate, caused an incident, or that any deployed database was exposed.

**Receipt bindings:** Shared owned-PG receipt SHA-256 prefix 64DAE77AC77D; independent review SHA-256 prefix 73BE375A6E99.

### AUD-278 — scoped acceptance

**Original criterion:** The upgrade chain drops the GIN index on events.search_vector and does not leave it restored.

**Evidence:** The actual pre-squash and baseline PostgreSQL statement/catalog comparison passed in the 10/10 owned-PG run and confirms the current baseline contains the events search-vector GIN index.

**Source pointers:** `docs/audits/AUDIT-2026-10.md:474` (snapshot, blob `ce20147fdbee`); `alembic/versions/202611020000_mvp_baseline.py:1531` (snapshot, blob `e4e0679260e8`); `docs/adr/ADR-051-mvp-migration-baseline-squash.md:39` (snapshot, blob `905f99cd4ff5`); `tests/integration/test_mvp_baseline_schema_equivalence.py:920` (snapshot, blob `227683c09284`)

**Boundary:** The finding is accepted for the final fresh-baseline index state only. ADR-051 retires replay of populated historical upgrades; no retry, locking, or deployed performance claim is made.

**Receipt bindings:** Shared owned-PG receipt SHA-256 prefix 64DAE77AC77D.

### AUD-309 — scoped acceptance

**Original criterion:** scripts/live_stand.py subprocess calls lack timeouts and lifecycle lock acquisition can wait indefinitely.

**Evidence:** Source inspection establishes finite subprocess and lifecycle-lock bounds. Named Windows checks passed for a child/grandchild timeout with inherited pipes and for real cross-process lock contention/recovery; the bounded retry control also passed.

**Source pointers:** `scripts/live_stand.py:1302` (snapshot, blob `aa4733565860`); `scripts/live_stand.py:3421` (snapshot, blob `aa4733565860`); `scripts/fast_preflight.py:409` (snapshot, blob `af7aa1f2152a`); `tests/test_live_stand_subprocess_timeouts.py:26` (snapshot, blob `f45186134308`)

**Boundary:** A POSIX-only case was skipped on Windows. The acceptance is for the deterministic host-side bounded-lifecycle criterion, not a deployed service or a claim that a POSIX runtime case executed.

**Receipt bindings:** Primary report SHA-256 prefix e7670b013a87.

### AUD-327 — scoped acceptance

**Original criterion:** The October audit reports that upgrading through historical revision 148642dd1207 fails on a legacy database with users whose role values are uppercase (original citation: alembic/versions/148642dd1207_fix_missing_tables.py:782-794).

**Evidence:** Owned PostgreSQL 17 fresh-schema equivalence/refusal proof passed 10/10. The current baseline models both role-enum labels and refuses to apply over a nonempty existing schema.

**Source pointers:** `docs/audits/AUDIT-2026-10.md:523` (snapshot, blob `ce20147fdbee`); `docs/adr/ADR-051-mvp-migration-baseline-squash.md:39` (snapshot, blob `905f99cd4ff5`); `alembic/versions/202611020000_mvp_baseline.py:77` (snapshot, blob `e4e0679260e8`); `alembic/versions/202611020000_mvp_baseline.py:2843` (snapshot, blob `e4e0679260e8`)

**Boundary:** ADR-051 retires populated legacy-row upgrade coverage. This is a fresh-schema baseline result, not an upgrade of an existing database containing uppercase-role rows.

**Receipt bindings:** Shared owned-PG receipt SHA-256 prefix 64DAE77AC77D.

### AUD-332 — scoped acceptance

**Original criterion:** The October audit marked tests/test_start_docker_live_owner_key_paths.py:170-177 because the when_supported symlink tests created symlinks without checking whether native symlink creation was supported. Scope: gate those test cases on actual symlink capability.

**Evidence:** The native Windows proof job reported 164 passed and two POSIX-only tests deselected. It exercised both original symlink cases, file/directory denial probes, the source census, and the synthetic ungated-test negative control.

**Source pointers:** `tests/symlink_support.py:28` (snapshot, blob `05b184a700fd`); `tests/test_start_docker_live_owner_key_paths.py:172` (snapshot, blob `75c812b698c7`); `tests/test_symlink_privilege_probe_contract.py:189` (snapshot, blob `a5e259d29eb0`); `tests/test_symlink_privilege_probe_contract.py:270` (snapshot, blob `a5e259d29eb0`)

**Boundary:** This is scoped native-Windows test-setup evidence. The POSIX-only cases were not executed; no full CI or unrelated Windows-proof claim follows.

**Receipt bindings:** Source-bound primary report SHA-256 prefix 23ECEEF1CD03.

### AUD-348 — scoped acceptance

**Original criterion:** AUDIT-2026-10.md:544: Upgrade 148642dd1207 removes Spotify tokens from users without transferring them. The dated reconciliation narrows the remaining historical loss case to an existing spotify_integrations row that blocks backfill before the legacy user columns are dropped.

**Evidence:** The 10/10 owned-PostgreSQL statement/catalog comparison confirms the fresh baseline creates the Spotify integration table directly and matches the pinned pre-squash endpoint except for approved additions.

**Source pointers:** `docs/audits/AUDIT-2026-10.md:544` (snapshot, blob `ce20147fdbee`); `docs/audits/AUDIT-2026-10-30-reconciliation.md:369` (snapshot, blob `6c8637f0bb3d`); `alembic/versions/148642dd1207_fix_missing_tables.py:870` (historical, blob `d762c45c9248`); `docs/adr/ADR-051-mvp-migration-baseline-squash.md:57` (snapshot, blob `905f99cd4ff5`)

**Boundary:** ADR-051 retires the populated historical token-backfill requirement. No claim is made that existing Spotify token rows were transferred or repaired.

**Receipt bindings:** Shared owned-PG receipt SHA-256 prefix 64DAE77AC77D.

### AUD-350 — scoped acceptance

**Original criterion:** The historical 202603280001 migration changes stored_events.created_at to TIMESTAMPTZ by altering the existing column, rewriting the outbox table.

**Evidence:** The 10/10 owned-PostgreSQL schema-equivalence/refusal run passed, and the named `test_aud350_stored_events_postgres_precision_roundtrip_is_equivalent` also passed on PostgreSQL. The latter checks timezone-aware instants and microsecond precision across the baseline schemas.

**Source pointers:** `docs/audits/AUDIT-2026-10.md:546` (snapshot, blob `ce20147fdbee`); `alembic/versions/202603280001_reconcile_post_uuid_migration_drift.py:622` (historical, blob `f71934a46e83`); `alembic/versions/202611020000_mvp_baseline.py:30` (snapshot, blob `e4e0679260e8`); `alembic/versions/202611020000_mvp_baseline.py:708` (snapshot, blob `e4e0679260e8`)

**Boundary:** ADR-051 retires populated historical TIMESTAMPTZ rewrite coverage. No populated-table rewrite, lock-duration, or production-row conversion claim is made; a separate test in the shared batch is not used to broaden this disposition.

**Receipt bindings:** Schema-equivalence receipt SHA-256 prefix 64DAE77AC77D; direct roundtrip JUnit SHA-256 prefix 9ACD5FF6EB8D.

### AUD-380 — scoped acceptance

**Original criterion:** The October audit says .semgrep.yml claims Semgrep runs in CI, but no Semgrep scanner job exists (.semgrep.yml:20-21).

**Evidence:** The frozen source now contains the promised Semgrep scanner invocation, raw-result validation, and a blocking aggregate dependency, so the original missing-job criterion is addressed.

**Source pointers:** `docs/audits/AUDIT-2026-10.md:599` (snapshot, blob `ce20147fdbee`); `.semgrep.yml:1` (snapshot, blob `94a21ff83822`); `.github/workflows/ci.yml:1053` (snapshot, blob `f6ecac56cbf6`); `.github/workflows/ci.yml:4781` (snapshot, blob `f6ecac56cbf6`)

**Boundary:** This is a source-level job-presence acceptance only. The cited hosted Matrix cancelled before a semgrep-sast job; no clean Semgrep scan or current SAST clearance is claimed.

**Receipt bindings:** Primary report SHA-256 prefix 596b51e6998f.

### AUD-392 — scoped acceptance

**Original criterion:** The original AUD-392 entry says HIBP leaked-password screening is off by default and not required in production (docs/audits/AUDIT-2026-10.md:611). Its merged companion says password-policy defaults are weaker than a reasonable minimum and are not overridden in production (line 734). The fix scope is deployed-default HIBP screening with explicit production disable rejected, plus stronger password defaults; it does not require live HIBP service availability.

**Evidence:** A fresh source-pinned serial run passed all 80 named cases across six modules with zero skips. It covers deployed staging/production HIBP defaults, rejection of deployed explicit-disable settings, clean/breached/error policy, and password-policy controls.

**Source pointers:** `docs/audits/AUDIT-2026-10.md:611` (snapshot, blob `ce20147fdbee`); `docs/audits/AUDIT-2026-10.md:734` (snapshot, blob `ce20147fdbee`); `docs/audits/AUDIT-2026-10-30-reconciliation.md:85` (snapshot, blob `6c8637f0bb3d`); `docs/audits/AUDIT-2026-11-01-review.md:309` (snapshot, blob `fca2b2a37fb2`)

**Boundary:** External HIBP transport was mocked and SQLite was used in the harness. This proves configuration and enforcement paths, not live HIBP availability.

**Receipt bindings:** Summary SHA-256 prefix BF8C9EE6A592; JUnit SHA-256 prefix 01F689DF55F4; independent review SHA-256 prefix 59971D08FEBC.

### AUD-393 — scoped acceptance

**Original criterion:** The specific migration alembic/versions/202602010004_drop_legacy_columns.py (originally cited at lines 117-140) swallows DDL errors and mutates module state.

**Evidence:** The source-matched 10/10 owned-PostgreSQL schema-equivalence run passed its exact statement/catalog assertions and existing-schema refusal controls. In the active baseline, the historical migration is absent and DDL is emitted directly without the old swallowed-error/module-state pattern.

**Source pointers:** `docs/audits/AUDIT-2026-10.md:612` (snapshot, blob `ce20147fdbee`); `docs/adr/ADR-051-mvp-migration-baseline-squash.md:39` (snapshot, blob `905f99cd4ff5`); `docs/adr/ADR-051-mvp-migration-baseline-squash.md:84` (snapshot, blob `905f99cd4ff5`); `alembic/versions/202611020000_mvp_baseline.py:2794` (snapshot, blob `e4e0679260e8`)

**Boundary:** Acceptance is within ADR-051 fresh-baseline scope. No populated historical upgrade or hosted final-source check is claimed.

**Receipt bindings:** Shared owned-PG receipt SHA-256 prefix 64DAE77AC77D.

### AUD-414 — scoped acceptance

**Original criterion:** The Rust crypto APIs accept scrypt N=1 and PBKDF2 iterations=1.

**Evidence:** The native Rust run reported 12 unit and 24 native integration tests passed. The direct public-API boundary tests reject scrypt N=1 and PBKDF2 iterations=1 below the accepted floors.

**Source pointers:** `docs/audits/AUDIT-2026-10.md:633` (snapshot, blob `ce20147fdbee`); `frontend/rust-crypto/src/lib.rs:65` (snapshot, blob `b13a1e4e61dd`); `frontend/rust-crypto/src/lib.rs:172` (snapshot, blob `b13a1e4e61dd`); `frontend/rust-crypto/src/tests.rs:57` (snapshot, blob `1dca50a16c3f`)

**Boundary:** One rustc linker notice was recorded; no zero-warning-gate result is claimed. The narrow criterion does not extend to WASM/browser error mapping.

**Receipt bindings:** Result SHA-256 prefix E3E17AB59762; output-log SHA-256 prefix 425C085D89FE.

### AUD-422 — scoped acceptance

**Original criterion:** `CONFIGURATION.md` documented only 95 of 290 typed Settings fields and omitted environment variables read outside `Settings`.

**Evidence:** The integrated configuration inventory now documents all 290 typed Settings fields and the environment reads outside `Settings`. The three named contract modules passed 24/24 on the integrated source; the independent source review passed.

**Source pointers:** `CONFIGURATION.md`; `tests/test_configuration_settings_inventory.py`; `tests/test_configuration_reference.py`; `tests/test_configuration_outside_settings_drift.py`.

**Boundary:** This accepts the documentation and inventory-contract criterion. It does not establish runtime behavior for every deployment environment, secret delivery, or hosted checks for later source changes.

**Receipt bindings:** Root integration receipt SHA-256 prefix `f924988bb3b7`; actual-main focused test receipt SHA-256 prefix `4487e9069793` (24/24, source pins unchanged); independent review recorded in the integration receipt.

### AUD-423 — scoped acceptance

**Original criterion:** Documented numbers, paths and defaults in README, SECURITY, DEPLOY and AGENTS disagreed with source-of-truth configuration and behavior.

**Evidence:** The integrated source/doc updates were followed by an actual-main serial regression run: 118 tests plus six subtests passed; JUnit reported 124 test cases, zero failures/errors/skips, and no warnings summary. All 137 pinned paths matched the run’s source tree `aa5777f68db6` before and after. A later test-fixture-only update at tree `ea381c19bda1` switched the ephemeral Argon2 test password to a CSPRNG value; no rerun on that later fixture version is claimed.

**Source pointers:** `README.md`; `README.ru.md`; `SECURITY.md`; `AGENTS.md`; `docs/DEPLOY.md`; `docs/DEPLOY.en.md`; `app/auth/security.py`; `tests/test_docs_source_alignment_static.py`; `tests/test_argon2id_variant_enforcement.py`.

**Boundary:** This accepts the documented source-alignment criterion for the updated surfaces and named regression checks. It does not establish every deployment value, a production-account inventory, full Tier-0 coverage, hosted required checks, or deployment state.

**Receipt bindings:** Root integration receipt SHA-256 prefix `8416c228788a`; actual-main regression receipt SHA-256 prefix `4585d7b71080` (118 tests plus 6 subtests, source pins stable).

### AUD-433 — scoped acceptance

**Original criterion:** Fresh-chain intermediate state: notifications has no child partitions and writes fail before migration 202607020001.

**Evidence:** The sole selected owned-PostgreSQL test passed from candidate SHA-256 prefix 5201F72D9641: the fresh baseline had the 26 notification children, accepted a routed write, and the rollback-only no-child control failed with SQLSTATE 23514.

**Source pointers:** `alembic/versions/202611020000_mvp_baseline.py:31` (snapshot, blob `e4e0679260e8`); `alembic/versions/202611020000_mvp_baseline.py:584` (snapshot, blob `e4e0679260e8`); `alembic/versions/202611020000_mvp_baseline.py:2488` (snapshot, blob `e4e0679260e8`); `tests/integration/test_aud433_notifications_baseline_partition.py:130` (snapshot, blob `2b4805a78cc6`)

**Boundary:** This is a fresh-chain migration case only, not a hosted required-check or deployed-cluster result. The executed copy differed from the frozen test only by a formatting line-wrap; assertions and SQL matched.

**Receipt bindings:** Owned-PostgreSQL receipt SHA-256 prefix CEDF6CB4643B; JUnit SHA-256 prefix 044E09A26805 Current indexed test source at tree `13693bbf3d16` has Git blob `2b4805a78cc6`..

### AUD-434 — scoped acceptance

**Original criterion:** The original AUD-434 entry says that alembic check did not compare server defaults and that push_subscriptions.topics diverged from the model. This review tests that named PostgreSQL JSON default against the model and baseline; it does not broaden the finding to every schema object or database workflow.

**Evidence:** The named PostgreSQL 17 case passed 1/1: a deliberate JSON server-default change was detected by Alembic as `modify_default`, then restoration returned the baseline to a clean check. The independent review accepts only the original default-comparison criterion.

**Source pointers:** `docs/audits/AUDIT-2026-10.md:653` (snapshot, blob `ce20147fdbee`); `alembic/env.py:199` (snapshot, blob `16edeb9ffd9c`); `alembic/env.py:208` (snapshot, blob `16edeb9ffd9c`); `app/core/db/alembic_json_server_defaults.py:44` (snapshot, blob `5275eb138295`)

**Boundary:** A separate 19-case unit JUnit has pytest exit 1 because the selected file-wide 100% coverage threshold failed; those cases are not represented as a global or file-wide coverage pass. Active floors and required checks remain unchanged.

**Receipt bindings:** Primary report SHA-256 prefix B865A7A9A16F; independent review SHA-256 prefix 08B1DD466AFE.

### AUD-436 — scoped acceptance

**Original criterion:** live_stand Windows SID resolution searches whoami through PATH, so Git Bash may select its GNU whoami instead of the native Windows utility.

**Evidence:** The named native-Windows test passed within the 164-pass proof job: with Git Bash ahead of System32 on PATH, the resolver still selects native System32 `whoami.exe` and returns the expected SID. A separate bounded native collector corroborates the path shadow.

**Source pointers:** `scripts/live_stand.py:584` (snapshot, blob `aa4733565860`); `scripts/live_stand.py:608` (snapshot, blob `aa4733565860`); `tests/test_start_docker_live_stand_state_root.py:423` (snapshot, blob `cbc022ba685c`); `.github/workflows/ci.yml:1337` (snapshot, blob `f6ecac56cbf6`)

**Boundary:** The whole `live_stand.py` file differs from the hosted run; acceptance is limited to the exact resolver functions/test bodies pinned to this tree. It is not a full-file or full-CI pass.

**Receipt bindings:** Primary report SHA-256 prefix EA65D1510C9D.

### AUD-447 — scoped acceptance

**Original criterion:** A password-reset token could be stored in plaintext in `dead_letter_jobs`.

**Evidence:** On the documented never-deployed snapshot, the corrected persistence regression passed 6/6 in committed-then-fresh-session SQLite checks. Malformed JSON, duplicate keys, and hash mismatch across dedup/replay leave no plaintext marker; identity/retry controls stayed stable and no message was published. Independent review ACCEPTs the criterion-specific scope.

**Source pointers:** `app/services/auth_service.py:170` (snapshot, blob `425cc1317c51`); `app/tasks/email.py:78` (snapshot, blob `972f7b00d40c`); `app/core/nats_broker.py:591` (snapshot, blob `45ab3fe9ee65`); `app/workers/dead_letter_queue.py:344` (snapshot, blob `02ce0856f0bc`)

**Boundary:** The platform was never deployed, so a production-data inventory is not required for this disposition. The run used in-memory SQLite, not PostgreSQL; it does not establish an all-status sweep, exact tombstone bytes, token-echo error redaction by itself, or hosted-check evidence.

**Receipt bindings:** SQLite summary SHA-256 prefix 767A1DDD604F; output SHA-256 prefix 4706AFAF18F6; independent review SHA-256 prefix 800EF471F1F3.

### AUD-450 — scoped acceptance

**Original criterion:** Tenant RLS could be bypassed by an ordinary caller setting the user-settable app.bypass_rls GUC to on (latent database-boundary issue), originally cited at alembic/versions/202607230001_multi_tenant_rls.py:156-163.

**Evidence:** The source-pinned owned-PostgreSQL run passed 3/3: an ordinary role could not expose another tenant or NULL-tenant rows by setting the user-controlled GUC; the dedicated authorized bypass-role member saw all rows; and rollback cleared the transaction-local GUC on the same backend. Independent review ACCEPTs this criterion.

**Source pointers:** `alembic/versions/202611020000_mvp_baseline.py:2681` (snapshot, blob `e4e0679260e8`); `infrastructure/postgres-roles/bootstrap-app-roles.sql:64` (snapshot, blob `fc1c83a10809`); `app/core/db/listeners.py:30` (snapshot, blob `1c8f7a90d673`); `tests/integration/test_aud277_360_450_tenant_rls_postgres.py:263` (snapshot, blob `d788eea37046`)

**Boundary:** The disposable PG17 container was loopback-only and removed. The ephemeral host-port number was not retained; the fixture validated a numeric port. This does not broaden AUD-277 historical policy-causality claims.

**Receipt bindings:** Runtime receipt SHA-256 prefix CDF36D99CA01; JUnit SHA-256 prefix 4199586572E9; independent review SHA-256 prefix 2C159B15BC1D.

### AUD-474 — scoped acceptance

**Original criterion:** The live profile CSRF rejection check must not report that no csrf_token remains by deleting the cookie before it is observed; inspect the browser cookie state after the rejected request and before cleanup.

**Evidence:** The corrected oracle observes cookie state after each 403 and before cleanup, with a Set-Cookie negative control. Four Chromium cases passed on byte-identical candidate files and two Node contract cases passed again on exact current index tree 13693; the three source files match the recorded SHA-256 prefix pins. Root ACCEPTs the original finding-specific test-oracle criterion.

**Source pointers:** `frontend/tests/e2e-live/profile-csrf.live.spec.ts` (SHA-256 prefix `e0fe23a98d71`); `frontend/tests/e2e-live/profile-csrf.contract.test.mjs` (SHA-256 prefix `109f7147a315440d9aef6934c813f35e6ac06db7dac73fa77a1ecdf645e3bd4`); `frontend/tests/e2e-live/profile-csrf-observation.contract.test.mjs` (SHA-256 prefix `71a8fd74fa6f`)

**Boundary:** Responses are synthetic. No full live stand, real backend, or end-to-end profile flow is claimed. The result is not a whole-frontend or overall CI acceptance.

**Receipt bindings:** Final source tree 13693bbf3d16; Node receipt SHA-256 prefix D8CDEE48038A; Chromium proof receipt SHA-256 prefix A69D2E7CD597; source SHA-256 prefix pins: live spec E0FE23A98D71, Node contract 109F7147A315440D9AEF6934C813F35E6AC06DB7DAC73FA77A1ECDF645E3BD4, observation contract 71A8FD74FA6F.

### AUD-482 — scoped acceptance

**Original criterion:** The Caddy image resolves Go dependencies during build, has no committed lock, and is outside govulncheck and OSV scanning.

**Evidence:** The committed Caddy module graph is consumed readonly by the build and included in hosted Go/OSV scanner scope. The Caddy module scan, exact OSV result validation, and exact manifest/license negative guards passed. OSV evaluated 166 packages and reported three module-level go-jose findings covered by finite current dispositions.

**Source pointers:** `services/caddy/Dockerfile:28` (snapshot, blob `8ebb02df163d`); `services/caddy/go.mod:1` (snapshot, blob `5f03608a8324`); `services/caddy/go.sum:1` (snapshot, blob `ad41ab132a87`); `.github/workflows/reusable-security-audit.yml:1013` (snapshot, blob `8082923e1ebb`)

**Boundary:** Acceptance is limited to the missing-lock/scanner-scope criterion. The existing advisories remain explicitly disposed; no zero-vulnerability or deployed-runtime claim is made.

**Receipt bindings:** Primary report SHA-256 prefix 4D200BC71C7D; independent review SHA-256 prefix 9D29CA600CE1.

### AUD-506 — scoped acceptance

**Original criterion:** Temporal used HTTP for JWKS key discovery and the noop authorizer, allowing forged or unauthorized JWTs to reach Temporal operations (services/temporal/config.yaml:100-107).

**Evidence:** The actual token producer and file-processor permission flow passed: a product-minted `default:write` token started the real workflow and the worker processed it. Missing, forged, wrong-audience, and valid-signature/no-permission controls were denied.

**Source pointers:** `services/temporal/config.yaml:104` (snapshot, blob `f8e130aba3aa`); `services/temporal/entrypoint.sh:36` (snapshot, blob `4c1c5e552e7f`); `docker-compose.yml:725` (snapshot, blob `27317a338a64`); `docker-compose.full.yml:1409` (snapshot, blob `03da01e15c1a`)

**Boundary:** This is a scoped producer/consumer runtime proof, not full Temporal or hosted CI acceptance. No token value is published.

**Receipt bindings:** Primary report SHA-256 prefix A3A0D6A126DD; independent review SHA-256 prefix D07B8B5E4E73.

## AUD-384 — original causal finding retracted as a false positive

**Original criterion:** the nightly Slack send step allegedly could not read the env value referenced by its own step-level `if` condition.

**Finding:** pinned GitHub documentation permits the step-level env context in `steps.if`, and the immutable runner merges step env before evaluating the condition. The original same-step-env causal allegation is therefore retracted. This does not establish current live Slack delivery; the separate output-gate rewrite remains a distinct source change. No test result is claimed for the unexecuted candidate cases.

**Source pointers:** `docs/audits/AUDIT-2026-10.md:603` (snapshot, blob `ce20147fdbee`); `.github/workflows/nightly-full-gate.yml:1078` (snapshot, blob `d4a5c83ea53d`); `.github/workflows/nightly-full-gate.yml:1189` (snapshot, blob `9dab5164445a`); `.github/workflows/nightly-full-gate.yml:1202` (snapshot, blob `9dab5164445a`)

**Receipt binding:** primary report SHA-256 prefix FDD5E074D527.

## Current scope and continuation

The current decision set contains 31 criterion-specific scoped acceptances plus the separate AUD-384 false-positive retraction: **484 / 512 (94.5%) accepted or resolved, with 28 open**. The 16S / 12P / 0U / 0N complement is listed in the current reconciliation. The 478/34 and 476/36 checkpoints remain dated history. The six new scopes are limited to the explicit evidence and boundaries in the current supplement; they do not establish full behavior beyond those cases.

AUD-269's current schema/HNSW results do not establish query performance or a deployed catalog; the expanded candidate flags are not actual execution. AUD-474's synthetic browser oracle does not establish a real backend or full live stand. Git object IDs and SHA-256 public prefixes are shown as abbreviated identifiers; exact bindings remain in private evidence inputs. The package retains the existing 78 required context/app pairs, blocking CodeQL, hooks, quality thresholds, active baselines and disposition matching rules. No passing scanner, full-source check set, hosted all-green run, merge, deployment, or release readiness is claimed.
