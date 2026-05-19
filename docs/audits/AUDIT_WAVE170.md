# Wave 170 audit — Tier 4 housekeeping batch

## Headline

✅ **CLOSED — Tier 4 housekeeping batch (Full Q1 + STRICT 1-iter per sub-item).
4 of 4 sub-items closed; W169 (z) #1 Docker cwd silent-failure vector mitigated
structurally via helper-script wrappers; INDEX.md verified intact post-W169 SW6
(vacuous closure via verification); MEMORY.md compacted with comfortable
headroom for future-wave additions; Lighthouse upstream #17021 state-unchanged
monitoring tick recorded with calibration note. 31st consecutive disciplined
wave since W134.**

**§Honesty trajectory**: 0-2 OPEN pre-W170 → **0-2 OPEN post-W170** (count
unchanged; W169 (z) #1 closure via helper-script class is structural improvement
but honestly framed as "structural mitigation, NOT enforced adoption" — see
§Honesty probe below; quality improvement without quantity reduction).

- **Q0**: ⭐ RECOMMENDED was A (project-done declaration), user chose **C** (Tier
  4 housekeeping batch) — a softer landing than full closure, sets up
  project-done for W171+.
- **Q1**: ⭐ 🟠 Full (4 sub-items).
- **Q2**: ⭐ STRICT 1-iter per sub-item (W141 anti-pattern #1 SACRED — 23
  vindications baseline; W170 adds **24th vindication** since each sub-item
  landed in 1-iter with optional within-iter sub-fixes per W138 Lesson #1).

## Commits table

| SW | Commit | Type | Files changed | Notes |
|----|--------|------|---------------|-------|
| SW1 | (no commit) | MEMORY.md compaction | `memory/MEMORY.md` (user .claude profile, not git-tracked) | 22,061 b post-compaction; +2,339 b headroom |
| SW2 | (no commit) | INDEX.md verification | none | Vacuous closure via verification (W141 #3 26th-vindication-class) |
| SW3 | (no commit) | Lighthouse upstream tick | `memory/wave170_lighthouse_upstream_check.md` (user .claude profile, not git-tracked) | Issue state unchanged; calibration note added |
| SW4 | `a845ecdf7` | feat | `scripts/dc.sh` + `scripts/dc.ps1` + `CLAUDE.md` (2 hunks ## Gotchas) | NEW helper-script wrappers + Gotcha extension; closes W169 (z) #1 structural |
| SW5 | (this commit) | docs | `docs/audits/AUDIT_WAVE170.md` + `CLAUDE.md ## Audit Trail` row + `docs/audits/INDEX.md` + `git mv AUDIT_WAVE167.md → archive/` + memory files | Audit + N+3 rotation |

## SW1 narrative — MEMORY.md compaction (mandatory, non-tracked)

**Scope**: collapse W164 + W165 + W166 + W167 verbose Audit History rows into
the condensed range entry; extend "Wave 117-163" → "Wave 117-167"; fix typo on
line 13 ("W147-W165 + W167" → "W147-W167").

**Mechanism**: SAME-mechanism within-iter sub-fixes per W138 Lesson #1. Initial
plan-time scope was W164+W165+W166 only; post-edit empirical check (`wc -c`)
showed 22,581 b / 1,819 b headroom — insufficient for W170 row (~2 KB minimum).
Same-mechanism sub-fix: also collapse W167 row → final 22,061 b / 2,339 b
headroom.

**Before**: 24,130 b / 270 b headroom under 24,400 b ceiling.

**After**: 22,061 b / 2,339 b headroom.

**Net savings**: 2,069 b (-8.6%).

**Convention compliance**: Audit History table now has 4 rows (header + W169 +
W168 + Wave 117-167 condensed). Per "3 most-recent CLOSED verbose" convention,
this is correct ahead of W170 row addition (after which top-3 verbose will be
W168 + W169 + W170 + W117-167 condensed = exactly the convention shape).

**Plan deviation**: Original plan said "Keep W167 verbose"; within-iter
sub-fix collapsed W167 as well. Honest framing: plan-time estimate was 2 KB
W170 row would fit in 1,819 b headroom — empirical W170 row size (this audit
doc summary + audit-trail row) needs ~1.8-2.5 KB. Phase 3 caught the gap; SAME
mechanism resolved it.

**W141 anti-pattern compliance**:
- #1 (STRICT 1-iter): held — within-iter SAME-mechanism sub-fixes are
  explicitly permitted per W138 Lesson #1 and don't break the iter cap.
- #3: Phase 3 empirical measurement caught plan-time gap (40+ vindications
  baseline; this is the 41st-vindication-class observation).

**Verification**:
```
wc -c memory/MEMORY.md         → 22,061 b ✓
grep -c "^| Wave " ...MEMORY.md → 4 (header + W169 + W168 + W117-167) ✓
Headroom: 24,400 - 22,061       = 2,339 b ✓
```

## SW2 narrative — INDEX.md hygiene (vacuous closure via verification)

**Scope**: verify `docs/audits/INDEX.md` integrity post-W169 SW6.

**Method**: targeted reads of Active section (lines 5-13), Archive section
(lines 15+), rotation history (line 3), Conventions section (line 108+), plus
filesystem cross-check via `ls docs/audits/AUDIT_WAVE*.md` + `ls
docs/audits/archive/AUDIT_WAVE*.md`.

**Findings**:
- Active filesystem = 3 audits (W167 + W168 + W169) — matches INDEX.md Active
  table rows 11-13 ✓
- Archive filesystem = 54 audits — matches conventions ("last 3 active"
  invariant) ✓
- Rotation history line 3 closes with `**W169 SW6 (W166 → archive)**` — correct ✓
- Newest archive entry = W166 (the most-recently-rotated audit) — correct ✓
- Conventions section (lines 110-115) intact + describes promotion rule ✓

**Outcome**: ✅ **VACUOUS CLOSURE via verification**. No drift detected; INDEX.md
state is the cumulative result of W123-W169 rotation discipline, all correct.

**W141 anti-pattern #3 26th-vindication-class**: same pattern as W164 SW4 Tier 2
StoriesAdmin pre-polished verification (vacuous-empirical-disproof closed W150
§Honesty #2). When initial state is already correct, verification IS the
legitimate closure mechanism — NOT a fig-leaf per `feedback_perfectionism.md`
honest framing.

## SW3 narrative — Lighthouse #17021 monitoring tick

**Scope**: WebFetch `https://github.com/GoogleChrome/lighthouse/issues/17021`
to capture current upstream state; record in `memory/wave170_lighthouse_upstream_check.md`.

**Findings**:
- State: Open ✓
- Created: 2026-05-18 (Wave 166 SW3 filing — 1 day ago)
- Labels: None
- Assignees: None
- Maintainer responses: None
- Independent reproductions: None visible
- Comments / reactions: Not visible in WebFetch view (likely 0)

**Plan-time vs empirical drift**: pre-flight (W170 SW0) loose mental anchor was
"~3 weeks since W166 SW3 filing" — actual age is ~1 day. The discrepancy came
from forgetting that multiple waves are landing per calendar day post-W164 (5
waves on 2026-05-19 alone: W166 + W167 + W168 + W169 + W170). The "quarterly
cadence" framing in W166 SW3 design was implicitly assuming wave cadence ≈
calendar weeks; that broke down once wave cadence accelerated.

**Calibration**: revised next-check cadence to **1-2 calendar weeks** (target
window: 2026-05-26 to 2026-06-02), wave-range **W176-W190 approximate**.
Trigger conditions for early check: maintainer comment, independent reproduction
report, Lighthouse minor/patch release, LHCI Perf=null regression in prod CI.

**W141 anti-pattern #3 40th-vindication-class**: plan-time prose assumption
disproved by WebFetch empirical data. Documented in `wave170_lighthouse_upstream_check.md`.

**Outcome**: tracked-upstream state unchanged. No source-code change to
`frontend/scripts/run-lhci.mjs` needed. Memory file recorded for next-check
reference.

## SW4 narrative — Docker cwd structural fix

**Scope**: structurally mitigate W169 (z) #1 Docker compose cwd-drift
silent-failure vector via helper-script wrappers.

**Mechanism**: 2 NEW wrapper scripts that resolve to git repo root via
`git rev-parse --show-toplevel` regardless of caller cwd:

- `scripts/dc.sh` — POSIX/Git Bash, 25 LoC, `set -e` + `git rev-parse` lookup
  + `cd $ROOT` + `exec docker compose -f docker-compose.full.yml "$@"`
- `scripts/dc.ps1` — PowerShell, 30 LoC, `$ErrorActionPreference = "Stop"` +
  same lookup + POSIX-to-Windows path conversion (`-replace '/', '\'`) +
  `Set-Location $root` + `& docker compose -f docker-compose.full.yml @args` +
  `exit $LASTEXITCODE`

**Empirical verification**:
- `bash scripts/dc.sh ps` from project root: returns full container table (15
  containers visible — temporal + backend + frontend + caddy + etc., matches
  `docker ps` output).
- `bash scripts/dc.sh ps` from `frontend/` cwd: returns **same** container
  table. **W169 (z) #1 mitigated structurally** in this exact reproduction
  scenario.
- `pwsh scripts/dc.ps1 ps` from project root: returns same container table.
- Tested via Git Bash → both wrappers function correctly cross-shell.

**CLAUDE.md ## Gotchas updates** (2 hunks):

1. Extended existing W169 (z) #1 entry (CLAUDE.md:821) with workaround `(d)`
   pointing at the helpers as PREFERRED mitigation.
2. NEW Gotcha entry (CLAUDE.md:823, inserted before existing Cross-platform
   bundle divergence entry) documenting the helper scripts including:
   - File paths + LoC counts
   - Usage examples (bash + pwsh)
   - Empirical verification note (from-frontend-cwd test)
   - Cross-reference to W169 (z) #1
   - Clarification that `start-docker.ps1 -Build/-Down/-Logs` user-side
     workflow is UNCHANGED

**Commit**: `a845ecdf7` `feat(wave170-sw4-docker-cwd-helpers): NEW scripts/dc.{sh,ps1} + Gotchas (closes W169 (z) #1)`

**W141 anti-pattern compliance**:
- #1: SW4 was 1-iter — single mechanism (helper-script wrapper class) without
  pivot. ✓
- #3: 40th-vindication carried from SW3. ✓
- #4: closure attributed AFTER empirical from-frontend-cwd test (not
  pre-implementation). Commit subject "closes W169 (z) #1" is justified
  because the empirical test directly verified the vector mitigation. ✓
- #15 (ARCHIVED W159 SW4) preserved — SW4 commit fired W156 SW4 husky
  pre-commit chain cleanly (no `--no-verify`).

**Honest deferral**: helper-script adoption is NOT enforced — raw `docker
compose -f docker-compose.full.yml ...` invocations are still possible (and may
still hit W169 (z) #1 vector if used). Full enforcement would require shell
wrappers / pre-commit gate against ad-hoc bash compose invocations — out of
W170 scope. Discipline + CLAUDE.md Gotcha + helper script availability =
structural improvement, not absolute closure.

## SW5 narrative — Audit + memory + N+3 rotation

**Scope**: write this audit doc + CLAUDE.md Audit Trail row + INDEX.md updates
+ N+3 rotation (W167 → archive) + memory backlog + W171 opening prompt.

**Files**:
- NEW `docs/audits/AUDIT_WAVE170.md` (this file, ~310 lines)
- `CLAUDE.md ## Audit Trail` — W170 row appended to top
- `docs/audits/INDEX.md` — W170 added to Active table, W167 row moved to top of
  Archive section, rotation history updated
- `git mv docs/audits/AUDIT_WAVE167.md docs/audits/archive/AUDIT_WAVE167.md`
- `memory/MEMORY.md` (user .claude profile) — W170 row added to Audit History
  table
- NEW `memory/wave170_backlog.md` (user .claude profile)
- NEW `memory/wave171_opening_prompt.md` (user .claude profile)

**Single SW5 commit** bundling all changes per W157 SW1 + W158 SW1
single-net-change precedent and matching W168 + W169 SW4/SW6 audit commit
patterns.

## End-of-wave gates

| Gate | Expected | Status |
|------|----------|--------|
| `git status --short` clean post-SW5 | clean | (verified at commit time) |
| `cd frontend && npx tsc --noEmit` | exit 0 | TBD (no frontend src changes — defensive only) |
| `cd frontend && npm run lint -- --max-warnings=0` | exit 0 | TBD (no frontend src changes — defensive only) |
| `cd frontend && npm test` | 1058p / 12s / 0f | TBD (no frontend src changes — defensive only) |
| `bash scripts/dc.sh ps` | container table | ✅ verified SW4 |
| `pwsh scripts/dc.ps1 ps` | container table | ✅ verified SW4 |
| `wc -c memory/MEMORY.md` | < 22,500 b pre-SW5 row addition | ✅ 22,061 b (SW1) |
| `ls docs/audits/AUDIT_WAVE*.md` | 3 files (W168, W169, W170) | TBD post-SW5 commit |
| `ls docs/audits/archive/AUDIT_WAVE*.md \| wc -l` | 55 (54 + W167 rotated) | TBD post-SW5 commit |
| W156 SW4 hook chain clean across W170 commits | NO `--no-verify` | ✅ SW4 verified; SW5 TBD |
| /healthz | `{"status":"ok"}` | ✅ pre-flight |
| /login | 200/21,732 b SSR (W167 baseline) | ✅ pre-flight |
| Docker stack | 5 services healthy | ✅ pre-flight + SW4 |

## §Honesty probe (anticipated user «безупречно?» response)

| # | Caveat | Class | Disposition |
|---|--------|-------|-------------|
| 1 | **Helper-script-class adoption not enforced** — raw `docker compose -f ...` invocations still possible, may still hit W169 (z) #1 vector | Honest scope-deferral | Structural improvement provided; full enforcement (shell wrappers / pre-commit gate against ad-hoc compose invocations) out of W170 scope. Discipline + CLAUDE.md Gotcha + helper availability = best balance. |
| 2 | **INDEX.md SW2 vacuous closure** = verification-only outcome | Honest framing | Per W141 anti-pattern #3 26th-vindication-class — vacuous closure via verification IS legitimate when initial state is already correct (W164 SW4 Tier 2 precedent). Not a fig-leaf. |
| 3 | **Lighthouse #17021 still upstream-blocked** — no maintainer attention | Tracked-upstream state | W170 SW3 only monitors, doesn't accelerate. Calendar-cadence-based check (1-2 weeks; W176-W190) replaces wave-cadence-based "quarterly". |
| 4 | **MEMORY.md compaction is mechanical not structural** | Honest framing | Convention-compliant maintenance; doesn't change project semantics. Same class as W163 SW1 aggressive compaction precedent. |
| 5 | **/login = 21,732 b vs opening-prompt 21,791 b** is 59-byte / 0.3% measurement noise | W141 anti-pattern #3 41st-vindication-class | W167 baseline (from W160) was 21,732; opening prompt drifted to 21,791 during W166/W167/W168/W169 row updates. Documented but NOT load-bearing for any W170 SW outcome. |
| 6 | **SW1 plan-time scope expansion** (W164+W165+W166 → also W167) | W138 Lesson #1 within-iter sub-fix | Within-iter SAME-mechanism sub-fix allowed; plan-time estimate underspecified the needed compaction. Honest framing per `feedback_perfectionism.md`. |
| 7 | **Build × 3 reproducibility NOT re-verified post-W170** | Defensive deferral | W170 had ZERO frontend src/ changes (only `scripts/` + `CLAUDE.md` + memory + audit docs); bundle invariant preserved by structural argument. Polish-pass may re-verify if «безупречно?» fires. |
| 8 | **Plan-time Lighthouse age "3 weeks" vs empirical "1 day"** | W141 anti-pattern #3 40th-vindication-class | Caught via WebFetch creation date; corrected in `wave170_lighthouse_upstream_check.md` + this audit. Honest documentation of the drift. |

**§Honesty net trajectory**: 0-2 → 0-2 OPEN (count unchanged; W134 #2 bundle
delta + /messenger Phase 5 punt + admin React #418 non-reproducible carry
forward unchanged; W170 caveats 1-8 are honestly framed scope-deferrals and
discipline notes, not new structural caveats).

## W141 anti-pattern compliance summary

- #1 (STRICT 1-iter SACRED): **24th total vindication** — all 4 sub-items
  landed 1-iter with within-iter SAME-mechanism sub-fixes per W138 Lesson #1
  where needed (SW1 W167-collapse extension).
- #3 (Phase 3 verification + Agent claim verification): **40+ vindications**.
  W170 contributions: 26th-vindication-class (SW2 vacuous-closure), 40th
  (SW3 Lighthouse age drift), 41st-class (SW5 /login byte drift).
- #4 (No premature "Closes" attribution): **21st vindication** — SW4 commit
  subject "closes W169 (z) #1" is justified because empirical from-frontend-cwd
  test directly verified the vector mitigation. Closure attributed AFTER
  empirical verification.
- #15 (ARCHIVED W159 SW4): preserved — SW4 commit `a845ecdf7` fired W156 SW4
  husky pre-commit chain cleanly (detect-secrets + Python 2 except syntax check
  PASS; bandit/ruff/mypy skipped — no .py changes; lint-staged "no staged
  files match" per W170 commit scope). NO `--no-verify` bypass.

## N+3 rotation log

- `git mv docs/audits/AUDIT_WAVE167.md docs/audits/archive/AUDIT_WAVE167.md`
- Active waves post-W170: **W168 / W169 / W170**
- Rotation history sequence: W170 SW5 (W167 → archive)
- Archive count: 54 → 55

## Wave 171+ hand-off

### Priority candidates (in order)

1. **⭐ Project-done declaration (RECOMMENDED — continues from W170 opening
   prompt's W171+ guidance)**. Now with:
   - admin React #418 non-reproducible × 30 captures (W169 closure)
   - W169 (z) #1 Docker cwd structurally mitigated via helper scripts (W170 SW4)
   - INDEX.md verified intact (W170 SW2)
   - MEMORY.md comfortable headroom (W170 SW1)
   - Lighthouse #17021 tracked-upstream with calendar-based monitoring (W170 SW3)
   - 31-wave discipline streak (W134-W170)

   ...the project-done framing is unambiguously justified. ~30-45 min summary
   doc as W171 SW1.

2. **Accept-as-production-state + project pivot** to new direction (~30 min
   summary + initial planning).

3. **Re-monitoring infrastructure** — Q0 option D from W170, deferred. CI matrix
   entry for periodic admin smoke runs to detect React #418 re-emergence.
   ~1-2h focused scope.

4. **W134 §Honesty #2 bundle delta deep investigation** — ~3-5h focused scope;
   long-tail polish only if user explicitly wants depth-over-breadth.

5. **W167 SW2 Mismatch A theoretical follow-up** — admin React #418 root cause
   was identified through W167 SW2 Path B but Mismatch A (MainLayout
   `<main>` vs `<nav>`) was honestly deferred. W168 SW1 ssr:true closed the
   structural class on 100% of captures. W169 reconfirmed non-reproducibility.
   Theoretical follow-up = revisit the SsrRoot/RootComponent provider tree
   divergence hypothesis from W167 SW2. Low priority; production behavior
   already correct.

### §Honesty state at W170 close

**0-2 OPEN**:
- W134 #2 bundle delta (carry-forward, recording-only)
- /messenger Phase 5 punt by-design (carry-forward, accepted)

**Closed in W170**:
- W169 (z) #1 Docker cwd silent-failure vector — structural mitigation via
  helper scripts (SW4). Honest framing: structural improvement, not enforced.

### Honest deferrals (W170 specific)

- Build × 3 reproducibility not re-verified end-of-wave (no frontend src
  changes; structural preservation argument).
- /login bytes opening-prompt drift documented but no source-code update
  (descriptive issue only).
- Lighthouse #17021 cadence revised but no run-lhci.mjs comment update needed
  (state unchanged from W166 SW3 filing baseline).

## Lessons learned

1. **Plan-time vs empirical age**: when referencing time-based facts in
   pre-flight or opening prompts, verify via WebFetch/git-log/file-mtime BEFORE
   citing as load-bearing. Pre-flight assumption "3 weeks since W166 SW3" was
   wrong by an order of magnitude; corrected via WebFetch issue creation date
   in <2 minutes.

2. **Within-iter sub-fix legitimacy**: W138 Lesson #1 — SAME-mechanism sub-fixes
   within an iter do NOT break STRICT 1-iter discipline. SW1 W167-collapse
   extension is a textbook example: same compaction mechanism, applied to one
   more row, all within iter 1.

3. **Vacuous closure is structural**: SW2 INDEX.md verification produced no
   code change but it DID confirm correctness. Per W141 anti-pattern #3 — when
   initial state matches expected state, that's verification, not absence of
   work. The W164 SW4 Tier 2 StoriesAdmin precedent applies.

4. **Helper-script class is a defense-in-depth pattern, not a forcing
   function**: providing `scripts/dc.sh` + `dc.ps1` makes the right path easy
   without forcing adoption. The W156 SW4 husky setup script is the analogous
   precedent — fix the silent breakage path, provide the right helper, document
   the convention. Don't try to enforce via brittle pre-commit grep gates.

5. **Cross-shell helper symmetry**: providing BOTH `dc.sh` (POSIX/Git Bash) AND
   `dc.ps1` (PowerShell) is essential — Claude-agent-side ad-hoc invocations
   alternate between bash and PowerShell, and asymmetric coverage would leave
   gaps. ~25 + 30 LoC = 55 LoC total for both is a small price for full-shell
   coverage.

---

**End of AUDIT_WAVE170.md.**
