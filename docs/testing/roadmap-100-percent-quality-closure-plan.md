# Closure Plan — Maximum Credible Test Coverage Roadmap

**Companion to:** `docs/testing/roadmap-100-percent-quality.md`
**Audit baseline commit:** `ce588bb0a1c08eb66ff2e5558349096a51d3ed4a` (the "finalize quality-roadmap" merge)
**Repository HEAD at audit time:** `0becc3e1ff130392dbc4166d04e6aa63495053bb`
**Audit date:** 2026-07-22
**Status:** execution in progress — baseline remains historical; see the uncommitted execution ledger below

## Execution ledger — 2026-07-27 (uncommitted)

This section records only independently verified results from the current closure
work. The historical measurements below remain unchanged so that the original
audit baseline is reproducible. Python reports were collected with `uv run` and
checked one file at a time after bounded test runs; no `.md` or `.diff` file is
intended for the checkpoint commit.

### Verified closures

- Python Tier0/auth, metrics/observability, cache, database, NATS, and the
  previously closed long-tail modules remain verified from the earlier
  checkpoint.
- `app/core/config/mixins/jwt_settings.py`: 133/133 statements, 48/48 branch
  pairs.
- `app/core/config/mixins/csp_settings.py`: 155/155 statements, 48/48 branch
  pairs.
- `app/api/ws/presence.py`: 159/159 statements, 50/50 branch pairs.
- `app/api/ws/connection_manager.py`: 209/209 statements, 64/64 branch pairs.
- `app/api/spotify.py`: 261/261 statements, 72/72 branch pairs.
- `app/api/notifications.py`: 297/297 statements, 90/90 branch pairs.
- `app/services/notifications/news_events.py`: 147/147 statements, 52/52
  branch pairs.
- `app/services/notification_templates.py`: 362/362 statements, 196/196
  branch pairs.
- `app/services/privacy_cleanup.py`: 91/91 statements, 4/4 branch pairs.
- `app/utils/request_coalescing.py`: 72/72 statements, 14/14 branch pairs.
- Notification model/repository and cleanup closures added during this session
  are also verified at 100% in their isolated reports.
- Go bounded verification on 2026-07-27: `go test ./... -count=1 -timeout=90s`
  passed for gateway (7 packages, 34s), ws-hub (4 packages, 9s), and
  file-processor (6 packages, 11s). Their fresh local statement profiles are
  87.9%, 81.9%, and 88.0%, respectively; these are measurements, not closure
  claims. Existing ws-hub and gateway `TestMain` goleak checks completed as
  part of the passing package runs. Local `-race` is blocked by the Windows
  environment lacking a C compiler (`go test -race` requires CGO).
- Additional Go modules `services/cmd/uni-cli` and `services/pkg/spiffe` also
  passed their bounded `go test ./...` runs.
- Frontend bounded verification: `npm run typecheck` passed and a one-worker
  Vitest smoke selection passed 24/24 tests. The full Vitest suite was not
  allowed to run unbounded on this host after its 120-second guard expired.
- Frontend property-based verification: the fast-check utility contract suite
  passed 5/5 in one worker. The scoped Stryker run mutated one pure utility file
  with 33 mutants and killed all 33 (100.00% mutation score) under
  `--concurrency 1`; generated reports remain temporary and uncommitted.
- CI wiring fixes verified by contract tests/static inspection: cross-browser
  advisory mode is now passed as an explicit reusable-workflow input (so the
  caller has no invalid job-level `continue-on-error`), the opt-in load/chaos
  job no longer uses a constant-false condition, and the GitHub Actions MinIO
  service no longer uses an unsupported `command` key. Full actionlint and
  remote CI verification remain open.
- Targeted Ruff is clean for all closure/contract test files changed in this
  session. A full `uv run ruff check tests` still reports 34 pre-existing
  findings in unrelated stress/security/tenant tests; those were not silently
  rewritten as part of this closure batch.
- Fixed a real testing-mode observability defect in
  `app/core/logging.py`: console structlog now formats positional `%s`
  arguments before event renaming. The logging regression suite passes 11/11.
- Regenerated frontend API SDK/types and MSW mocks from a freshly generated
  FastAPI OpenAPI document. The generated diff now includes `ChallengeState`,
  `MfaChallengeOut.state`, and the audit time-travel endpoint; frontend
  `npm run typecheck` passes, followed by a bounded one-worker API smoke of
  24/24 tests. Remote drift rerun remains pending.
- Fixed the Pact provider workflow's localhost service wiring by publishing
  Postgres/Redis ports; its workflow contract suite passes 14/14. A remote
  provider rerun remains pending.
- Fixed the file-processor Pact body mismatch at its source: the consumer and
  provider now declare the JSON-encoded protobuf representation as
  `application/json`, allowing Pact V4 structural matchers to run instead of
  comparing matcher documents as opaque `application/grpc` bytes. File-
  processor Go tests pass; remote Pact verification remains pending.

### Still open

The roadmap is not complete. The remaining workstreams are the frontend 99/98/98
closure plus broader Stryker/property/diff coverage beyond the verified utility
slice; Go low-coverage bootstrap and
goroutine/fuzz/integration hardening; Rust crypto/WASM fuzz+proptest+Miri and
remote coverage execution; remote Pact provider replay; browser-matrix
stabilization; Checkov/Kyverno and nightly-full-gate evidence; negative-security
and performance baselines; durable dashboard/certification evidence; and the
manual Codecov token action. The latest remote evidence also contains separate
failures in Checkov (72 findings on the historical PR merge), continuous
performance baselines, DAST, and a file-processor Pact body mismatch (fix
prepared locally); these remain actionable until a fresh remote verification. The
repository wiring for several workstreams
already exists and is locally contract-tested, but it must not be marked
complete from backend unit-coverage evidence alone or from YAML presence
without green remote runs and the roadmap's stabilization windows.

## 0. Why this document exists

