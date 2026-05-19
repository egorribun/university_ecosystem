# Wave 171 audit — 31-wave maintenance-mode checkpoint + admin smoke CI monitoring

## Headline

✅ **CLOSED — Combo A+C (32nd consecutive disciplined wave; ~2-3h core).
"Maintenance-mode checkpoint" (NOT "project-done final state" — per operational
Q0 brainstorming: "continue maintenance + bug fixes only" mode) + admin smoke
CI monitoring infrastructure (NEW `.github/workflows/admin-smoke-monitoring.yml`,
493 LoC). Directly addresses W169 §Honesty residual "admin React #418
non-reproducible × 30 captures ≠ proven absent" **operationally** (not absolute
closure — monitoring infrastructure ships; future scheduled cron firings
provide empirical evidence over time).**

**§Honesty trajectory**: 0-2 OPEN pre-W171 → **0-2 OPEN post-W171** (count
unchanged; structural improvement via monitoring infrastructure addresses W169
§Honesty residual operationally; carryforward W134 #2 bundle delta + /messenger
Phase 5 punt by-design preserved unchanged — same pattern as W170 quality
improvement without quantity reduction).

- **Q0**: ⭐ RECOMMENDED was A (project-done declaration), brainstorming-derived
  **Combo A+C** (31-wave maintenance-mode checkpoint + admin smoke CI
  monitoring). Pure A was honestly framed as **operationally ceremonial**
  given user-validated "maintenance + bug fixes only" operational mode (future
  waves will fire when real bugs surface, regardless of project-done framing).
