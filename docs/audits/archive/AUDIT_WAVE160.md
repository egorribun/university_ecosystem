# Wave 160 audit — Tier 3 LHCI 3-session × 3-run ratchet + Tier 4 housekeeping

**Branch**: `egorribun`
**HEAD pre-W160**: `e59cc7e7f` (W159 polish-close)
**HEAD post-W160 SW2**: `44b33c230` (`chore(wave160-sw2-lhci-ratchet)`)
**Wave-step commits**: `7ca2b63eb` (SW1-fix-1) → `c5ad2f425` (SW1-fix-2) → `44b33c230` (SW2 ratchet) → SW4 audit commit (this)
**Wave start**: 2026-05-17 10:22Z
**Wave close**: 2026-05-17 ~14:30Z (~4h wall-clock; ~3h core; within Q1 Recommended budget)
**21st consecutive wave** with `superpowers:brainstorming` + Phase 1 Explore + Phase 3 Review + W141 anti-pattern discipline (W134-W160).

---

## Headline

**Tier 3 LHCI ratchet via 3-session × 3-run methodology DELIVERED — first ratchet decision applied post-W125-W149 SSR Phase 5 + W158 SW1 canonical minified PROD bundle.**

- **CLS gate ratcheted**: `error@0.10 → error@0.05` (50% tighter WCAG-Good ceiling) based on worst cross-session median 0.044 on /map; variance ~0.000 across 3 sessions; 12% margin to new ceiling
- **9-URL × 3-session × 3-run = 81 LHRs captured** via `gh workflow run lhci-linux.yml` × 3 sessions on Linux CI runner (no Windows wrapper hang, no EPERM)
- **W134 §Honesty #1** (LHCI baseline framing long-overdue since W117 SW8 opening prompts) **CLOSED** structurally
- **W159 NEW #2** (LHCI measured 4 of 9 URLs in W159 SW2 Windows wrapper) **CLOSED** via 9-URL full sweep
- **2 SW1 latent infrastructure bugs DISCOVERED + FIXED** within iter 1 course-correction (per W138 Lesson #1): `actions/upload-artifact@v7` hidden-files default + `LHCI_URLS=""` empty-string handling
- **3 ratchet candidates HONESTLY HELD** (per `feedback_perfectionism.md`): Perf (structural Linux CI screenshot blocker), LCP (mobile throttling reality), TBT (same)

**§Honesty trajectory**: 5-8 OPEN pre-W160 → **5-8 OPEN post-W160** (net ZERO range; 2 closures balanced by 2 NEW honest scope-deferrals — see §Honesty section)

**(z) discoveries**: 2 NEW (artifact upload v7 + LHCI_URLS empty-string) — both within SW1 iter 1, both shipped as structural fixes (not deferred)

**W141 anti-pattern compliance**: #1 **14th vindication** (STRICT 1-iter held; 2 SW1 sub-fixes were course-corrections within same iter per W138 Lesson #1); #3 **17th + 18th vindications** (Phase 3 verification of opening-prompt + workflow-description claims caught BOTH latent bugs empirically); #4 **15th vindication** (closures attributed AFTER 81-LHR data captured + ratchet applied); #15 (ARCHIVED W159 SW4 — husky infrastructure preserved; all W160 commits fired cleanly without `--no-verify`)

---

## Wave summary

User-approved Q1+Q2 (Recommended Tier 3 LHCI ratchet + Tier 4 MEMORY.md compaction + STRICT 1-iter per Tier option) + Q3 9-URL full sweep + Q4 Pure Linux CI × 3 workflow_dispatch (per brainstorming-skill sub-design questions after main Q1+Q2).

**3 code commits on `egorribun`**:

| Commit | Type | Files | Description |
|--------|------|-------|-------------|
| `7ca2b63eb` | fix | 2 (+7/-0) | SW1-fix-1: `actions/upload-artifact@v7` include-hidden-files=true |
| `c5ad2f425` | fix | 1 (+16/-3) | SW1-fix-2: distinguish empty LHCI_URLS from leading-comma override |
| `44b33c230` | chore | 1 (+57/-2) | SW2 CLS ratchet `error@0.10 → error@0.05` + document 81-LHR cross-session medians |
| SW4 audit | docs | ~9 | This audit + CLAUDE.md row + INDEX.md + N+3 rotation + memory + handoff |

---

## SW1: 3 × workflow_dispatch + collect artifacts (81 LHRs) — DONE

### Plan vs reality

Plan said: trigger 3 sessions sequentially via `gh workflow run lhci-linux.yml --ref egorribun --field urls=""`, wait for each via `gh run watch`, download via `gh run download`. Reality required **2 latent bug fixes within iter** before clean data flow:

**Latent bug #1: `actions/upload-artifact@v7` hidden-files default**

First session #1 attempt (run `25988283380`, HEAD `e59cc7e7f`) completed `success` per CI status but `gh run download` returned `no valid artifacts found to download`. Log diagnostic via `gh run view --log` revealed: `##[warning]No files were found with the provided path: frontend/.lighthouseci. No artifacts will be uploaded.`

Root cause: `actions/upload-artifact@v7.0.1` (the pinned SHA) introduced a breaking change vs v3-v5 — `include-hidden-files` defaults to `false`, which filters out files inside any path starting with `.` (including the `.lighthouseci/` hidden dir that `@lhci/cli` writes its LHR JSONs to). The previous v5 default included hidden files; the v7 silent SHA upgrade inherited the new restrictive default.

The workflow's "Print summary table" step uses Node's `fs.readdirSync` (no hidden-file filter) so it correctly found the 1 URL's worth of LHRs that the run produced. But the upload step skipped them all.

Fix (`7ca2b63eb`): explicit `include-hidden-files: true` on the upload step, with 5-line comment block citing the v7 breaking change + closure framing.

**Latent bug #2: `LHCI_URLS=""` overrides 9-URL default**

After bug #1 was fixed, second attempt session #1 (run `25988491091`, HEAD `7ca2b63eb`) was triggered via `gh workflow run lhci-linux.yml --ref egorribun --field urls=""`. Initial workflow log shows step status `Run Lighthouse CI` completed `success`; summary table at end showed **only `/` URL** (1 row, Perf `-`, CLS 0.001).

This was unexpected — the workflow input description at `lhci-linux.yml:47` reads "Comma-separated URL paths (empty = full default 9-URL sweep)". Empirical reality: `LHCI_URLS=""` was setting up a single-URL run.

Phase 3 root cause investigation via `Read frontend/scripts/run-lhci.mjs`: lines 120-123 ran `process.env.LHCI_URLS?.split(",")` ─ `?.` only short-circuits on null/undefined. For literal empty string `""`:
- `"".split(",")` → `[""]`
- `.map(p => p.trim() || "/")` → `["/"]`
- `.filter(Boolean)` → `["/"]` (truthy single element)
- `overridePaths.length === 1` → overrides defaults
- Result: single-URL sweep instead of 9-URL default

The workflow `LHCI_URLS: ${{ inputs.urls }}` unconditionally sets the env var, so the workflow_dispatch default `urls: ""` ALWAYS triggers this branch. Every previous lhci-linux.yml workflow_dispatch invocation (W139 SW3 retries on 2026-05-09) had been silently narrowed to root-only, not the documented 9-URL sweep — masked because those runs `failure`'d at earlier Lighthouse PAGE_HUNG steps before reaching summary table.

Fix (`c5ad2f425`): truthiness gate on env var. `const lhciUrlsEnv = process.env.LHCI_URLS; const overridePaths = lhciUrlsEnv ? lhciUrlsEnv.split(...).map(...).filter(Boolean) : undefined;`. Empty string `""` falls through to defaults; non-empty strings (including `,login,dashboard` leading-comma MSYS-bypass pattern from W119 SW2) still process normally.

**Verification of both fixes**

Third session #1 attempt (run `25988551157`, HEAD `c5ad2f425`) completed `success` in 24m40s (~3× longer than the broken 1-URL run) → 27 LHRs in artifact → `gh run download` extracted them cleanly to `.wave160-lhci/session-1/`. Sanity check verified: `lhr.requestedUrl` covers all 9 URLs (/, /login, /dashboard, /news, /schedule, /events, /activity, /map, /404) × 3 runs each.

Then sessions #2 (run `25989078530`, ~24 min) + #3 (run `25989579477`, ~24 min) ran sequentially per the `concurrency.group: lhci-linux-${{ github.ref }}` + `cancel-in-progress: true` constraint. Both succeeded; both delivered 27 LHRs each. Total: **81 LHRs across 3 sessions** matching plan exactly.

### Cross-session medians (per-URL × per-metric, mobile devtools throttling, VITE_LHCI=true)

3-run median per session → median-of-3-session-medians (cross-session median). Variance band ±0.01-0.05 across the 3 sessions — methodology validates per W124 SW4.

| URL        | Perf | A11y | BP   | SEO  | CLS   | LCP(ms) | TBT(ms) |
|------------|------|------|------|------|-------|---------|---------|
| /          | —    | 1.00 | 0.96 | 0.92 | 0.001 | 2895    | 549     |
| /login     | —    | 1.00 | 0.96 | 0.91 | 0.000 | 324     | 272     |
| /dashboard | —    | 1.00 | 0.96 | 0.92 | 0.000 | 2857    | 517     |
| /news      | —    | 1.00 | 0.96 | 0.92 | 0.000 | 340     | 446     |
| /schedule  | —    | 1.00 | 0.96 | 0.92 | 0.000 | 376     | 423     |
| /events    | —    | 1.00 | 0.96 | 0.92 | 0.000 | 396     | 454     |
| /activity  | —    | 1.00 | 0.96 | 0.92 | 0.000 | 411     | 455     |
| **/map**   | —    | 1.00 | 0.96 | 0.92 | **0.044** | 403 | 466     |
| /404       | —    | 1.00 | 0.96 | 0.92 | 0.000 | 309     | 425     |

**Cross-URL worst-case**:
- Perf: ALL `—` (null — structural blocker, see SW2)
- A11y: 1.00 everywhere
- CLS: 0.044 on /map
- LCP: 2895ms on /
- TBT: 549ms on /

**Methodology validation**: per-session medians for the same URL × metric stay within ±0.01-0.05. Single 3-run can swing ±0.04 from cross-session truth per W124 SW4 — the variance band here is at the LOWER end of W124's range, suggesting methodology gives clean signal post-SSR.

---

## SW2: CLS ratchet decision + apply — DONE

### Ratchet decision tree (data-driven per W160 plan §SW2 step 3)

**(1) CLS ratchet `error@0.10 → error@0.05` — APPLIED**

- Worst cross-session median: **0.044** on /map
- Variance: ~0.000 across 3 sessions (truly stable)
- New ceiling 0.05 has 12% margin (0.006 buffer from worst measured)
- Across all 81 LHRs, worst SINGLE-RUN value is also 0.044 (no single-run outliers)
- Tightens WCAG-Good ceiling by 50%
- SAFE — all 9 URLs measure ≤ 0.044

**(2) Perf gate HOLD `warn@0.40` — STRUCTURAL Linux CI blocker**

Phase 3 LHR inspection via `node -e` on `.wave160-lhci/session-1/lhr-1779014608238.json` revealed:

```
audits with null score or error:
  speed-index => "Chrome didn't collect any screenshots during the page load..."
  screenshot-thumbnails => "Chrome didn't collect any screenshots..."
  metrics => "Chrome didn't collect any screenshots..."
core audit values:
  FCP: 524.091 (measured)
  LCP: 3045.31 (measured)
  TBT: 587.916 (measured)
  CLS: 0.001 (measured)
  Perf score: null
  A11y score: 1
```

Lighthouse can compute individual metrics (FCP/LCP/TBT/CLS via Chrome DevTools Protocol traces) but CANNOT compute `categories.performance.score` without `speed-index`, which requires screenshot collection. Chrome flags at [`run-lhci.mjs:130`](frontend/scripts/run-lhci.mjs:130) (`--headless=new --disable-gpu --no-sandbox --disable-dev-shm-usage --allow-insecure-localhost --ignore-certificate-errors --test-type`) prevent Chrome from collecting screenshots in the headless mode under Linux CI runner conditions. Same null-Perf pattern across ALL 9 URLs × 81 LHRs (100% reproducible).

This closes routine-e5 calibration drift **PARTIALLY** — the prior `error@0.40` relaxation to `warn@0.40` was justified pre-SSR by CI Linux measuring 0.10-0.12 lower than Windows wrapper. W160 confirms the drift NOW manifests as null Perf (structural unmeasurability) rather than just calibration delta. Full ratchet pending W161+ chrome flags investigation (likely drop `--disable-gpu` or switch `--headless=chrome` to restore screenshot collection on Linux CI).

**(3) LCP gate HOLD `warn@2500ms` — mobile throttling reality**

Worst cross-session median LCP = 2895ms on /. Above the 2500ms ceiling. CI Linux devtools throttling (4× CPU + Slow 4G) is structurally harsher than Windows wrapper baselines — same dist measured 2000ms on Windows wrapper (W159 SW2) vs 2895ms on Linux CI. This is the REAL mobile-grade measurement; the Windows wrapper number was the lenient one. Ratchet warn→error would block merges; hold until perf work lands (W161+ candidate via SSR Phase 5 mobile optimizations OR Lighthouse throttling adjustment).

**(4) TBT gate HOLD `warn@200ms` — same mobile throttling reality**

Worst TBT = 549ms on /. Above 200ms ceiling. Same structural reasoning as LCP.

### Implementation

Commit `44b33c230` `chore(wave160-sw2-lhci-ratchet)`:
- Edited [`frontend/scripts/run-lhci.mjs:206-289`](frontend/scripts/run-lhci.mjs:206) inline assertions
- Changed `"cumulative-layout-shift": ["error", { maxNumericValue: 0.1, aggregationMethod: "median" }]` → `{ maxNumericValue: 0.05, aggregationMethod: "median" }`
- Added 47-line comment block documenting W160 SW2 cross-session medians + ratchet decision lineage + structural Perf blocker rationale
- Preserved comment history (routine-e5 + W118 SW5 + W119 SW3 + W120 SW2 + W124 SW4)

### Aggregate script

Scratch `frontend/scripts/wave160-aggregate-lhci.mjs` (~280 LoC) was created at SW2 start to compute cross-session medians from 81 LHRs. Deleted at SW4 cleanup per W119 SW2 / W120 SW1 / W134 SW3 convention — the data + decisions are preserved in this audit + the SW2 commit body.

---

## SW3: MEMORY.md W158 row compaction — DONE

Per W157 SW3c + W158 SW3 + W159 SW3a rolling-pattern convention. Compacted W158 verbose row (2,817 chars at MEMORY.md:21) to one-liner format mirroring W156 / W155 / W154 compact rows.

- Pre-SW3: MEMORY.md = 22,840 b; W158 row = 2,817 chars
- Post-SW3: MEMORY.md = **21,050 b** (-1,790 b / -7.8%); W158 row = **1,027 chars** (-1,790 chars / -63.5%)
- Headroom from 24,400 ceiling: **3,350 b** (well above plan's projected 1.16 KB)
- No git commit (memory file lives in user `.claude` profile only — W138 polish-followup convention)

W160 verbose row addition in SW4 (~1,800-2,300 chars expected) will push to ~23,000 b — still 1.4 KB under ceiling.

---

## SW4: Audit + memory + N+3 rotation + W161 handoff — THIS COMMIT

### Files created / modified

1. NEW [`docs/audits/AUDIT_WAVE160.md`](docs/audits/AUDIT_WAVE160.md) — this audit
2. MODIFIED `CLAUDE.md ## Audit Trail` — W160 row at top (concise per W134 user-feedback lesson; ~2,000-2,500 chars)
3. MODIFIED [`docs/audits/INDEX.md`](docs/audits/INDEX.md) — active table replaces W157 with W160; rotation history appends "W160 SW4 (W157 → archive)"
4. **N+3 rotation**: `git mv docs/audits/AUDIT_WAVE157.md docs/audits/archive/AUDIT_WAVE157.md` per W122 polish-docs-v3 covenant
5. MODIFIED `memory/MEMORY.md` (user .claude profile) — added W160 verbose row + updated active wave references (W158/W159/W160)
6. NEW `memory/wave160_backlog.md` (user .claude profile)
7. NEW `memory/wave161_opening_prompt.md` (user .claude profile)
8. DELETED `frontend/scripts/wave160-aggregate-lhci.mjs` (SW2 scratch)

---

## Verification matrix

| Check | Pre-W160 baseline | Post-W160 actual | Status |
|-------|-------------------|--------------------|--------|
| tsc | 0 errors | 0 errors | ✅ |
| eslint (max-warnings=0) | 0 warnings | 0 warnings | ✅ |
| prettier format:check | clean | clean (post scratch-script delete) | ✅ |
| vitest | 1058p/12s/0f (W159 baseline) | **1058p/12s/0f** in 28.71s | ✅ EXACT |
| npm audit | 0 vulnerabilities | 0 vulnerabilities | ✅ |
| Cargo.lock drift | none (idempotent ≥25 waves) | none | ✅ |
| Docker stack | 4 (healthy) + caddy no-hc | 4 (healthy) + caddy no-hc | ✅ |
| /healthz | `{"status":"ok"}` | `{"status":"ok"}` | ✅ |
| /login SSR HTTP | 200 / 21,791 b (W158 ±59) | 200 / **21,732 b** (matches W157 baseline exactly) | ✅ |
| LHCI gate ratcheted | CLS error@0.10 | **error@0.05** | ✅ APPLIED |
| 81 LHRs captured | N/A | 81 LHRs (9 URLs × 3 runs × 3 sessions) | ✅ COMPLETE |
| MEMORY.md size | 22,840 b | 21,050 b post-SW3 | ✅ |
| Build × 3 sha256 | main JS `b417bace...c0a2`, server.js `304095c1...4ac` BYTE-IDENTICAL × 3 (W134-W159 ≥25-wave invariant) | **EMPIRICALLY VERIFIED post-SW4 polish-pass**: main JS `b417bace9893d6f9d61a8e2743a786edc7cc42173fa2a2d5cdc65a47f4e1c0a2` + server.js `304095c1fa3296583c6edd5db5d70d621b9b8f33fb9b2786ebdbf1ea0cfe34ac` BYTE-IDENTICAL × 3 runs (`b417bace...c0a2` + `304095c1...4ac` match W159 baseline EXACTLY) | ✅ INVARIANT EXTENDS TO ≥26 WAVES |

**Build × 3 re-verification — polish-pass empirical extension** (2026-05-17 post-«безупречно?» probe): originally deferred per structural argument (W160 SW2 changed only `run-lhci.mjs` assertion thresholds, NOT production build pipeline). Post-SW4 polish-pass executed `BUILD_SKIP_PWA=true npm run build` × 3 anyway as defensive validation per user's "безупречно?" probe. **Result**: main JS sha256 + server.js sha256 BYTE-IDENTICAL across 3 runs AND match W134-W159 baseline EXACTLY (`b417bace...c0a2` + `304095c1...4ac`). The W134 SW3-W159 ≥25-wave invariant **EXTENDS through W160 → ≥26-wave BYTE-IDENTICAL invariant** empirically confirmed (not just structurally preserved). Each build ~22s wall-clock; total polish-pass build budget ~70s.

---

## §Honesty trajectory

**Pre-W160**: 5-8 OPEN (post-W159 close)

### Closures (2)

1. **W134 §Honesty #1** (LHCI baseline framing long-overdue per opening prompts since W117 SW8) — CLOSED via 3-session × 3-run methodology application with full per-URL × per-metric data captured for 9 URLs × 81 LHRs.

2. **W159 NEW #2** (LHCI measured 4 of 9 URLs in W159 SW2 Windows wrapper) — CLOSED via 9-URL full sweep × 3 sessions on Linux CI runner.

### Carryforward (4)

- W134 §Honesty #2 — bundle delta carry (honest framing recording; no action needed)
- W134 §Honesty #10 — /messenger Phase 5 punted (W161+ Tier 2 candidate)
- W156 §Honesty caveat on chrome-devtools-mcp Windows snapshot wall (W137+ pending tool-level investigation)
- W159 NEW #1 — LHCI wrapper Windows cleanup hang (W161+ structural fix candidate; CI Linux methodology in W160 sidesteps this but doesn't fix the wrapper itself)

### NEW W160 caveats (2)

1. **Perf measurement structurally blocked on Linux CI** — `chromeFlags: --headless=new --disable-gpu` prevents screenshot collection → `categories.performance.score = null` across all 81 LHRs. Routine-e5 calibration drift PARTIALLY closed via SW2 documentation; full closure pending W161+ chrome flags investigation (~30-60 min wave to drop `--disable-gpu` or switch `--headless=chrome`, then re-run 1 LHCI sweep to confirm Perf scores populate).

2. **LCP + TBT gates HOLD at warn** — worst measurements (LCP 2895ms on /; TBT 549ms on /) exceed current ceilings (2500ms; 200ms). Mobile devtools throttling on Linux CI is harsher than Windows wrapper. Ratchet warn→error would block merges; held until perf work lands (separate from chrome-flags fix; mobile performance optimization wave).

**Post-W160**: 5-8 → **5-8 OPEN** (net ZERO range; 2 closures + 2 NEW = structural narrowing, not numerical change)

The opening-prompt projection was "3-6 OPEN target". W160 actual is 5-8 — slightly higher due to the 2 NEW caveats discovered empirically (per `feedback_perfectionism.md` honest framing). Net SCOPE is narrower than W160 start (W134 #1 + W159 NEW #2 are big-ticket closures; the 2 NEW caveats are well-scoped W161+ candidates).

---

## (z) Path discoveries (W141 anti-pattern #3 vindications)

**2 NEW (z) discoveries**, both within SW1 iter 1 (per W138 Lesson #1: empirical findings disprove plan assumptions — course-correct within iter, not separate iter pivots):

### (z) #1: `actions/upload-artifact@v7.0.1` `include-hidden-files: false` default

Opening prompt and W129 SW6 framing claimed `lhci-linux.yml` worked end-to-end since 2026-05-09 creation. Empirical: artifact upload had been silently broken for hidden-dir contents (which is exactly where `@lhci/cli` writes its LHR JSONs).

**W141 anti-pattern #3 17th vindication**. The previous failed runs on 2026-05-09 (run IDs `25588904029` + `25588722320`, both `failure` per `gh run list` history) hit upstream PAGE_HUNG before reaching the upload step, masking this latent bug for 8 days.

### (z) #2: `LHCI_URLS=""` overrides 9-URL default to single root

Workflow input description claims "empty = full default 9-URL sweep" but `process.env.LHCI_URLS?.split(",")` on `""` produces `[""]` → maps to `["/"]` → truthy → overrides defaults. Documentation-vs-behavior gap.

**W141 anti-pattern #3 18th vindication**. The 2026-05-09 failed runs also exercised this path (LHCI_URLS="" via workflow_dispatch default), but failed at lighthouse-collection step before the URL-narrowing showed in any summary.

### NEW Linux CI screenshot blocker (NOT counted as (z) — surfaced empirically during analysis)

W160 SW2 LHR inspection revealed Chrome headless under `--headless=new --disable-gpu --no-sandbox` fails to collect screenshots. This is a known Lighthouse 13.x + Chrome flag interaction (per W117 polish-A2 / W124 SW4 lessons about CI Linux measurement environment). Documented as W160 NEW caveat #1 + W161+ candidate.

---

## W141 anti-pattern register status

Register: **14 patterns** (post-W159 SW4 formal archival of #15). W160 stable — no NEW patterns introduced.

### Vindications this wave

| # | Anti-pattern | W160 vindication # | Detail |
|---|---|---|---|
| 1 | Iterate past STRICT 1-iter cap per Tier option | **14th** | SW1 had 2 sub-bug-fix course-corrections within iter 1 (per W138 Lesson #1, NOT pivots); SW2 single iter applied; SW3 + SW4 single iter each. No iter exhaustion. |
| 3 | Trust Agent / opening-prompt claims without verification | **17th + 18th** | Phase 3 empirical verification surfaced BOTH latent infrastructure bugs (artifact upload v7; LHCI_URLS empty-string). |
| 4 | Premature "Closes §Honesty #X" claim | **15th** | Closures attributed AFTER 81-LHR data captured + ratchet applied + SW2 commit landed. The 2 closures (W134 #1 + W159 NEW #2) are empirically backed. |
| 6 | Skip pre-flight checklist when scope feels small | preserved | All 12 pre-flight steps ran at Phase 1 |
| 11 | Assume cross-platform without empirical verification | preserved | CI Linux measurement IS the empirical verification of cross-platform LHCI behavior vs Windows wrapper |
| 15 | (ARCHIVED W159 SW4) | preserved | All W160 commits fired W156 SW4 hook chain cleanly; no `--no-verify`; lint-staged + pre-commit Python tool ran on each commit |

---

## Lessons for W161+

### Reuseable patterns from W160

1. **3-session × 3-run methodology yields tight variance band post-SSR** — per W124 SW4 predicted ±0.04-0.06 cross-session variance; W160 measured ±0.01-0.05 actual. The SSR Phase 5 stability + canonical PROD bundle minified delivery make the measurement environment more deterministic. Future LHCI ratchet decisions can confidently use 3-session × 3-run on Linux CI without expecting wider variance.

2. **Linux CI workflow_dispatch sequential triggers respect `cancel-in-progress: true`** — total wall-clock ~75 min for 3 sessions (each ~24 min). Acceptable cost for ratchet-grade data.

3. **Empirical LHR inspection via `node -e` is critical for null-score diagnosis** — the aggregate script alone showed "Perf -" but didn't explain WHY. Inspecting `lhr.audits.speed-index.errorMessage` directly revealed the Chrome screenshot blocker. Future LHCI audits should include this diagnostic step when scores look anomalous.

4. **Course-correction within iter is NOT anti-pattern #1 violation** — per W138 Lesson #1. The 2 SW1 sub-fixes (artifact upload v7 + LHCI_URLS empty-string) shipped within iter 1; SW2 stayed iter 1. Per W141 anti-pattern #1 definition, "iter 2" = "different mechanism after iter 1 mechanism fails". Both SW1 fixes were SAME mechanism (workflow_dispatch + artifact download) with config fixes for latent bugs — not pivots.

5. **MEMORY.md rolling compaction headroom-track**: W160 SW3 freed 1,790 b (-7.8%); current ceiling headroom 3,350 b. W161 SW4 will need to compact W159 row (next oldest after W160 close).

### W161+ candidates (3-wave-horizon outlook)

**W161 (~2-4h core, MEDIUM confidence)**:
- **Tier 1: Lighthouse chrome flags fix** — drop `--disable-gpu` from `run-lhci.mjs:130` OR switch `--headless=new → --headless=chrome` to restore screenshot collection on Linux CI. Then re-run 1 LHCI sweep × 3 runs to confirm Perf scores populate. If they do, apply Perf ratchet (likely `warn@0.40 → error@0.40` minimum closure of routine-e5 calibration drift). ~30-60 min focused; **closes W160 NEW #1 + closes routine-e5 fully**.
- **Tier 1 alt: Windows LHCI wrapper hang investigation** — W159 NEW #1 + W126 polish #3 + vite-plugin-pwa Windows hang family. File upstream issue OR migrate to native Workbox CLI step. ~3-5h structural; closes W159 NEW #1.
- **Tier 4: MEMORY.md rolling compaction** — W159 row (1,557 chars verbose) becomes oldest of "3 most-recent" after W161 closes. Compact to ~1,000-1,200 chars per W156 template.

**W162 (~2-4h core, LOW confidence — depends on W161)**:
- **Tier 2: /messenger × 2 SSR enable OR explicit defer** — last `ssr: false` opt-down siblings per W127 SW6 / W130 SW2 / W133 SW3-SW5 SSR continuation pattern. Closes W134 #10.
- **Tier 3 build infra**: vite-plugin-pwa Windows hang structural fix (W126 polish #3 + W159 NEW #1 root cause).

**W163+ (depends on W161-W162 outcomes)**:
- If Perf gate fully ratcheted post-W161 + all original SSR opt-downs closed → production canary documentation per W132 SW6 runbook + Phase 6 rollout readiness.
- If /admin polish arc resumed → W150 SW1-SW4 already on disk; estimated 3-5 more SWs per historical anchoring (Schedule 14, Map 23, Events 6, Activity 4, News 6, Dashboard 10).

**§Honesty target W163**: 1-4 OPEN.

**Discipline streak projection**: 24 consecutive waves by W163 close (W134-W163).

---

## Reference

- **PR**: https://github.com/egorribun/university_ecosystem/pull/1114
- **CI status**: `gh run list --branch=egorribun --limit=12` (SW2 commit `44b33c230` CI firing at audit-write time)
- **W160 SW1 fix commits**: `7ca2b63eb` + `c5ad2f425`
- **W160 SW2 ratchet commit**: `44b33c230`
- **W160 LHCI runs**:
  - Session #1: https://github.com/egorribun/university_ecosystem/actions/runs/25988551157
  - Session #2: https://github.com/egorribun/university_ecosystem/actions/runs/25989078530
  - Session #3: https://github.com/egorribun/university_ecosystem/actions/runs/25989579477
- **Earlier failed/cancelled runs** (sources of bug discoveries): `25988283380` (artifact upload v7 bug), `25988414129` (cancelled mid-flight), `25988491091` (LHCI_URLS empty-string bug)
- **Plan file**: `C:\Users\egorribun\.claude\plans\c-users-egorribun-claude-projects-c-use-fuzzy-panda.md`
- **W159 audit**: [docs/audits/AUDIT_WAVE159.md](AUDIT_WAVE159.md)

---

**End of W160 audit. Active waves post-W160: W158 / W159 / W160. N+3 rotation: W157 → archive in SW4 commit.**