An audit of `docs/testing/roadmap-100-percent-quality.md` against the real repository state found that the roadmap is **not complete**, despite its own checkboxes marking Waves 0–1 `[x]`. The final "finalize quality-roadmap" PR (#1207, merge commit `ce588bb0a`) was merged into `main` while its own **"Coverage & Quality Policy Gate"** and **"CI Success"** required jobs were reporting `failure`. This was possible because neither the classic branch-protection API nor the active GitHub ruleset (`id 8335285`) on `main` ever listed those jobs in `required_status_checks` — a governance gap, not a one-off mistake.

This document is the actionable closure plan. It is organized as phases with concrete files, functions, line/branch counts, and CI changes. Every number quoted below was measured directly, not estimated:

- Python: recomputed via `scripts/quality/normalize_coverage_reports.py` and direct XML parsing against `backend-coverage-All-Python 3.14/coverage.xml` downloaded from CI run `29842664722` (the last run that actually executed on the final merged tree).
- Go: recomputed via `go tool cover -func=coverage.out` against the three downloaded `go-coverage-services-*` artifacts from the same run.
- Rust: recomputed via `cargo llvm-cov` JSON (`rust-coverage/*/llvm.json`) from the same run.
- Frontend: recomputed via `frontend-coverage/coverage-final.json` (Istanbul/v8 format) from the same run.
- Governance: recomputed live via `gh api repos/egorribun/university_ecosystem/rulesets/8335285` and `.../branches/main/protection`.

## 1. Decisions already made (do not re-litigate these during implementation)

| Question                                                                                                                                                                                                                                     | Decision                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Governance model for a de-facto solo-maintainer repo                                                                                                                                                                                         | **Technical self-enforcement.** Add every blocking CI job to the GitHub ruleset's `required_status_checks`. Do not rely on human review discipline as the primary gate. `ownership-mapping.json`/`CODEOWNERS` become accurate documentation, not blocking review gates, because there is no second active contributor (`Semeno-v` has `write` access but 0 commits in the entire history).                                                                                                                                    |
| `quality-contract.json` floors (99%/98% Python, 99% Go statements, 100% Tier0, 100% mutation score, 100% diff coverage) vs. the honestly-lower CI floors (90% Go, 85% mutation, 80% diff-coverage) that the code comments explicitly justify | **Ratchet up to the contract values.** Do not lower the contract. This is the larger-effort path (writing real tests) but matches the roadmap's own "Definition of maximum" and avoids quietly declaring victory by rewriting the target.                                                                                                                                                                                                                                                                                     |
| Chromium-only E2E vs. the roadmap's required Firefox/WebKit/mobile-WebKit matrix                                                                                                                                                             | **Include the full matrix as its own workstream with an explicit stabilization budget** (Phase 7), landed as advisory-then-blocking, mirroring the existing `go-integration-*` advisory→blocking precedent already used in this repo.                                                                                                                                                                                                                                                                                         |
| CI gating strategy once ~15 more jobs become required                                                                                                                                                                                        | **Fast PR gate + nightly full gate on `main`.** Only bounded-duration jobs (unit tests, coverage, lint, incremental mutation) block PRs. Long-running suites (full-repo mutation score, load/chaos, the new browser shards) run nightly via `schedule: cron` + `workflow_dispatch` (the pattern already used by `weekly-cleanup.yml` and `dast.yml`) and become required for merges to `main` only after they are green for 30 days, exactly like the existing `go-integration-*` promotion criterion documented in `ci.yml`. |
| `bypass_actors: [{actor_type: RepositoryRole, actor_id: 5 (admin), bypass_mode: always}]` on the ruleset                                                                                                                                     | **Left technically unchanged** (not selected for hardening in this plan). Documented explicitly as an accepted risk for a solo-owned repository, with a _process_ rule (state the bypass reason in the PR description) rather than a technical lock — because removing admin bypass on a single-owner repo risks the owner locking themselves out with no path to override a false-positive gate.                                                                                                                             |

## Phase G — Governance and branch-protection hardening (do this first)

Rationale for going first: every other phase's "done" state can be silently unmerged again if the enforcement gap that let PR #1207 land with failing gates is not closed first.

### G.1 — Add real required status checks to the ruleset

Current `required_status_checks` on ruleset `8335285` (`main`):

```text
CI Diagnostic
Pre-commit & Linting (Read-only)
```

`ci-success` and `coverage-policy-gate` are absent, and `ci-success`'s own dependency array does **not** even reference `security-audit`'s sub-jobs correctly in a way GitHub treats as a single check name — verify actual GitHub check-run names (they can differ from job ids) before adding.

**Task G.1.1** — Enumerate the exact GitHub check-run _display names_ (not YAML job ids) for every job that must gate merges. Use `gh api repos/egorribun/university_ecosystem/commits/<sha>/check-runs` on a recent commit to get the authoritative name list, since display names come from the workflow's `name:` field, not the job key.

**Task G.1.2** — Add to `required_status_checks.required_status_checks[]` in the ruleset (via `gh api --method PUT repos/.../rulesets/8335285` or the repo Settings UI):

- `CI Success`
- `Coverage & Quality Policy Gate`
- `Source/Test Inventory & Anti-Pattern Check`
- `Backend Tests (Python 3.14) / Unit Tests (All-Python 3.14)`
- `Backend Tests (Python 3.14) / Integration Tests (All-Python 3.14)`
- `Backend Type Check`
- `Frontend Tests / Lint & Format`
- `Frontend Tests / Unit Tests`
- `Frontend Tests / Production Build`
- `Go Tests (services/gateway) / Test Go Service (services/gateway)`
- `Go Tests (services/ws-hub) / Test Go Service (services/ws-hub)`
- `Go Tests (services/file-processor) / Test Go Service (services/file-processor)`
- `Go Tests (services/cmd/uni-cli) / Test Go Service (services/cmd/uni-cli)`
- `Rust — cargo test (×3 crates) + wasm-pack + coverage`
- `Rust Lint & Format`
- `Alembic Migrations`
- `DB Migration Gate (Postgres)`
- `Helm Lint & Validate`
- `Contract Tests`
- `Schemathesis — API Schema Conformance`
- `OpenAPI Backward Compatibility Check` (from `contract-validation.yml`)
- `Verify OpenAPI Types`
- `Security Audit / Semgrep SAST`
- `Security Audit / Python Dependency Audit`
- `Security Audit / Node.js Dependency Audit`
- `Security Audit / Go Vulnerability Scan`
- `Security Audit / detect-secrets Baseline Integrity`
- `Trivy Image Scan`

**Task G.1.3** — Do **not** add these to required checks yet (they belong to Phase G.2's "full" bucket, or are already advisory by explicit repo decision documented in `ci.yml`): `mutation-tests`, `load-and-chaos-tests`, `chaos-tests`, `go-integration-ws-hub`, `go-integration-file-processor`, `go-integration-gateway`, `ws-stress-test`, `Continuous Performance Benchmarking`, `WS-Hub Go Benchmark Regression Gate`.

**Task G.1.4** — Re-verify with a throwaway PR that a deliberately-broken `coverage-policy-gate` now blocks merge (cannot be bypassed except by the documented admin override in G.3).

### G.2 — Fast/Full CI split

See Phase 14 (Ratchet sequencing table) for the authoritative ratchet floors; the fast/full job classification is described inline below. Summary of the mechanics:

**Task G.2.1** — Create `.github/workflows/nightly-full-gate.yml` with `on: schedule: cron: "0 1 * * *"` + `workflow_dispatch`, running: full-repo `mutmut run` (no time-box, no incremental diff filter) with `export_cicd_stats` actually invoked and gated at the ratcheting mutation-score floor (see Phase 14), `load-and-chaos-tests` promoted from the PR pipeline to this nightly workflow, the full Playwright browser matrix (chromium + firefox + webkit + mobile-webkit) once Phase 7 lands, `go-integration-*` full suite, `kyverno test` (Phase 8.2), Miri (Phase 5.5).

**Task G.2.2** — Add a Slack/GitHub-issue-on-failure step to `nightly-full-gate.yml` so nightly regressions are not silently ignored (there is no PR to fail against).

**Task G.2.3** — Once `nightly-full-gate.yml` is green for 30 consecutive calendar days, promote its constituent checks into the ruleset's `required_status_checks` for merges to `main` (mirrors the existing `go-integration-*` promotion criterion already written into `ci.yml`'s `ci-success` job comments).

### G.3 — Document (do not remove) the admin bypass

**Task G.3.1** — Add a `## Bypass policy` section to `AGENTS.md` (or `CONTRIBUTING.md` if one exists) stating: admin-role bypass on the `main` ruleset is intentionally left at `bypass_mode: always` because this is a single-active-maintainer repository and a hard lock risks an unrecoverable deadlock (e.g., a required check breaks due to a third-party service outage with no other admin to grant an exception). Any bypass merge must state the specific reason in the PR description or merge commit message. This is a process control, not a technical one, and is explicitly weaker than a hard block — accepted as a known, documented trade-off.

### G.4 — Fix fictitious ownership mapping

**Task G.4.1** — In `quality/ownership-mapping.json`, replace every `@backend-team`, `@frontend-team`, `@go-team`, `@rust-team`, `@devops-team`, `@platform-team`, `@security-team` value with the real, single active owner (`@egorribun`). Keep the path-prefix structure (it is still useful for the orphan/ownership checker in `scripts/quality/check_orphans_and_anti_patterns.py`), only the owner string changes.

**Task G.4.2** — In `.github/CODEOWNERS`, replace `@security-team`/`@devops-team` references with `@egorribun`. Keep `require_code_owner_review: true` in the ruleset as-is (it currently resolves to the same single person, so it adds no false safety but also no false friction).

**Task G.4.3** — Re-run `scripts/quality/generate_test_inventory.py` + `scripts/quality/check_orphans_and_anti_patterns.py` locally after G.4.1 to confirm no owner-resolution regression (the checker will now resolve every path to `@egorribun`; confirm it still passes with `Quality inventory validation passed`).

### G.5 — Codecov integration (requires a manual user action)

**Task G.5.1 (user action, cannot be automated by an agent):** Create a Codecov account/link for `egorribun/university_ecosystem`, generate a `CODECOV_TOKEN`, and add it as a GitHub Actions secret (`gh secret set CODECOV_TOKEN`).

**Task G.5.2** — Author `codecov.yml` at the repo root with per-component `flags` (`python`, `frontend`, `go-gateway`, `go-ws-hub`, `go-file-processor`, `rust-native`, `rust-pyo3-sanitizer`, `rust-wasm-sanitizer`) mapped to the same paths as `quality/quality-contract.json`'s components, `coverage.status.project` per flag with the same floors as the contract, and `comment: layout: "condensed_header, diff, flags, files"` so PRs get an automatic coverage comment.

**Task G.5.3** — Wire the missing Codecov upload step into `reusable-frontend-tests.yml` and `reusable-e2e-tests.yml` (currently only `reusable-backend-tests.yml` and `reusable-go-tests.yml` upload; Rust and combined-frontend uploads are absent).

### G.6 — Make Checkov actually block

**Task G.6.1** — Run `checkov --framework all -d .` locally once, capture the full current finding list, and either fix each real finding or add a scoped, justified `--skip-check` entry (never `soft_fail: true`) per finding ID in `.checkov.yml` (new config file) with an inline comment explaining why it's a false positive for this repo.

**Task G.6.2** — Remove `soft_fail: true` from `.github/workflows/checkov.yml` once G.6.1's baseline is clean, so future IaC regressions actually fail the job. Add this job to the Phase G.1 required-checks list once stable.

## Phase 0 — Close the Tier0 measurement gap

The roadmap's Wave 2 exit gate and the "Definition of maximum" both require 100% line/branch/function coverage and explicit negative-path tests for every Tier0 path. The current `scripts/quality/normalize_coverage_reports.py` has **zero lines referencing Tier0** — the generated `quality-manifest.json` always emits `"tier0": null`. `quality/quality-contract.json`'s `tier0.coverage` floors are consequently never actually checked against real per-file data; they exist only as a schema shape that `validate_quality_contract.py` can lint syntactically.

**Task 0.1** — Extend `normalize_coverage_reports.py` to accept the already-existing `quality/ownership-mapping.json` `tier0_rules` glob list and cross-reference it against every parsed report's per-file breakdown (Python XML, Go coverprofile per-line, Rust llvm-cov per-file, frontend LCOV per-file) to produce a `tier0` aggregate: `{lines: {covered, total, percent}, branches: {...}, functions: {...}, files: [{path, component, lines_percent, branches_percent, ...}]}`.

**Task 0.2** — Update `quality/coverage-manifest.schema.json` to make `tier0` a required, non-nullable object (currently implicitly allows `null` because nothing populates it).

**Task 0.3** — Update `validate_quality_contract.py`'s consumption in the `coverage-policy-gate` CI step (or add a new dedicated check step) to fail the job if any Tier0 file's line, branch, or function coverage is below 100% — not just the aggregate `tier0.coverage` contract floor, but per-file, matching the roadmap's literal wording ("Every Tier 0 ... path has 100% line, branch and function coverage").

**Task 0.4** — This phase has a hard dependency on Phase 2.1 (Python Tier0 file closure) landing first, or the new gate will immediately fail CI on rollout. Land Task 0.1–0.2 (measurement only, non-blocking) before Task 0.3 (enforcement).

## Phase 1 — Wave 1 remediation: activate historical-duration sharding

`tests/conftest.py` already implements a correct greedy bin-packing shard algorithm keyed off `quality/test-durations.json` (`--shard-id`/`--num-shards` pytest options), but no workflow ever passes these flags — `reusable-backend-tests.yml` only uses `pytest-xdist -n auto`.

**Task 1.1** — Decide sharding strategy: keep `xdist -n auto` for intra-shard parallelism (it is legitimately better for CPU-bound-per-worker distribution) and layer the existing `--shard-id`/`--num-shards` on top for splitting the suite across separate CI runner matrix legs (the two mechanisms are complementary, not redundant — xdist parallelizes within one runner, `--shard-id` splits across runners).

**Task 1.2** — Add a `strategy: matrix: shard: [0, 1, 2, 3]` to the `backend-tests` job in `ci.yml`, passing `--shard-id=${{ matrix.shard }} --num-shards=4` alongside the existing `-n auto`, splitting backend test wall-clock time roughly 4x.

**Task 1.3** — Regenerate `quality/test-durations.json` from the CI `pytest-report.xml` (junit timing data) after every significant test-suite change; add a small `scripts/quality/update_test_durations.py` helper that parses `pytest-report.xml` and rewrites the JSON, and call it as a post-step in `reusable-backend-tests.yml` with the output committed via a scheduled bot PR (weekly, alongside `weekly-cleanup.yml`).

## Phase 2 — Python backend coverage closure

Current measured state (component `python`): **95.54% lines (17,971/18,809), 85.92% branches (3,471/4,040)**. Contract floor: **99% lines, 98% branches**. Gap: **838 lines, 569 branches** at the aggregate level. (Note on totals: the sum of missing lines and branches across the 114 individual files in Phase 2.2 totals 1003 lines / 648 branches. This static snapshot variance occurs because Phase 2.3 branch-only files and XML condition-coverage rounding are excluded from the Phase 2.2 line-gap list, while the aggregate gap reflects the net repository deficit against contract floors. Treat per-file numbers as the authoritative work breakdown.)

### 2.1 — Tier0 files (mandatory 100%, do these before anything else in this phase)

| File                                           | Lines gap    | Branches gap |
| ---------------------------------------------- | ------------ | ------------ |
| `app/services/auth/lockout.py`                 | 12 (134/146) | 11 (33/44)   |
| `app/services/auth/graphql_token_validator.py` | 4 (69/73)    | 3 (15/18)    |
| `app/services/auth/login_session_manager.py`   | 2 (71/73)    | 0 (8/8)      |
| `app/auth/security.py`                         | 2 (232/234)  | 1 (61/62)    |
| `app/api/auth/login.py`                        | 1 (118/119)  | —            |

For each: read the file, identify the exact uncovered lines via `coverage report --show-missing` (or open `coverage.xml`'s `<line number=... hits="0">` entries), write behavior-level tests through the public service/API surface (per the roadmap's "Replace coverage boosters that only call internals with behavioural tests" instruction — do not add trivial internal-call tests here, these are Tier0 auth paths and need real negative-path assertions: expired/malformed tokens, lockout threshold boundaries, concurrent login-session races).

### 2.2 — Non-Tier0 line-coverage closure, ordered by total missing (lines + branches) descending

Work through this list top-to-bottom; it is already sorted so the highest-leverage files come first. Each row is `path — lines missing / branches missing`.

1. `app/core/metrics.py` — 38 / 63
2. `app/core/observability.py` — 59 / 32
3. `app/deps/cache.py` — 40 / 27
4. `app/api/ws/presence.py` — 35 / 20
5. `app/core/config/notifications.py` — 32 / 20
6. `app/api/ws/connection_manager.py` — 22 / 25
7. `app/api/spotify.py` — 29 / 17
8. `app/api/notifications.py` — 29 / 15
9. `app/api/events.py` — 30 / 11
10. `app/api/users.py` — 32 / 7
11. `app/services/notifications/news_events.py` — 16 / 23
12. `app/core/nats_broker.py` — 25 / 13
13. `app/api/news.py` — 20 / 17
14. `app/core/config/base.py` — 22 / 15
15. `app/repositories/chat_repository.py` — 24 / 10
16. `app/schemas/schemas.py` — 19 / 14
17. `app/core/events.py` — 20 / 7
18. `app/api/health.py` — 22 / 4
19. `app/core/localization/core.py` — 15 / 8
20. `app/api/stats.py` — 17 / 5
21. `app/services/partition_manager.py` — 16 / 6
22. `app/services/notifications/schedule_reminders.py` — 9 / 13
23. `app/schemas/notifications.py` — 11 / 10
24. `app/api/sessions.py` — 12 / 8
25. `app/core/database.py` — 8 / 12
26. `app/core/config/mixins/jwt_settings.py` — 13 / 7
27. `app/models/users.py` — 12 / 8
28. `app/repositories/user_repository.py` — 13 / 7
29. `app/routers/notifications.py` — 9 / 11
30. `app/api/schedule.py` — 16 / 2
31. `app/core/container.py` — 18 / 0
32. `app/core/config/cache.py` — 12 / 5
33. `app/services/chat/creation_service.py` — 9 / 8
34. `app/core/config/database.py` — 12 / 3
35. `app/api/deps/auth.py` — 9 / 5
36. `app/api/internal/csp_report.py` — 10 / 4
37. `app/core/cache.py` — 8 / 6
38. `app/services/stats_cache.py` — 6 / 8
39. `app/core/ssrf.py` — 9 / 4
40. `app/repositories/news_repository.py` — 9 / 4
41. `app/services/nats_messaging.py` — 6 / 7
42. `app/services/user/profile_service.py` — 8 / 5
43. `app/services/event_handlers.py` — 8 / 4
44. `app/services/notifications/delivery.py` — 4 / 8
45. `app/repositories/schedule_repository.py` — 7 / 4
46. `app/services/audit_service.py` — 4 / 7
47. `app/services/image_proxy.py` — 9 / 2
48. `app/utils/files.py` — 5 / 6
49. `app/api/stories.py` — 8 / 1
50. `app/cli/migrate_passwords.py` — 4 / 5
51. `app/core/config/mixins/cors_settings.py` — 4 / 5
52. `app/services/file_scanner.py` — 5 / 4
53. `app/services/notification_queue.py` — 8 / 1
54. `app/services/schedule_service.py` — 6 / 3
55. `app/core/localization/formatting.py` — 2 / 6
56. `app/management/weekly_cleanup.py` — 4 / 4
57. `app/models/user_loaders.py` — 5 / 3
58. `app/scripts/backfill_uuids.py` — 5 / 3
59. `app/services/event_service.py` — 3 / 5
60. `app/api/images.py` — 3 / 4
61. `app/core/config/mixins/csp_settings.py` — 2 / 5
62. `app/core/middleware/content_size.py` — 4 / 3
63. `app/cqrs/queries.py` — 2 / 5
64. `app/management/normalize_static.py` — 4 / 3
65. `app/models/stories.py` — 3 / 4
66. `app/utils/migrations.py` — 6 / 1
67. `app/api/ws/authenticator.py` — 4 / 2
68. `app/cli/db.py` — 4 / 2
69. `app/models/auth.py` — 4 / 2
70. `app/services/notification_service.py` — 6 / 0
71. `app/services/notifications_retention.py` — 5 / 1
72. `app/services/chat/attachment_service.py` — 3 / 3
73. `app/services/user/media_service.py` — 3 / 3
74. `app/utils/request_coalescing.py` — 2 / 4
75. `app/core/event_decorators.py` — 2 / 3
76. `app/core/feature_flags.py` — 4 / 1
77. `app/core/internal_access.py` — 3 / 2
78. `app/services/notification_templates.py` — 1 / 4
79. `app/services/privacy_cleanup.py` — 4 / 1
80. `app/services/user_service.py` — 5 / 0
81. `app/services/user/compliance_service.py` — 2 / 3
82. `app/services/user/logic.py` — 2 / 3
83. `app/api/admin/audit.py` — 2 / 2
84. `app/core/cache_versioning.py` — 4 / 0
85. `app/core/config/app_gen.py` — 2 / 2
86. `app/services/cache_warmup.py` — 2 / 2
87. `app/services/ical.py` — 2 / 2
88. `app/main.py` — 2 / 1
89. `app/api/websocket.py` — 3 / 0
90. `app/cli/infra.py` — 3 / 0
91. `app/core/task_registry.py` — 2 / 1
92. `app/core/middleware/request_id.py` — 2 / 1
93. `app/services/data_access.py` — 2 / 1
94. `app/services/geolocation.py` — 1 / 2
95. `app/api/ws/ticket.py` — 2 / 0
96. `app/core/health.py` — 1 / 1
97. `app/core/spicedb_watch.py` — 1 / 1
98. `app/core/config/security.py` — 1 / 1
99. `app/core/config/storage.py` — 1 / 1
100. `app/core/di/spicedb.py` — 1 / 1
101. `app/core/policies/csp.py` — 1 / 1
102. `app/models/notifications.py` — 2 / 0
103. `app/repositories/active_session_repository.py` — 2 / 0
104. `app/repositories/user_stats_repository.py` — 2 / 0
105. `app/services/fraud_detection_service.py` — 1 / 1
106. `app/services/story_cleanup.py` — 2 / 0
107. `app/services/auth/login_session_manager.py` (branches only, already listed in 2.1 for lines) — see 2.1
108. `app/services/notifications/cleanup.py` — 1 / 1
109. `app/workers/outbox.py` — 2 / 0
110. `app/api/dlq.py` — 1 / 0
111. `app/repositories/audit_repository.py` — 1 / 0
112. `app/services/email_change_cleanup.py` — 1 / 0
113. `app/services/mfa_challenge_cleanup.py` — 1 / 0
114. `app/services/password_reset_cleanup.py` — 1 / 0
115. `app/services/push_service.py` — 1 / 0
116. `app/services/geolocation.py` (duplicate entry, see 94)

### 2.3 — Branch-only closure (files already at 100% lines, branches still short)

These files need only new _branch_ conditions covered (e.g., an `if/else` arm, an exception path, a default-parameter fallback), not new lines — typically 1-3 targeted test cases each:

`app/core/protocols.py` (16 branches), `app/services/chat/command_service.py` (10), `app/services/auth_service.py` (6), `app/api/validation.py` (4), `app/repositories/base.py` (4), `app/openapi.py` (3), `app/core/circuit_breaker.py` (3), `app/core/config/__init__.py` (3), `app/services/notifications/core.py` (3), `app/core/event_retry.py` (2), `app/core/security_headers.py` (2), `app/core/spicedb.py` (2), `app/repositories/health_repository.py` (2), `app/services/news_service.py` (2), `app/services/story_service.py` (2), `app/services/auth/fingerprint_service.py` (2), and 19 additional files with exactly 1 missing branch each (`app/api/ws/serializers.py`, `app/auth/rbac.py`, `app/auth/handlers/logout.py`, `app/core/event_dlq.py`, `app/core/event_registry.py`, `app/core/middleware/response_hardening.py`, `app/core/middleware/setup.py`, `app/cqrs/bus.py`, `app/graphql/schema.py`, `app/management/reset_mfa.py`, `app/routers/schedule.py`, `app/services/minio_storage.py`, `app/services/push_topics.py`, `app/services/ws_hub_client.py`, `app/services/user/analytics_service.py`, `app/services/user/stats_service.py`, `app/utils/pagination.py`, `app/workers/notifications.py`, `app/core/ratelimit/circuit_breaker.py`).

### 2.4 — Replace mock-only "disposable" integration cells with real containers

The roadmap requires "disposable PostgreSQL, Valkey, NATS, MinIO and SpiceDB integration cells." Postgres/Valkey/NATS already use real containers (via `tests/conftest.py`'s `testcontainers.postgres.PostgresContainer` pattern and the `docker-compose`-backed integration test services). MinIO and SpiceDB do not.

**Task 2.4.1** — Add a `testcontainers.minio.MinioContainer` (or equivalent generic container wrapper if the official module lacks one) fixture to `tests/conftest.py`, gated the same way as the existing Postgres container (`USE_TESTCONTAINERS_MINIO=1` env var, falling back to mocks only when unset — do not remove the existing mock-based unit tests in `tests/test_minio_storage_coverage.py`, they remain valid as fast unit tests; add a new `tests/integration/test_minio_integration.py` for the container-backed cell).

**Task 2.4.2** — Add a disposable SpiceDB container (official `authzed/spicedb` image supports an in-memory `--datastore-engine=memory` flag for exactly this use case) fixture, and a new `tests/integration/test_spicedb_integration.py` exercising real ReBAC permission checks (not mocked `core/spicedb.py` calls) — schema load, relationship write, permission check, permission revoke, and negative "denied" assertions.

**Task 2.4.3** — Update `tests/chaos/test_minio_chaos.py` to run its failure-injection scenarios (S3Error, timeout) against the real container via network fault injection (reuse the existing ToxiProxy setup already present for other chaos tests — see `docker-compose.infra.yml`) instead of `unittest.mock.MagicMock`.

### 2.5 — Hypothesis stateful testing

The roadmap requires "Hypothesis/Schemathesis **stateful**/property tests." Current `tests/test_property_based.py` and `tests/test_pydantic_routes_hypothesis.py` use `@given`/`strategies` but zero `RuleBasedStateMachine` usage.

**Task 2.5.1** — Add a `RuleBasedStateMachine` in `tests/test_property_based.py` (or a new `tests/test_stateful_ratelimit.py`) modeling the rate limiter / circuit breaker (`app/core/circuit_breaker.py`, referenced by Tier0 rules) state transitions: `record_success`, `record_failure`, `is_open`, `half_open_probe` as rules, with invariants asserting the breaker never allows requests through while genuinely open and always resets after the cooldown window.

**Task 2.5.2** — Add a second `RuleBasedStateMachine` modeling session/login lockout lifecycle (`app/services/auth/lockout.py`) — `record_failed_attempt`, `record_successful_login`, `is_locked`, `time_advance` as rules, with an invariant asserting the account is never lockable below the configured threshold and never permanently locked past the configured window.

### 2.6 — Mutation testing gate rework

Current state: `scripts/mutmut_ci_gate.py` hardcodes `--min-score 85.0`, `mutation-tests` in `ci.yml` is incremental (only files changed vs. `origin/main`), time-boxed at 20 minutes with **silent score-verification skip** if the time-box is hit (`ec -eq 124` branch), and the job is **advisory** — not in `ci-success`'s blocking `results[]` array. This contradicts the roadmap's "Mutation testing kills 100% of viable mutants" and Wave 10's "Enable strict ... mutation gates in the required PR matrix."

**Task 2.6.1** — Split mutation testing into two jobs:

- **`mutation-tests-incremental`** (PR-blocking, fast gate): keep the diff-only scope, but change the timeout handling so a time-box hit **fails** the job instead of silently skipping score verification (raise the time-box to 25 minutes to reduce false failures first, and shard the changed-module list across parallel matrix legs if a single PR's diff is large enough to still risk timing out).
- **`mutation-tests-full`** (nightly, `nightly-full-gate.yml`): run `mutmut run` across the entire `app/` tree with `also_copy = ["infrastructure", "alembic", "docker-compose.full.yml"]` added to `[tool.mutmut]` in `pyproject.toml` so the three currently-excluded infra-contract tests (`test_migrations_runtime.py`, `test_wave173_caddy_routing.py`, `test_wave173_ws_hub_env.py`) can be re-included, and explicitly call `mutmut run --CI` followed by the score-export step the current job never calls, gated at the ratcheting floor in Phase 14.

**Task 2.6.2** — Build an equivalent-mutant registry (`quality/mutation-exclusions.json`), matching the same schema discipline as `quality/quality-contract.json`'s `exclusions`/`quarantines` (id, path, reason, owner, issue, evidence, created_on, expires_on) so genuinely-equivalent mutants (e.g., logging statement text changes) can be recorded without silently lowering the denominator — per the roadmap's explicit requirement.

**Task 2.6.3** — Once `mutation-tests-incremental` is stable for 30 days, add it to the Phase G.1 required-checks list.

### 2.7 — diff-cover floor

**Task 2.7.1** — In `reusable-backend-tests.yml`, change `uv run diff-cover coverage.xml --compare-branch=origin/$compareBranch --fail-under=80` to `--fail-under=100`, but land this **last**, after Phase 2.2's backlog is materially reduced — otherwise every future PR touching a still-uncovered legacy file will be blocked on unrelated legacy debt. Sequence: raise to 90 once 2.2 items 1–60 are closed, then 100 once 2.2 is fully closed.

## Phase 3 — Frontend coverage closure

Current measured state (component `frontend`): **91.81% lines, 82.12% branches, 82.21% functions** — all three already clear the contract floor (91/82/82). The remaining gap is not about hitting the contract minimum; it is about hitting the roadmap's actual stated target of "at least 99% line/statement coverage" for handwritten production components (the `frontend` component's contract floor of 91/82/82 is itself a placeholder floor below the roadmap's stated 99%/98% "maximum" language — this is flagged in Phase 14's ratchet table).

Raw counts across the whole `src/`: **4,056 missing statements, 1,955 missing branches, 388 missing functions** across 537 files with any gap.

### 3.1 — Highest-leverage files (top 60 by total missing units, descending)

Each row: `path — missing statements / missing branches / missing functions`.

1. `src/hooks/auth/useProfileSync.ts` — 252 / 48 / 6
2. `src/push/subscribe.ts` — 129 / 78 / 0
3. `src/pages/StoriesAdmin.tsx` — 144 / 27 / 13
4. `src/pages/Profile.tsx` — 107 / 26 / 14
5. `src/components/map/WeatherParticles.tsx` — 128 / 3 / 10
6. `src/pages/settings/hooks/useWebAuthn.ts` — 91 / 2 / 2
7. `src/hooks/useChatWebSocket.ts` — 69 / 23 / 1
8. `src/api/client.ts` — 48 / 27 / 7
9. `src/pages/Schedule.tsx` — 58 / 15 / 4
10. `src/pages/Register.tsx` — 41 / 23 / 9
11. `src/components/auth/MfaChallengeView.tsx` — 59 / 3 / 6
12. `src/components/profile/NowPlayingCard.tsx` — 36 / 28 / 3
13. `src/pages/NewsDetail.tsx` — 42 / 8 / 14
14. `src/components/pwa/InstallPrompt.tsx` — 47 / 13 / 1
15. `src/pages/settings/hooks/useSessionManagement.ts` — 50 / 7 / 4
16. `src/components/messenger/ChatWindow.tsx` — 25 / 33 / 1
17. `src/components/news/NewsCardEditDialog.tsx` — 36 / 20 / 2
18. `src/pages/EventDetail.tsx` — 37 / 11 / 10
19. `src/pages/settings/hooks/useTotpEnrollment.ts` — 44 / 13 / 1
20. `src/hooks/useNowPlaying.ts` — 29 / 21 / 5
21. `src/components/dashboard/ScheduleCard.tsx` — 34 / 17 / 2
22. `src/pages/settings/hooks/useDndSettings.ts` — 29 / 22 / 0
23. `src/components/messenger/NewChatModal.tsx` — 34 / 12 / 3
24. `src/features/news/components/NewsFormDialog.tsx` — 21 / 27 / 1
25. `src/hooks/features/useMessengerController.ts` — 19 / 30 / 0
26. `src/contexts/MessengerContext.tsx` — 33 / 14 / 1
27. `src/pages/settings/SettingsSecurity.tsx` — 40 / 6 / 2
28. `src/components/stories/StoryViewer.tsx` — 28 / 19 / 0
29. `src/features/events/components/EventsHeader.tsx` — 33 / 11 / 3
30. `src/components/messenger/ChatArea.tsx` — 13 / 27 / 6
31. `src/components/map/MapLibreMap.tsx` — 30 / 7 / 7
32. `src/components/map/MapSearchBar.tsx` — 29 / 11 / 3
33. `src/components/settings/ui/Layout.tsx` — 35 / 6 / 2
34. `src/contexts/AppShellContext.tsx` — 19 / 23 / 1
35. `src/hooks/auth/useLoginFlow.ts` — 39 / 3 / 0
36. `src/api/interceptors/rateLimit.ts` — 31 / 10 / 0
37. `src/components/schedule/ScheduleMobileView.tsx` — 26 / 12 / 3
38. `src/components/dashboard/WeatherAmbient.tsx` — 35 / 4 / 0
39. `src/components/events/EventDetailEditDialog.tsx` — 24 / 14 / 1
40. `src/components/mfa/OtpEntry.tsx` — 31 / 8 / 0
41. `src/components/schedule/DayColumn.tsx` — 29 / 9 / 1
42. `src/components/search/SearchDialog.tsx` — 21 / 15 / 3
43. `src/pages/ResetPassword.tsx` — 18 / 19 / 2
44. `src/pages/Settings.tsx` — 33 / 4 / 2
45. `src/components/events/EventEditDialog.tsx` — 16 / 12 / 10
46. `src/components/news/NewsDetailHero.tsx` — 32 / 4 / 2
47. `src/pages/ForgotPassword.tsx` — 28 / 8 / 2
48. `src/sw/api.ts` — 37 / 0 / 1
49. `src/components/schedule/ScheduleListView.tsx` — 22 / 12 / 2
50. `src/pages/settings/hooks/usePasswordChange.ts` — 30 / 6 / 0
51. `src/components/events/EventFileManager.tsx` — 31 / 4 / 0
52. `src/components/motion/PageFadeIn.tsx` — 27 / 6 / 2
53. `src/components/motion/ScrollReveal.tsx` — 28 / 6 / 1
54. `src/pages/Dashboard.tsx` — 19 / 14 / 2
55. `src/pages/settings/hooks/useEmailChange.ts` — 28 / 7 / 0
56. `src/AppProviders.tsx` — 31 / 1 / 2
57. `src/components/events/EventDetailBody.tsx` — 34 / 0 / 0
58. `src/features/admin/AdminAuditFeature.tsx` — 15 / 15 / 3
59. `src/utils/trustedTypes.ts` — 20 / 10 / 3
60. `src/components/mfa/StepUpDialog.tsx` — 19 / 12 / 0

For each: write user-facing Testing Library interactions (per the roadmap's Wave 3.3 instruction) covering the missing branches — these are overwhelmingly error/loading/empty/permission-denied/reconnect paths in hooks and dialogs, not dead code. `src/push/subscribe.ts` and `src/hooks/useChatWebSocket.ts` specifically need WebSocket reconnection and push-subscription-failure branch coverage (roadmap Wave 3.2's explicit "WebSocket reconnection" requirement). `src/sw/api.ts` needs PWA/service-worker branch coverage (Wave 3.2's "PWA/service worker" requirement).

### 3.2 — Long-tail cleanup (files 61–537)

477 files, aggregate 2,764 missing units (1,483 statements / 1,079 branches / 202 functions), each individually small (1–15 missing units). Do not itemize these; track as a single running backlog task with a burn-down chart in the Phase 10 dashboard. Suggested execution rule: whenever any of these files is touched for an unrelated feature/bugfix PR, its diff-coverage requirement (Phase 3.5 below) will force it toward 100% incidentally — supplement with a dedicated monthly "coverage debt" sweep of 10–15 files from this list until exhausted.

### 3.3 — Frontend mutation testing (currently absent entirely)

**Task 3.3.1** — Add `@stryker-mutator/core` + `@stryker-mutator/vitest-runner` to `frontend/package.json` devDependencies.

**Task 3.3.2** — Author `frontend/stryker.config.mjs` scoped initially to pure utility modules with no DOM/React dependency: `src/utils/*.ts`, `src/i18n/formatters.ts`, validation schemas (Valibot-based files under `src/schemas/` if present, or equivalent), and pure reducers/state-machine hooks (`src/hooks/features/useMessengerController.ts`'s reducer logic if extractable).

**Task 3.3.3** — Add a `stryker-incremental` job to the fast PR gate (diff-scoped, same pattern as Python's `mutation-tests-incremental`) and a `stryker-full` job to `nightly-full-gate.yml`, both gated at the Phase 14 ratchet floor.

### 3.4 — Frontend property-based testing (currently absent entirely)

**Task 3.4.1** — Add `fast-check` to `frontend/package.json` devDependencies.

**Task 3.4.2** — Add property tests for: URL-state serialization/deserialization (`src/router.ts`'s search-param helpers), date/i18n formatters (`src/i18n/formatters.ts`), and any hand-rolled parsers (`src/utils/sanitize.ts`, `src/utils/sanitizeArticleHtml.ts` — round-trip and idempotency properties: sanitizing already-sanitized output must be a no-op, matching the existing `strip_html` idempotency fix referenced in git history).

### 3.5 — Frontend diff-coverage tooling (currently absent entirely)

**Task 3.5.1** — Add a `diff-cover frontend/coverage/lcov.info --compare-branch=origin/main --fail-under=<ratchet floor>` step to `reusable-frontend-tests.yml`, mirroring the Python setup in `reusable-backend-tests.yml`. `diff-cover` supports LCOV input natively, so no additional tooling is needed beyond the existing `uv`-managed Python environment (it is a Python package, already available via the backend's `uv` toolchain, callable from the frontend job with a `uv run` prefix or a dedicated `pip install diff-cover` step if frontend jobs don't have `uv` set up).

## Phase 4 — Go services coverage and hardening

Current measured state: `go-gateway` **92.56% statements**, `go-ws-hub` **91.70%**, `go-file-processor` **90.74%**. Contract floor: **99%**. CI's honest current floor: **90%** (explicitly documented in `ci.yml`'s matrix comments as "measured unit-only reality").

### 4.1 — Lowest-covered functions by service (target for new table-driven/fuzz tests)

**gateway** (`services/gateway`):

- `cmd/gateway/main.go:151 setupRouter` — 75.0%
- `cmd/gateway/main.go:128 initGRPC` — 80.0%
- `middleware/auth.go:766 Optional` — 80.9%
- `cmd/gateway/main.go:109 initSentry` / `cmd/gateway/main.go:349 initTracer` — 85.7% each
- `cmd/gateway/main.go:47 main` — 86.4%
- `middleware/ratelimit.go:42 NewRateLimiter` — 90.0%
- `middleware/auth.go:448 listenOnce` — 90.0%
- `middleware/auth.go:478 shouldRefreshProbabilistic` — 87.5%
- `middleware/auth.go:256 fetchJWKSPublicKey` — 91.7%
- `middleware/auth.go:540 verifySession` — 92.9%
- `middleware/auth.go:656 Validate` — 92.3%

**ws-hub** (`services/ws-hub`):

- `pkg/hub/hub.go:376 SubscribeToNATS` — **59.1%** (lowest in the entire Go codebase — prioritize first)
- `pkg/hub/client.go:233 WritePump` — 76.2%
- `pkg/hub/client.go:77 ReadPump` / `pkg/hub/client.go:135 handleIncomingMessage` — 83.3% each
- `pkg/hub/auth_client.go:75 NewInternalAPIAuthClient` — 83.3%
- `pkg/hub/hub.go:518 handleCacheInvalidation` — 83.9%
- `internal/telemetry/telemetry.go:36 InitTracer` — 81.8%
- `main.go:24 main` / `main.go:114 setupHub` — 84.6% each
- `pkg/hub/client.go:179 handleMessage` — 84.2%
- `pkg/hub/hub.go:309 broadcastMessage` — 88.5%
- `pkg/hub/handlers.go:293 tryForceRefreshJWKS` — 88.9%
- `main.go:136 setupHandlers` — 88.2%

**file-processor** (`services/file-processor`):

- `cmd/file-processor/main.go:255 startNatsSubscriber` — **44.4%** (lowest in the entire Go codebase — prioritize first)
- `internal/workflow/workflow.go:311 encodeImage` — 71.4%
- `internal/workflow/workflow.go:258 downloadAndDecodeImage` — 80.8%
- `cmd/file-processor/main.go:235 setupTemporalWorker` — 83.3%
- `cmd/file-processor/main.go:430 runServers` — 85.0%
- `cmd/file-processor/main.go:604 initTracer` — 85.7%
- `cmd/file-processor/main.go:78 runMain` — 88.2%

For the `main.go`/bootstrap-heavy functions (`setupRouter`, `initGRPC`, `startNatsSubscriber`, `setupTemporalWorker`), prefer **`go-integration-*` tests against real testcontainers** (they are already advisory-running against `testcontainers-go` per ADR-022) over unit mocks — this is genuinely hard-to-unit-test bootstrap wiring, and the roadmap's own integration-cell requirement fits this code better than forcing artificial unit coverage.

### 4.2 — goleak

**Task 4.2.1** — Add `go.uber.org/goleak` as a dependency to all three `services/*/go.mod`.

**Task 4.2.2** — Add a `TestMain(m *testing.M) { goleak.VerifyTestMain(m) }` to one `_test.go` file per package in each service (standard goleak entry-point pattern), starting with `services/ws-hub/pkg/hub` (the package with the most goroutine-heavy code: `SubscribeToNATS`, `ReadPump`/`WritePump`, `StartLimiterCleanup`) and `services/gateway/middleware` (JWKS refresher goroutine in `StartJWKSRefresher`/`listenOnce`).

### 4.3 — Fuzz coverage gaps

**Task 4.3.1** — Add `services/gateway/middleware/auth_fuzz_test.go`'s existing but never-executed `FuzzJWTValidation` to a CI step — either extend `.github/workflows/go-fuzz.yml` with a second job for gateway, or add it to `ci.yml`'s existing `go-fuzz` job as a third `go test -fuzz=` invocation alongside the two ws-hub fuzz targets.

### 4.4 — Integration tests: advisory → blocking

**Task 4.4.1** — Track `go-integration-ws-hub`, `go-integration-file-processor`, `go-integration-gateway` flake rate for 30 days (the criterion already documented in `ci.yml`'s `ci-success` comments). Once below 1%, move them from the "reported but not blocking" section of `ci-success` into the blocking `results[]` array and into the Phase G.1 ruleset required-checks list.

### 4.5 — Coverage ratchet

**Task 4.5.1** — Raise `coverage-threshold` in `ci.yml`'s Go test matrix from 90 to 95 once Phase 4.1's lowest-covered functions (SubscribeToNATS, startNatsSubscriber, and the `main.go` bootstrap functions) are addressed via 7.1's integration-test approach; raise to 99 once fully closed. See Phase 14 for the exact sequencing.

## Phase 5 — Rust, PyO3, and browser WASM

Current measured state: `rust-native` **88.53% lines (571/645), 80.0% functions (56/70)** — the only failing Rust component. `rust-pyo3-sanitizer` (99.37%/100%) and `rust-wasm-sanitizer` (100%/100%) already pass.

### 5.1 — `native/rust_ext/src/lib.rs` closure

This is the **only file** in the entire native Rust surface below target — 74 missing lines, 14 missing functions, all concentrated in one file.

**Task 5.1.1** — Run `cargo llvm-cov --html` locally on `native/rust_ext` to get the exact uncovered line ranges (the aggregate JSON used for this audit does not carry per-line detail; only per-file summaries were extracted). Cross-reference against the existing `proptest`/fuzz targets in `native/rust_ext/fuzz/fuzz_targets/` to identify which of the 14 uncovered functions are FFI error-mapping paths (per the roadmap's "FFI error mapping" requirement) versus pure-Rust internal logic, and prioritize FFI error paths first since those are the ones with an explicit roadmap callout.

### 5.2 — Track `rust-crypto` as a real contract component

Currently `frontend/rust-crypto` has tests (`tests/native.rs`, `tests/wasm.rs`) but is **absent from `quality/quality-contract.json`'s `components` map** and from `normalize_coverage_reports.py`'s `--rust-report` CLI options — meaning its coverage is never measured or gated at all, despite the roadmap's Wave 5 intro explicitly naming it alongside `rust_ext`, `pyo3-sanitizer`, and `wasm-sanitizer`.

**Task 5.2.1** — Add `rust-crypto` to `quality/quality-contract.json`'s `components` (coverage floors matching the other Rust components: 99 lines / 98 functions) and to `quality/coverage-manifest.schema.json`'s `componentName` enum.

**Task 5.2.2** — Add a `--rust-report rust-crypto=artifacts/coverage/rust/rust-crypto/llvm.json` invocation to the `coverage-policy-gate` job in `ci.yml`, and a corresponding `cargo llvm-cov` step in `rust-lint`/a new dedicated coverage job for `frontend/rust-crypto`.

### 5.3 — Fuzz coverage for the two crates currently without it

**Task 5.3.1** — Add `fuzz/fuzz_targets/` to `frontend/wasm-sanitizer` (currently only `native/rust_ext` and `crates/pyo3-sanitizer` have fuzz harnesses) targeting the sanitization entry points exposed to browser WASM bindings, with malformed-byte and boundary-size inputs per the roadmap's explicit Wave 5.3 wording.

**Task 5.3.2** — Add `fuzz/fuzz_targets/` to `frontend/rust-crypto` targeting HMAC/crypto primitive boundaries (empty input, maximum-length input, non-UTF8 byte sequences).

**Task 5.3.3** — Add both new fuzz targets to `.github/workflows/rust-fuzz.yml`'s job matrix.

### 5.4 — proptest for the two crates currently without it

**Task 5.4.1** — Add `proptest` as a dev-dependency to `frontend/wasm-sanitizer/Cargo.toml` and `frontend/rust-crypto/Cargo.toml` (currently only `native/rust_ext` and `crates/pyo3-sanitizer` use it), with properties covering round-trip encode/decode invariants and idempotency of sanitization.

### 5.5 — Miri (currently entirely absent from CI)

**Task 5.5.1** — Add a new `.github/workflows/rust-miri.yml` (or a job within `nightly-full-gate.yml`) running `cargo +nightly miri test` for `crates/pyo3-sanitizer` and `frontend/rust-crypto` (pure-Rust logic without heavy FFI/syscall dependencies — Miri cannot interpret PyO3's C-API calls or WASM host bindings, so scope it explicitly to the subset of each crate's test suite that exercises pure Rust logic, documented via a `#[cfg(not(miri))]` skip list for the FFI-heavy tests, matching the roadmap's own "Miri or sanitizer cells where platform support permits" qualifier).

## Phase 6 — Contracts, schemas, and compatibility

Current state: exactly one Pact contract exists (`tests/contracts/pacts/ws-hub-university-backend.json`, 1 interaction, consumer-side only via the `contract-tests` CI job's `-k "not integration"` pytest filter). No provider-side verification job exists.

**Task 6.1** — Add a `pact-provider-verify` CI job that runs the backend as the provider and replays the existing ws-hub consumer pact against it (using `pact-python`'s verifier, already compatible with the existing `PACT_DO_NOT_TRACK` env var setup in `contract-tests`).

**Task 6.2** — Author new consumer pacts for the two other cross-process boundaries currently covered only by hand-written schema-assertion tests (`tests/contracts/test_gateway_rest_contract.py`, `tests/contracts/test_file_processor_grpc_contract.py`) — convert or supplement these with real Pact consumer definitions so they participate in the same provider-verification replay mechanism as the ws-hub contract, per the roadmap's "consumer-driven provider verification and contract replay in both producer and consumer jobs" requirement.

**Task 6.3** — Add explicit backward/forward payload-migration tests for at least one enum that has evolved historically (search `alembic/versions/` for any migration that added an enum value) — a round-trip test asserting an old-shape persisted payload still deserializes correctly under the current schema.

## Phase 7 — Full browser matrix (advisory → blocking, dedicated stabilization budget)

Current state: `playwright.config.ts` declares `chromium`, `firefox`, `webkit`, `mobile-webkit` projects, but every CI workflow (`reusable-e2e-tests.yml`'s caller in `ci.yml`) only ever passes `browser: chromium`. The `ci.yml` comment explicitly states "Chromium-only by design."

**Task 7.1** — Add `firefox`, `webkit`, `mobile-webkit` as additional `browser` matrix values in `ci.yml`'s `e2e-tests` job, but land them first as a **separate, non-blocking job** (`e2e-tests-cross-browser`, `continue-on-error: true`, not in `ci-success`'s blocking array) so failures are visible without blocking merges during stabilization.

**Task 7.2** — Triage failures per browser. WebKit historically has known flakiness classes in this ecosystem (memory/OOM behavior under CI runners, timing differences in animation-heavy tests) — budget for: adjusting `testTimeout`/expect-timeout values per-browser via Playwright's `use: { ...devices[...] }` overrides, auditing the `reduced-motion` test helpers (already present in 19 test files) for WebKit-specific gaps, and re-running the existing `visual-regression.spec.ts`/`visual.spec.ts` baselines per-browser (Chromatic baselines are Chromium-only today; decide whether to extend Chromatic multi-browser or keep visual regression Chromium-only while functional E2E goes cross-browser).

**Task 7.3** — Once `e2e-tests-cross-browser` is green for 30 consecutive days across all three new browsers, split it into per-browser required jobs and add them to the Phase G.1 ruleset required-checks list, retiring the "Chromium-only by design" comment in `ci.yml`.

**Task 7.4** — Add Cache-Control header assertions to the SSR-focused E2E specs (`hydration.spec.ts` and/or a new `ssr-caching.spec.ts`) asserting the production preview server (`npm run build && npm run preview`, already the existing `webServer` config) emits expected cache headers for static assets vs. the SSR HTML shell — this specific gap (no header assertions anywhere in `tests/e2e/`) is independent of the browser-matrix work and can land immediately without waiting for Task 7.1–10.3.

## Phase 8 — Data, deployment, and infrastructure

**Task 8.1** — Checkov `soft_fail` removal: see Phase G.6 above (already scheduled there; cross-referenced here for Wave 8 traceability).

**Task 8.2** — Add a `kyverno-test` CI job. Kyverno ships a native `kyverno test` CLI subcommand for exactly this purpose (policy unit testing without a live cluster) — author `k8s/kyverno/tests/` with at least one positive and one negative test case per policy in `k8s/kyverno/cluster-policies.yaml`, and wire `kyverno test k8s/kyverno/tests/` into a new job in `ci.yml`.

**Task 8.3** — `load-and-chaos-tests` advisory → blocking: this job's blocker is the production Temporal container failing to boot reliably in CI (`W144`-class issue per the existing `ci-success` comment). Track root cause separately (likely a Temporal server config/entrypoint issue specific to the CI environment, not a test-quality issue) and move to `nightly-full-gate.yml` in the interim per Phase G.2, revisiting blocking-promotion once the Temporal boot issue has a documented fix.

## Phase 9 — Non-functional, security, and resilience

**Task 9.1** — Expand the abuse/negative-security test suite beyond the existing RLS/tenant-isolation coverage (`tests/integration/test_rls_matrix.py`, `test_rls_messages.py` — 10 tests total today) with explicit scenarios for: privilege escalation (attempt to elevate role via a manipulated JWT claim or a repository-layer bypass), replay-attack resistance (reused nonce/CSRF token, reused WebSocket ticket), and cache-poisoning (crafted cache key collision across tenants in `app/deps/cache.py` / `app/core/cache_versioning.py`, which are both already flagged as coverage-gap files in Phase 2.2 — combine the new negative-security tests with that closure work rather than treating them as separate effort).

**Task 9.2** — Add a documented, statistically-stable performance regression baseline for the native optimizer (`native/rust_ext`) and the WebSocket hub, using the existing `criterion` benchmark infra already present for `pyo3-sanitizer` (`Rust Criterion Benchmarks (pyo3-sanitizer)` job) as the template — extend it to `native/rust_ext` and formalize the currently-ungated `WS-Hub Go Benchmark Regression Gate` job's thresholds (verify it currently has real fail-under thresholds, not just report-and-continue).

## Phase 10 — Certification, dashboard, and maintenance

**Task 10.1** — Author `scripts/quality/generate_dashboard.py`: reads the history of `quality-manifest.json` artifacts (requires archiving them somewhere durable across runs — e.g., committing a rolling `artifacts/quality/history/<date>.json` snapshot via a scheduled bot commit, or using GitHub's artifact retention plus a small script that fetches the last N runs via `gh api`) and renders a static HTML/Markdown trend dashboard (coverage per component over time, mutation score over time, Tier0 status, open exclusions/quarantines with expiry countdown) — published as a GitHub Pages artifact or committed to `docs/testing/dashboard.md`.

**Task 10.2** — Author a certification record generator (`scripts/quality/generate_certification.py`) invoked on tagged releases (hook into `.github/workflows/release.yml`), producing a signed/hashed record containing: exact commit SHA, the full required-check matrix results, all coverage/mutation/contract report hashes, current exclusion/quarantine register contents, and known limitations — satisfying the roadmap's Wave 10.4 exit gate.

**Task 10.3** — Write a quarterly flaky-test-audit runbook (`docs/testing/flaky-test-audit-runbook.md`): process for reviewing `--run-quarantined` marked tests, checking quarantine expiry dates against `quality/quality-contract.json`'s `quarantines` register (currently empty — this becomes actionable once any quarantine is ever added), and a disaster-recovery exercise checklist (restore from a migration snapshot, verify Alembic downgrade/upgrade round-trip against a production-like dataset size).

## Phase 14 — Ratchet sequencing table

Raise contract floors only after the corresponding phase's backlog is materially closed, in this order, to avoid ever re-triggering the exact "Coverage & Quality Policy Gate fails on merge" failure mode this plan exists to fix:

| Step | Component                                    | Metric                   | From → To                                                                        | Gate condition to proceed                                                                                      |
| ---- | -------------------------------------------- | ------------------------ | -------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| 1    | `python`                                     | `tier0.*`                | n/a → 100% (measured)                                                            | Phase 0 (measurement) lands + Phase 2.1 (5 Tier0 files) closed                                                 |
| 2    | `python`                                     | lines                    | 95.54 → 97                                                                       | Phase 2.2 items 1–60 closed                                                                                    |
| 3    | `python`                                     | lines                    | 97 → 99                                                                          | Phase 2.2 items 61–116 + Phase 2.3 closed                                                                      |
| 4    | `python`                                     | branches                 | 85.92 → 92                                                                       | Phase 2.2 items 1–60 closed                                                                                    |
| 5    | `python`                                     | branches                 | 92 → 98                                                                          | Phase 2.2 items 61–116 + Phase 2.3 closed                                                                      |
| 6    | `go-*`                                       | statements               | 90 → 95                                                                          | Phase 4.1 lowest-covered functions addressed via integration tests                                             |
| 7    | `go-*`                                       | statements               | 95 → 99                                                                          | Phase 4.1 fully closed                                                                                         |
| 8    | `rust-native`                                | lines/functions          | 88.5/80 → 99/98                                                                  | Phase 5.1 (`lib.rs`) closed                                                                                    |
| 9    | `frontend`                                   | lines/branches/functions | 91/82/82 → 95/88/88                                                              | Phase 3.1 (top-60) closed                                                                                      |
| 10   | `frontend`                                   | lines/branches/functions | 95/88/88 → 99/98/98                                                              | Phase 3.2 (long tail) closed                                                                                   |
| 11   | `policy.patch_coverage` (backend)            | diff-cover               | 80 → 90 → 100                                                                    | Phase 2.2 items 1–60 closed, then fully closed                                                                 |
| 12   | `policy.patch_coverage` (frontend, new)      | diff-cover               | n/a → 80 → 100                                                                   | Phase 3.5 tooling lands, then Phase 3.1 closed                                                                 |
| 13   | `policy.viable_mutant_score` (Python)        | mutmut                   | 85 (incremental, silent-skip) → 85 (incremental, hard-fail) → 100 (full nightly) | Phase 2.6.1 lands, then Phase 2.6.2 equivalent-mutant registry is populated for genuinely-equivalent survivors |
| 14   | `policy.viable_mutant_score` (frontend, new) | Stryker                  | n/a → 100 (scoped to pure utilities)                                             | Phase 3.3 lands                                                                                                |

Never skip a step or raise a floor before its gate condition — this table exists specifically to prevent a repeat of the PR #1207 failure mode where a contract floor was aspirational rather than earned.

## Phase 15 — Execution order

1. **Phase G** (governance) — must land before any other phase's "done" state can be trusted to stay merged.
2. **Phase 0** (Tier0 measurement, non-blocking sub-tasks only) — land measurement before enforcement.
3. **Phase 2.1** (Python Tier0 file closure) — small, high-priority, unblocks Phase 0's enforcement sub-task.
4. **Phase 0** (Tier0 enforcement sub-task) — now safe to make blocking.
5. **Phases 2–5** (Python, Frontend, Go, Rust) in any order convenient for working sessions — independent except where a ratchet-table gate condition specifies.
6. **Phases 6, 8, 9** (contracts, data/deployment, non-functional & security) — independent, can interleave with the above.
7. **Phase 7 (browser matrix)** — dedicated stabilization effort; budget calendar time for WebKit flake triage before promoting to blocking.
8. **Phase 10 (dashboard/certification)** — do this last; consumes stabilized trend data.
9. **Phase 14 ratchet steps** — applied incrementally throughout, gated exactly as specified in the table.