- **Q1**: ⭐ Combo A+C (single maintenance enabler addressing operationally
  biggest open gap — admin React #418 monitoring).
- **Q2**: ⭐ STRICT 1-iter per sub-item (W141 anti-pattern #1 SACRED — 24
  vindications baseline; W171 adds **25th vindication** since each SW landed
  in 1-iter with NO mechanism pivots).
- **Q3 brainstorm answer**: "Open-ended absorption — do what's honestly best"
  → recommended Moderate (~2-3h) over Minimum (~30-45 min lightweight A
  only) or Maximum (~3-5h long-tail D investigation).

## Commits table

| SW | Commit | Type | Files changed | Notes |
|----|--------|------|---------------|-------|
| SW0 | (no commit) | MEMORY.md compaction | `memory/MEMORY.md` (user .claude profile, not git-tracked) | 20,586 b post-compaction; +3,814 b headroom |
| SW1 | `686614860` | feat | NEW `.github/workflows/admin-smoke-monitoring.yml` (493 LoC) | Admin smoke CI monitoring workflow + scheduled cron Mondays 03:00 UTC |
| SW2 | (no commit) | Local verification | none | YAML syntax valid + cron syntax sanity + script feasibility confirmed via Phase 1+3 reads |
| SW3 | `6a1c1cd00` | docs | NEW `docs/audits/AUDIT_WAVE171.md` + `git mv AUDIT_WAVE168.md → archive/` + `CLAUDE.md` (## Audit Trail row + rotation history + Active waves) + `docs/audits/INDEX.md` (Active table W171 + W168 to Archive + rotation history) | Checkpoint audit + N+3 rotation |
| polish-v1 | `e83270645` | docs | `docs/audits/AUDIT_WAVE171.md` (+52/-5) | «Безупречно?» self-audit post-push captured cron default-branch caveat (§Honesty #11) + MEMORY.md tight headroom (§Honesty #12) + 2 lessons learned (#8, #9). W141 #3 45th-class vindication. |
| polish-v2 | `a521432f2` | docs | `.github/workflows/admin-smoke-monitoring.yml` (+8) + `CLAUDE.md` (1 hunk) + `docs/audits/AUDIT_WAVE171.md` (+26/-4) | 4-gap closure: CLAUDE.md cron caveat propagation + audit doc 45+46+47-class vindications + **Build × 3 EMPIRICALLY VERIFIED × 3 BYTE-IDENTICAL** (matches W170 polish-v2 baseline EXACT) + workflow file header default-branch caveat note. W141 #3 46+47-class vindications. |
| polish-v3 | (this commit) | docs | `docs/audits/AUDIT_WAVE171.md` (commits table + polish-v3 narrative) + `CLAUDE.md` (polish-v3 + CI Matrix SUCCESS ref) + `memory/MEMORY.md` (W171 row polish refs) | **Recursion terminator** per W164-W170 canonical pattern. Captures **CI Matrix Expansion SUCCESS 29m38s** for polish-v2 push run `26123305057` + 7 sub-gates GREEN. **W171 fully closed**. No further polish-vN expected. |

## SW0 narrative — MEMORY.md compaction (mandatory, non-tracked)

**Scope**: drop W168 verbose entry from Active backlog section (the W168 row
gets archived in SW3 N+3 rotation anyway); collapse W168 verbose Audit History
row to a one-liner with link to `docs/audits/AUDIT_WAVE168.md`.

**Before**: 24,324 b / 76 b headroom under 24,400 b ceiling — TIGHT, won't fit
a W171 row addition (~1-2 KB).

**After**: 20,586 b / 3,814 b headroom (-3,738 b / -15.4%).

**Net savings**: 3,738 b — exceeds plan target of ~1,800 b. More aggressive
collapse than originally planned saves headroom for W172+ row additions before
next MEMORY.md compaction cycle.

**Plan deviation (honest framing)**: Plan target was 22,500-23,000 b post-
compaction (~1,400 b headroom). Empirical post-edit was 20,586 b (~3,814 b
headroom) — over-target. Acceptable per `feedback_perfectionism.md` honest
framing: more headroom ≠ more work, just more room before next compaction.

**Mechanism**: SAME-mechanism within-iter per W138 Lesson #1 (extended scope
from "collapse W168 Audit History only" to "ALSO drop W168 Active backlog
entry"). NOT a mechanism pivot — both edits use Edit tool's `replace` flag
on text in MEMORY.md.

**Convention compliance**: Audit History table now has 4 rows (header + W170 +
W169 + W168 one-liner + W117-W167 condensed). Per "3 most-recent CLOSED verbose"
convention, this is correct ahead of W171 row addition (after which top-3
verbose will be W169 + W170 + W171 + W117-W168 condensed = exactly the convention
shape after SW3 finishes the table update).

**W141 anti-pattern compliance**:
- #1 (STRICT 1-iter): held — within-iter SAME-mechanism sub-fixes per W138
  Lesson #1 don't break the iter cap.
- #3 (Phase 3 verification): empirical `wc -c` measurement caught the over-
  target outcome (3,814 b vs 1,400 b min target) — non-blocking but honestly
  documented; ~42 vindications baseline pre-W171.

**Verification**:
```
wc -c memory/MEMORY.md         → 20,586 b ✓
Headroom: 24,400 - 20,586       = 3,814 b ✓
```

## SW1 narrative — NEW admin-smoke-monitoring.yml workflow

**Scope**: NEW `.github/workflows/admin-smoke-monitoring.yml` (493 LoC,
22,422 b) mirroring `.github/workflows/visual-audit.yml` infrastructure (W139
SW1 + W140 SW4 iter cycles) but invoking `wave165-admin-visual-smoke.mjs`
(W165 SW3) for admin React #418 detection on a scheduled cron cadence.

**Commit**: `686614860` `feat(wave171-sw1-admin-smoke-monitoring): NEW workflow
+ scheduled cron for React #418 re-emergence detection`. ~95% template reuse
from visual-audit.yml.

**Key differences from visual-audit.yml** (4 items):

1. **Trigger**: `workflow_dispatch` + `schedule: cron("0 3 * * 1")` Mondays
   03:00 UTC weekly (visual-audit is `workflow_dispatch` only — on-demand
   debug, not periodic monitoring). Weekly cadence balances early detection
   vs CI cost (~20-25 min/run × 4 weeks = ~80-100 min/month). Off-peak timing
   reduces shared runner contention.

2. **User seeding**: NEW `uv run python scripts/seed_demo_data.py` +
   `scripts/seed_admin_data.py` (visual-audit uses CSRF dance via
   `/api/v1/auth/register` for `test@university.dev`). Admin user has
   `role=admin` which CANNOT be set via the public register endpoint
   (default role is "student"); must be seeded via backend Python script.
   Both scripts are idempotent (catch IntegrityError on unique-constraint
   violations).

3. **Script invocation**: `wave165-admin-visual-smoke.mjs` with
   `TEST_EMAIL=admin@university.dev` + `TEST_PASSWORD=Admin@2024test`
   (matches `wave165.mjs:124-125` + `seed_admin_data.py:61-62`). visual-audit
   invokes `wave138-visual-audit.mjs` with test user.

4. **Artifact path + retention**: `frontend/.screenshots/wave165-admin-visual-smoke`
   + 30-day retention (visual-audit: 14 days). Longer retention enables
   quarterly trend analysis if React #418 re-emerges sporadically.
   `include-hidden-files: true` defensive per W160 SW1 (z) lesson — `.screenshots/`
   starts with "." (hidden dir per `actions/upload-artifact@v7` behavior).
   Current visual-audit.yml omits the flag and works, but defensive cost is
   zero (1 line).

**Re-asserted exit code (workflow status propagation)**:

`continue-on-error: true` on the script step → artifacts always upload (per
visual-audit.yml pattern). Final "Re-assert smoke result" step uses
`steps.smoke.outcome == 'failure'` to propagate non-zero exit (wave165 codes
1=HTTP, 2=hydration, 3=JWT, 4=JWKS) to workflow status so scheduled cron
failures show up red in Actions UI immediately.

**Re-used 100% from visual-audit.yml** (~15 steps, ~95% template reuse):

- Postgres + Redis + NATS services with health checks
- Node 22 + Python 3.13 + uv setup with caches
- Backend deps via `uv sync --frozen`
- WASM binaryen 3-attempt retry (W139 (z) #5 + W140 SW4 iter3)
- RS256 key generation via openssl
- Alembic migrations
- Frontend build with `VITE_E2E_MODE=1` + tree-shake invariants check
- Backend uvicorn + Node SSR background spinup
- `/health/ready` waits (W140 SW4 iter3 path fix — NOT `/health` which 404s)
- Caddy ingress via `docker run` (mirrors W139 SW1)
- Backend log diagnostic dump (W140 SW4 iter5 pattern)

**Summary table adaptation**: visual-audit.yml emits 7-column table (Route /
HTTP / Auth / Hydr err / Console err / Axe critical/serious / Net req).
admin-smoke-monitoring.yml emits 7-column adapted shape (Path / Theme / HTTP /
Auth / Hydr err / Console err / Net req — wave165 sidecar has theme + path
separately; no axe scan; same other fields). Status footer line distinguishes
3 outcomes: clean / failed captures / hydration errors detected.

**Husky pre-commit chain** (W141 #15 ARCHIVED preserved): commit `686614860`
fired chain cleanly:
- lint-staged: "No staged files match" (workflow file outside frontend lint-staged
  glob — expected)
- ruff check/fix/format: skipped (no .py changes)
- detect-secrets scan: PASSED (despite `Admin@2024test` example credential —
  `# pragma: allowlist secret` annotation respected)
- Detect hardcoded secrets: PASSED
- bandit/mypy/secret-enforcement: skipped (no Python changes)
- Reject Python 2 except syntax: PASSED

NO `--no-verify` bypass.

## SW2 narrative — Local verification (no commit)

**Scope**: validate workflow YAML structure + cron syntax + admin smoke script
local execution feasibility.

**Verification results**:

1. **YAML syntax**: ✅ Python `yaml.safe_load_all(open(...))` parses 1 doc
   cleanly; structure asserts pass (workflow_dispatch + schedule both present;
   cron `0 3 * * 1` extracted; 1 job; 3 services postgres+redis+nats; 25 steps).

2. **Cron syntax sanity**: ✅ `0 3 * * 1` is standard crontab format —
   minute(0) hour(03 UTC) day-of-month(*) month(*) day-of-week(1 = Monday).
   Equivalent to "Mondays 03:00 UTC weekly" / ~06:00 Moscow.

3. **wave165 script feasibility**: ✅ Phase 1 Explore agent + Phase 3 Review
   confirmed (W141 #3 discipline):
   - `wave165.mjs:131-137` ADMIN_ROUTES hardcoded (5 routes × 2 themes)
   - `wave165.mjs:397-403` hydrationErrors regex includes W167 SW1
     `/Minified React error #\d+/` pattern catching #418-#427 family
   - `wave165.mjs:562-575` exit codes: 0=clean / 1=HTTP-failed / 2=hydration
   - `wave165.mjs:408-420` sidecar shape: path, theme, httpStatus, finalUrl,
     redirectedToLogin, consoleErrorCount, hydrationErrorCount,
     networkRequestCount, screenshotPath, sampleErrors, navError
   - Env vars: ORIGIN (default `http://localhost`), TEST_EMAIL, TEST_PASSWORD,
     OUT_DIR — all configured in workflow

4. **gh workflow validation**: deferred to post-merge (or W171 polish
   recursion). After push, `gh workflow view admin-smoke-monitoring.yml --ref
   egorribun` should confirm GitHub Actions parses the workflow successfully.

**Honest framing per `feedback_perfectionism.md`**: SW2 outputs structural
confidence (YAML valid, cron syntax standard, script structurally compatible
with workflow's auth + URL chain) but NOT full validation. Full validation
requires actually triggering the workflow via `gh workflow run
admin-smoke-monitoring.yml` which is **post-merge work** — defer to W171
polish-pass OR W172+ scope. Following W139 SW1 visual-audit.yml precedent
(landed first; first scheduled cron fires post-merge).

## SW3 narrative — Audit + N+3 rotation (this commit)

**Scope**: NEW `docs/audits/AUDIT_WAVE171.md` (this file, ~280 lines) + N+3
rotation (W168 → archive) + CLAUDE.md updates (Audit Trail row + rotation
history line + Active waves line) + INDEX.md updates (W171 to Active, W168 to
Archive) + MEMORY.md row addition + NEW memory files (`wave171_backlog.md` +
`wave172_opening_prompt.md` in user `.claude` profile).

**Active waves post-W171**: **W169/W170/W171** (post N+3 rotation: W168 →
archive). Archive count: 55 → 56.

**Commit subject**: `docs(wave171-sw3-audit): 31-wave maintenance-mode
checkpoint + admin smoke monitoring + N+3 W168-archive`.

## Polish-v3 narrative — recursion terminator + CI Matrix Expansion SUCCESS evidence

**Scope**: capture CI Matrix Expansion SUCCESS evidence for polish-v2 push +
declare "no further polish-vN" closure + update CLAUDE.md / MEMORY.md to
reflect full polish chain. Per W164-W170 canonical recursion terminator
pattern (W170 polish-v3 captured CI Matrix Expansion SUCCESS 29m07s for
polish-v2 run `26118404589`; W169 polish-v3 captured 28m20s for polish-v2
run `26108885325`).

**CI Matrix Expansion SUCCESS for polish-v2 push `a521432f2` run
`26123305057`**: **29m38s SUCCESS**. ALL gates GREEN:

- ✅ CI - Matrix Expansion: SUCCESS 29m38s (main matrix gate)
- ✅ Chromatic Visual Regression: SUCCESS 1m57s
- ✅ Go Lint & SBOM: SUCCESS 1m43s
- ✅ Contract Validation — OpenAPI + Spectral: SUCCESS 1m42s
- ✅ DB Performance Gate: SUCCESS 1m15s
- ✅ Generate OpenAPI Spec: SUCCESS 1m21s
- ✅ Dependency Review: SUCCESS 22s
- ⏭️ Auto-merge dependabot patches: skipped (correctly — not a dependabot PR)

**Total**: 7 SUCCESS + 1 skipped = 8 of 8 jobs final. EXACT match to W170
polish-v3 + W169 polish-v3 SUCCESS patterns.

**Bundle baseline preserved across CI verification**: CI built and tested
against polish-v2 commit `a521432f2` which has NO frontend src changes vs
W170 polish-v3 baseline. Build × 3 LOCAL-MACHINE BYTE-IDENTICAL was already
empirically verified in polish-v2 (main JS sha `142897dd...3a38898` × 3 +
server.js sha `6ec125ed...0bca00` × 3). CI Matrix Expansion SUCCESS
**transitively re-validates** the bundle from a Linux runner perspective
(different env — Windows local vs Linux CI per W141 polish A3 documented
non-determinism axis — but functional gates all PASS regardless).

**Polish recursion termination**: Per W164-W170 pattern, polish-v3 is the
explicit "no further polish-vN" declaration. Polish-v1 captured cron
caveat; polish-v2 closed 4 gaps via empirical work + propagation;
polish-v3 captures CI evidence + declares closure. No further polish-vN
expected unless user fires another «безупречно?» probe surfacing genuinely
new gaps.

**W141 anti-pattern compliance**:

- #1 (STRICT 1-iter SACRED): preserved. polish-v3 is within-iter
  SAME-mechanism (doc update + CI evidence capture). No mechanism pivot.
- #3 (Phase 3 verification): preserved. Empirical `gh run list` post-CI
  verified ALL 8 jobs final state before commit. **48th-class vindication**.
- #4 (No premature "Closes"): preserved. Polish-v3 commit declares "W171
  fully closed" ONLY AFTER empirical CI SUCCESS evidence captured. NOT
  pre-emptive.
- #15 (ARCHIVED W159 SW4): preserved. Polish-v3 commit expected to fire
  W156 SW4 husky pre-commit chain cleanly. NO `--no-verify`.

## §Honesty probe (anticipated user «безупречно?» response)

| # | Caveat | Class | Disposition |
|---|--------|-------|-------------|
| 1 | **Helper-script-class adoption STILL not enforced** (W170 §Honesty #1 carry-forward) | Carry-forward unchanged | Admin smoke monitoring addresses DIFFERENT operational gap (React #418 detection); W170 #1 stays open. Pre-commit gate against raw `docker compose -f` invocations stays W172+ candidate. |
| 2 | **Cron cadence is judgment call** (weekly Mondays 03:00 UTC chosen) | Plan-time choice with documented rationale | Weekly balances early detection vs CI cost (~20-25 min/run × 4 weeks = ~80-100 min/month). Could be revisited as monthly if cost concern OR daily if React #418 risk perceived higher. Encoded in workflow comment block. |
| 3 | **Workflow not actually triggered in W171** — first scheduled cron fires post-merge | Honest framing | SW2 best-effort YAML + cron syntax validation only; full validation requires post-merge `gh workflow run` trigger (deferred to W171 polish OR W172+ scope). Following W139 SW1 visual-audit.yml precedent. |
| 4 | **Admin user seeding step is NEW vs visual-audit.yml** | Plan-time scope expansion | `seed_demo_data.py` + `seed_admin_data.py` are idempotent (per CLAUDE.md gotcha + seed_admin_data.py docstring); safe addition. CI cost: ~5-15 sec/run. Risk: low (scripts are established backend infrastructure). |
| 5 | **Wave165 lacks ROUTES env override** | Scope-acceptable | Admin smoke scope is FIXED by definition (5 admin routes × 2 themes = 10 captures). Override not needed; if W172+ wants subset testing, can add via `process.env.ROUTES?.trim()` pattern (W140 SW4 iter7). |
| 6 | **W141 anti-pattern #1 — SW1 single-iter scope** | Discipline check | SW1 was single workflow file creation mirroring template; landed in 1-iter with NO mechanism pivots. SW0 had within-iter SAME-mechanism scope extension (drop W168 Active backlog entry in addition to collapsing Audit History row) — explicitly permitted per W138 Lesson #1. |
| 7 | **«Project-done» framing NOT used in audit** | Honest framing per Q0 brainstorming | Per "maintenance + bug fixes only" operational mode (user-validated Q0), "project-done" would be ceremonial. Audit headline: "31-wave maintenance-mode checkpoint" — preserves discipline trail honestly without over-claiming closure. Future waves W172+ fire when real bugs surface (operational reality, NOT abandonment). |
| 8 | **§Honesty 0-2 → 0-2 OPEN count unchanged** | Net trajectory | New monitoring infrastructure improves operational rigor without closing existing carryforward §Honesty caveats (W134 #2 bundle delta + /messenger Phase 5 punt by-design). Net structural improvement without quantity reduction (mirrors W170 SW pattern). |
| 9 | **`include-hidden-files: true` is defensive** | W160 SW1 (z) hedge | Current visual-audit.yml doesn't set the flag and (presumably) works for `.screenshots/wave138-visual-audit` path. Adding the flag in admin-smoke follows W160 SW1 (z) lesson — `actions/upload-artifact@v7` strips hidden contents by default. Cost: 1 line; Risk: zero. |
| 10 | **SW0 over-target compaction** | Plan deviation honestly framed | Plan target was 22,500-23,000 b (~1,400 b headroom). Empirical: 20,586 b (~3,814 b headroom). More aggressive collapse than planned. Acceptable per `feedback_perfectionism.md`: more headroom = more room before next compaction, not more work. Documented openly. |
| 11 | **Workflow scheduled cron will NOT fire until cherry-picked to main OR PR #1114 merged** | Polish-v1 self-audit discovery | GitHub Actions limitation: scheduled triggers require the workflow file on the default branch (main). Empirical check post-push: `gh workflow view admin-smoke-monitoring.yml` returns HTTP 404 because file is on `egorribun` branch only. W139 SW1 precedent: visual-audit.yml was cherry-picked to main as commit `4db94fb5a` for default-branch visibility. Two options for W172+: (a) user-authorized cherry-pick to main (hard-to-reverse — requires explicit authorization per CLAUDE.md "executing actions with care") OR (b) wait for PR #1114 merge to main (scheduled cron activates automatically). The infrastructure IS shipped + correct; activation timing is the deferred aspect. **NOT a regression of W171 work** — the workflow file is structurally complete + ready. Plan §Honesty #3 ("Workflow not actually triggered in W171") was partially correct but understated the limitation (didn't anticipate default-branch requirement for cron).
| 12 | **MEMORY.md headroom is tight** | Trade-off accepted | Final state 24,335 b / 65 b headroom under 24,400 ceiling. Matches W170 post-state pattern (76 b headroom pre-W171). W172 SW0 will compact again via standard W141 #1 within-iter sub-fix pattern. Acceptable per maintenance-mode workflow — compaction is per-wave routine, not a deferred issue. |

**§Honesty net trajectory**: 0-2 → 0-2 OPEN (count unchanged; W171 adds
maintenance-enabling infrastructure addressing W169 §Honesty residual
operationally; carryforward W134 #2 + /messenger by-design preserved
unchanged; caveats #1-#12 are honestly-framed scope-deferrals and discipline
notes, not new structural caveats). Polish-v1 added #11 (scheduled cron
default-branch requirement) + #12 (MEMORY.md tight headroom) — both honest
documentation of post-commit empirical findings.

## W141 anti-pattern compliance summary

- **#1 (STRICT 1-iter SACRED)**: **25th total vindication**. All 4 SWs landed
  1-iter:
  - SW0 had within-iter SAME-mechanism scope extension (per W138 Lesson #1)
  - SW1 was single workflow file write with NO mechanism pivots
  - SW2 verification-only (no iter mechanism)
  - SW3 audit + N+3 rotation as planned

- **#3 (Phase 3 verification + Agent claim verification)**: **43+ vindications**
  baseline preserved. W171 contributions:
  - Phase 1 Agent recommended option (b) NEW separate workflow over (a)
    extending visual-audit.yml; Phase 3 verified via direct Read of
    visual-audit.yml structure + wave165 script — confirmed Agent correct
    on workflow_dispatch-only trigger, TEST_EMAIL=test@university.dev (not
    admin), wave138 invocation (not wave165). **43rd vindication**.
  - Phase 3 caught one verification point Agent didn't address explicitly
    (`.screenshots/` hidden dir behavior with v7 artifact upload —
    `include-hidden-files: true` defensive). **44th-class observation**.
  - SW0 empirical `wc -c` post-compaction caught over-target outcome
    (20,586 b vs plan 22,500-23,000 b). Non-blocking but documented honestly.
  - **Polish-v1** empirical `gh workflow view` post-push caught the cron
    default-branch limitation (HTTP 404 because workflow on feature branch).
    Plan §Honesty #3 ("Workflow not actually triggered in W171") was partially
    correct but understated the GitHub Actions platform constraint. **45th-class
    vindication** — polish-pass empirical verification is structural discipline
    that anticipates user «безупречно?» probe.
  - **Polish-v2** empirical gap audit (this commit) caught 4 internal
    consistency gaps: (a) audit doc missing #3 45th-class entry; (b) CLAUDE.md
    W171 row missing cron caveat reference; (c) workflow file header missing
    default-branch caveat note; (d) Bundle × 3 reproducibility not empirically
    verified end-of-wave. **46th-class vindication**.

- **#4 (No premature "Closes" attribution)**: **22nd vindication**. SW1 commit
  subject says "for React #418 re-emergence detection" (NOT "Closes React #418
  monitoring") — attributes the *infrastructure capability*, not absolute
  closure of W169 §Honesty residual. Audit doc explicitly frames as
  "**operationally** closed" (not absolute closure — monitoring ships;
  empirical evidence accumulates over future cron firings).

- **#15 (ARCHIVED W159 SW4)**: preserved. SW1 commit `686614860` + SW3 audit
  commit (this commit, hash TBD) both fired W156 SW4 husky pre-commit chain
  cleanly. NO `--no-verify` bypasses.

## N+3 rotation log

- `git mv docs/audits/AUDIT_WAVE168.md docs/audits/archive/AUDIT_WAVE168.md`
- Active waves post-W171: **W169 / W170 / W171**
- Rotation history sequence: W171 SW3 (W168 → archive)
- Archive count: 55 → 56

## Wave 172+ hand-off

### Priority candidates (post-W171)

1. **Continue "maintenance + bug fixes only" mode** — W172+ fires if/when real
   bug surfaces (operational reality). No active development planned. The
   31-wave audit trail (W134-W171) serves as historical learning artifact +
   onboarding documentation for any future maintainer.

2. **First scheduled cron firing** (post-W171 PR merge + first Monday 03:00
   UTC) — operational validation of admin-smoke-monitoring.yml infrastructure.
   **CRITICAL**: scheduled cron will NOT fire until workflow file is on the
   default branch (main). Two activation paths:
   - **Path A (Recommended)**: Wait for PR #1114 to merge to main →
     workflow lands on default branch → first cron fires at next Monday
     03:00 UTC.
   - **Path B (W139 SW1 precedent)**: User-authorized cherry-pick to main
     (commit visual-audit.yml-style as `4db94fb5a` was) → workflow
     immediately registers on default branch → can fire next Monday +
     workflow_dispatch becomes visible in `gh workflow view`. **Hard-to-
     reverse — requires explicit user authorization per CLAUDE.md
     "executing actions with care".**

   Once activated:
   - **If captures pass** (10 × HTTP 200 + 0 hydration errors): W169 §Honesty
     residual "non-reproducible ≠ proven absent" operationally re-confirmed.
     Future weekly firings provide ongoing empirical evidence.
   - **If captures fail** (≥1 React #418 firing): W172+ fires immediately for
     React #418 triage. Sidecar JSON artifacts + summary table provide
     starting evidence.

3. **Helper-script enforcement** (W170 §Honesty #1 closure path, deferred from
   W171) — pre-commit gate against raw `docker compose -f` invocations in
   commit-able files (forces use of `scripts/dc.{sh,ps1}` helpers). ~1-2h
   focused scope. Trade-off: false-positive risk on legitimate exceptions.

4. **Reusable workflow refactor** (W171 plan §Recommendation deferral) —
   extract common setup (postgres+redis+nats+uv+Node+Caddy+WASM-retry+RS256+
   seeding) from visual-audit.yml + admin-smoke-monitoring.yml into a shared
   GitHub reusable workflow (`.github/workflows/setup-linux-authed-infra.yml`).
   ~4-6h focused scope; only justified if W172+ accumulates ≥3 smoke workflow
   variants.

5. **W134 §Honesty #2 bundle delta deep investigation** (long-tail polish
   carry-forward) — ~3-5h focused scope; only if depth-over-breadth wanted.

### §Honesty state at W171 close

**0-2 OPEN**:

- **W134 #2 bundle delta** (carry-forward, recording-only). Long-standing
  audit-claim drift; documented but not load-bearing for production behavior.
- **/messenger Phase 5 punt by-design** (carry-forward, accepted-state). User
  decision: chat is inherently WebSocket-driven; SSR LCP win marginal;
  client-only render with React Query + optimistic UI is the right UX.

**Closed operationally in W171** (not "absolute closure"):

- **W169 §Honesty residual** "admin React #418 non-reproducible ≠ proven
  absent" — admin smoke CI monitoring provides ongoing detection
  infrastructure; scheduled cron firings will provide empirical evidence over
  time. The W171 infrastructure ships; absolute closure depends on N future
  firings × clean captures accumulating.

### Honest deferrals (W171 specific)

- **Scheduled cron NOT active until workflow on default branch** (Polish-v1
  discovery): workflow file shipped to egorribun branch via SW1 commit
  `686614860`, but GitHub Actions scheduled cron only fires for workflows
  on the default branch (main). Empirical: `gh workflow view
  admin-smoke-monitoring.yml` returns HTTP 404 post-push. W139 SW1
  precedent for cherry-picking visual-audit.yml to main; user-decision
  for admin-smoke. **Most honest path**: wait for PR #1114 merge — workflow
  activates automatically (Path A above).
- Workflow YAML structurally validated but NOT actually triggered (no
  workflow_dispatch invocation in W171). Triggering requires either
  cherry-pick to main OR PR #1114 merge first.
- Cron cadence "weekly Mondays 03:00 UTC" is plan-time judgment call; W172+
  can adjust based on empirical CI cost data.
- `include-hidden-files: true` defensive flag included even though current
  visual-audit.yml omits it and works — zero-cost insurance per W160 SW1 (z).
- ~~Build × N reproducibility NOT re-verified end-of-wave~~ → **CLOSED in
  polish-v2** via empirical Build × 3 BYTE-IDENTICAL verification: all 3
  fresh `rm -rf dist && npm run build` runs from clean state produce
  IDENTICAL sha256 (main JS `142897dd32e886903c24b28292f487b9cfbe597cdb7a3b86ca36767a63a38898` ×
  3 + server.js `6ec125ed1df8310e3d186d4b2065af7e56b6eb154f161f899ac360daad0bca00` ×
  3 + filename `index-BlWdKfsi.js` × 3) — MATCHES W170 polish-v2 + W169
  polish-v2 baseline EXACTLY. W134-W170 ≥34-wave LOCAL-MACHINE BYTE-IDENTICAL
  invariant chain EMPIRICALLY EXTENDS through W171 → **≥35-wave invariant
  EMPIRICALLY VERIFIED** (not just structural argument). W141 anti-pattern
  #3 47th-class vindication: empirical verification of structural argument
  is stronger than structural argument alone.

## Lessons learned

1. **"Maintenance + bug fixes only" mode honest framing**: per user Q0
   brainstorming + `feedback_perfectionism.md`, "project-done" declarations
   should match operational reality. Pure ceremony framings ("final state")
   risk diminishing future maintenance waves' legitimacy by implying the
   project shouldn't change. "Maintenance-mode checkpoint" preserves
   discipline trail honestly without over-claiming closure.

2. **Non-reproducible ≠ proven absent → operational counterpart is monitoring**:
   W169 SW2+SW5 captured 30 admin pages × 0 React #418 firings. Statistically
   supportive but not proof. Adding scheduled CI monitoring is the
   **operational** counterpart that catches re-emergence automatically.
   Pattern recipe for future "non-reproducible" findings: pair with periodic
   monitoring infrastructure.

3. **Phase 3 verification of Agent recommendations**: W171 Phase 1 Explore
   agent recommended option (b) NEW separate workflow over (a) extending
   visual-audit.yml. Phase 3 verified via direct Read of visual-audit.yml
   structure + wave165 script — confirmed Agent was correct on
   workflow_dispatch-only trigger, TEST_EMAIL=test@university.dev (not admin),
   wave138 invocation (not wave165). W141 anti-pattern #3 43rd vindication.

4. **Open-ended absorption + trust = brainstorming integration with W134-W170
   workflow**: when user grants "open-ended absorption — do what's honestly
   best", the most honest scope is moderate (~2-3h), not minimum or maximum.
   Combo A+C with single maintenance-enabler addresses operational gap
   without over-scoping. Pattern matches W139-W144 broad-but-time-bounded
   approach.

5. **Brainstorming skill integration with W134-W170 31-wave workflow**:
   brainstorming skill produces Q0 organically through clarifying questions;
   W134-W170 workflow then proceeds with Phase 1 Explore → Phase 3 Review →
   Phase 4 plan file → Phase 5 ExitPlanMode. The two are complementary, not
   redundant. Brainstorming surfaces operational reality (maintenance mode);
   workflow provides discipline structure (anti-patterns, verification,
   polish).

6. **Template-mirror workflows minimize divergence risk**: SW1 mirrors
   visual-audit.yml (~95% reuse) with 4 explicit differences documented in
   workflow comment block. Pattern recipe for future "similar but distinct"
   workflow needs: clone template + document differences inline, NOT
   reusable workflow refactor for first instance. Refactor justified when ≥3
   variants accumulate.

7. **Defensive flags from prior (z) lessons cost zero**: `include-hidden-files:
   true` per W160 SW1 (z) is 1 line + zero behavioral risk. Future workflow
   authoring should apply known-defensive flags by default even when current
   templates omit them. Anti-pattern #3 vindication-class category for "Agent
   missed defensive opportunity" observations.

8. **GitHub Actions scheduled cron triggers require workflow on default branch**
   (Polish-v1 discovery): scheduled triggers on a workflow file in a feature
   branch are INERT — they don't fire until the file lands on the default
   branch (main). W139 SW1 set the precedent via cherry-pick to main (commit
   `4db94fb5a`); without the cherry-pick, the workflow stays dormant. Future
   workflow-additions on feature branches should anticipate this — either
   (a) cherry-pick to main with user authorization, OR (b) accept activation
   deferral to PR merge as honest framing. W141 anti-pattern #3 lesson: even
   careful plans miss platform-specific implicit assumptions; polish-pass
   empirical verification catches them.

9. **«Безупречно?» polish-pass empirical verification is structural
   discipline** (W171 polish-v1 confirmation): per `feedback_perfectionism.md`,
   the user's «безупречно?» probe expects honest self-audit, not reassurance.
   Polish-v1 ran `gh workflow view` AFTER the SW3 commit + push, surfacing the
   default-branch cron caveat that the original plan missed. Pattern recipe:
   after declaring "done", run empirical verification commands (gh workflow
   view, gh run list, curl smoke, etc.) and document any findings as §Honesty
   additions BEFORE the user fires the «безупречно?» probe — anticipate the
   gaps the probe would surface.
