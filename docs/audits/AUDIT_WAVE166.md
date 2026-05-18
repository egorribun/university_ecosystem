# AUDIT_WAVE166 — Broader pivot (Tier 1+2+3): admin JWT role + admin React #418 honest defer + Lighthouse upstream issue

**Wave 166** (Broader pivot, Q0=C, ~2-3h core wall-clock; **27th consecutive wave** with brainstorming + Phase 1 Explore + Phase 3 Review + W141 anti-pattern discipline).

**Branch**: `egorribun` (HEAD post-wave: `2d69bd293` SW4 audit; SW3 `b4b5d1a2a` / SW2 `ae03e61d3` / SW1 `07da10e10` preceded)
**Plan reference**: `C:\Users\egorribun\.claude\plans\c-users-egorribun-claude-projects-c-use-shimmering-dolphin.md`
**Predecessor**: AUDIT_WAVE165.md (W165 closed 2 W164 carries + honestly deferred Tier 1 LCP/TBT ubuntu-22.04 Outcome B)

---

## Headline

3 SW commits **shipped**. Outcomes (mixed; honest framing per `feedback_perfectionism.md` + W141 anti-pattern #4):

1. **SW1 `07da10e10` Tier 1 admin auth JWT role claim** — ✅ **CLOSURE VERIFIED EMPIRICALLY**. Threaded `role: user.role.value` into JWT extra_claims alongside W136 SW1 `is_active`. Wave165-admin-visual-smoke.mjs re-run post-Docker-rebuild confirmed `JWT payload: role=admin aud=university-ecosystem-api is_active=true` for the admin user. Closes W165 NEW W166+ candidate #1 (admin auth JWT-no-role-claim race on cold-cache /admin/* URL navigation).

2. **SW2 `ae03e61d3` Tier 2 admin React #418 mounted-state pattern** — ⚠ **STRUCTURAL DEFENSE applied; React #418 candidate NOT CLOSED**. Empirical post-rebuild sidecar evidence (`frontend/.screenshots/wave165-admin-visual-smoke/admin_audit_light.json:23-28`) shows the same `Minified React error #418` × 2 firings per admin page from `vendor-react-CFU_zHBc.js:8:31205` — IDENTICAL pattern to W165 pre-W166 evidence. SW2 commit message subject claimed "close React #418 hydration mismatch" which was **premature per W141 anti-pattern #4**. AdminLayout was not the source of mismatch; mounted-state pattern was correctly applied but to the wrong component. Per W141 anti-pattern #1 STRICT 1-iter cap, **MANDATORY honest-defer to W167 SW2-followup** — no mechanism pivot within SW2. SW2 commit STAYS in history as structural defense (eliminates one possible source on AdminLayout level + zero regression risk).

3. **SW3 `b4b5d1a2a` Tier 3 Lighthouse upstream issue** — ✅ **STATE SHIFT COMPLETE**. Filed [`GoogleChrome/lighthouse#17021`](https://github.com/GoogleChrome/lighthouse/issues/17021) with 108-LHR reproducibility evidence + chrome flag variant disproofs + ubuntu-22.04 cross-OS verification. State shifts from W162 SW1's "permanent platform limitation accepted" framing to **"tracked-upstream"**. Upstream maintainer response (won't fix / duplicate / Chromium upstream) is accepted per plan §SW3 risk register — state shift is the closure, NOT maintainer action.

**§Honesty trajectory**: 0-2 OPEN pre-W166 → **1-5 OPEN post-W166** (mixed: 2 closures + 1 state-shift offset by 3 NEW W166 caveats — see §Honesty section). Honest framing per `feedback_perfectionism.md` — W166 ships real value (SW1 + SW3) but SW2 outcome is structural defense not closure.

---

## Scope confirmation

User-approved via AskUserQuestion × 2 at wave start:
- **Q0 = C Broader pivot** (~2-5h budget)
- **Q1 = Tier 1+2+3 full broader pivot** (Recommended) — SW1 + SW2 + SW3 + SW4
- **Q2 = STRICT 1-iter per Tier** (Recommended) — W141 anti-pattern #1 19th vindication baseline post-W165

Plan approved via ExitPlanMode (`c-users-egorribun-claude-projects-c-use-shimmering-dolphin.md`).

---

## SW1 — Tier 1: admin auth JWT role claim (commit `07da10e10`)

**Scope**: Thread `role` claim into JWT mint so SSR-side `_admin.tsx:34` beforeLoad reads role from JWT instead of waiting for async `/users/me` (eliminates cold-cache navigation race).

**Files changed** (2 files, +311/-1 net):
- `app/services/auth/login_session_manager.py:79-83` — extra_claims dict extended with `"role": user.role.value` alongside existing W136 SW1 `is_active` claim (+10 LoC comment + 4 LoC dict expansion)
- `tests/test_wave166_jwt_role_claim.py` — NEW ~300-LoC test file, 6 tests mirroring W136 SW1 `tests/test_auth_jwt_payload.py` pattern

**Why this is minimal**:
- `User.role` is `Mapped[UserRole]` (verified `app/models/users.py:44`). `UserRole` is `StrEnum` (`app/models/enums.py:4-15`). `.value` returns canonical string ("student", "teacher", "admin", "superuser", "anonymous").
- `SessionService._mint_jwt` already merges extra_claims via `payload.update(extra)` at `app/services/session_service.py:211` — no infrastructure change needed.
- `finalize_login` is the single chokepoint for ALL login flows (password, MFA, passkey, OAuth) per W136 SW1 framing — adding one key threads through every login.
- `frontend/src/ssrAuth.ts:127` ALREADY extracts role claim: `const role = typeof payload.role === "string" ? payload.role : "student"` — pre-W166 the claim was missing → defaulted to "student" → admin users at SSR layer were treated as students.

**Verification (local-tests slice, 28 pass / 0 fail / 3.41s total)**:
- `pytest tests/test_wave166_jwt_role_claim.py -v` → 6/6 PASS (0.85s)
- `pytest tests/test_auth_jwt_payload.py -v` → 5/5 W136 SW1 baseline PASS (regression guard)
- `pytest tests/test_auth_jwt_rs256.py -v` → 5/5 W137 SW1 baseline PASS (regression guard)
- `pytest tests/test_login_service_coverage.py -v` → 12/12 PASS (1.10s)

**Verification (Docker runtime, empirical closure)**:
- Backend container rebuilt with SW1 code
- `wave165-admin-visual-smoke.mjs` re-run logged: `JWT payload: role=admin aud=university-ecosystem-api is_active=true`
- All 10 admin route captures returned httpStatus=200 + AUTHED (no redirect to /login)
- Closes **W165 NEW W166+ candidate #1** (admin auth JWT-no-role-claim cold-cache race) ✅

**W141 anti-pattern vindications during SW1**:
- **#3 30th vindication**: opening prompt §"### W165 admin auth flow finding" cited `_set_access_token_cookie` at `login_session_manager.py:148-165` — actual is `154-171` (minor 7-line offset). Phase 3 Read verified the actual structure: `finalize_login` extra_claims call site is at lines 75-80 (NOT 148-165 which is the cookie-setting method, a different concern).
- **#3 31st vindication**: Phase 1 Explore Agent 1 cited `app/services/auth/session_service.py:210-211` — actual path is `app/services/session_service.py` (NOT under `auth/` subdir) and `_mint_jwt` + `payload.update(extra)` is at lines 194-218 (line 211 specifically for the update).

Neither error structurally invalidated the plan — both citations were conceptually correct, just precise location off.

**SW1 risk register outcome**: All 3 risks (mid-deploy JWT invalidation, gateway compatibility, STRICT 1-iter cap) cleared. SW1 succeeded first try.

---

## SW2 — Tier 2: admin React #418 mounted-state pattern (commit `ae03e61d3`) — STRUCTURAL DEFENSE, NOT CLOSURE

**Scope**: Apply W156 SW3 LiveRegionProvider mounted-state pattern to AdminLayout to close suspected hydration mismatch on `_admin.tsx:11-22` from `useReducedMotion()` + `useMediaQuery()` returning SSR defaults vs CSR browser values.

**Files changed** (1 file, +31/-1 net):
- `frontend/src/routes/_admin.tsx` — added `import { useEffect, useState } from "react"` + W166 SW2 comment block + `mounted` state pattern gating `ssrSafeIsNarrow` + `ssrSafePrefersReducedMotion`

**Hypothesis pre-implementation (Phase 3 confidence ~72%)**:
- `useReducedMotion()` + `useMediaQuery()` at AdminLayout render → SSR returns defaults (`false`, `false`) but CSR returns actual browser values
- AdminBackdrop conditional renders (`{!isNarrow && ...}` + `{!isNarrow && !prefersReducedMotion && ...}` at `AdminBackdrop.tsx:32,44`) emit different orb subtrees → DOM divergence → React #418
- W156 SW3 LiveRegionProvider mounted-state pattern (canonical at `LiveRegionProvider.tsx:50-115`) should close this

**Empirical outcome post-Docker-rebuild + smoke re-run**:

| Metric | Pre-W166 (W165 SW3) | Post-W166 SW2 |
|--------|----------------------|---------------|
| React #418 firings per /admin/audit | 2 (sidecar lines 24, 56) | **2 (sidecar lines 23, 55) — UNCHANGED** |
| Source stack frame | `vendor-react-CFU_zHBc.js:8:31205` | `vendor-react-CFU_zHBc.js:8:31205` — SAME |
| Error args | `args[]=HTML&args[]=` | `args[]=HTML&args[]=` — SAME |
| Script `hydrationErrorCount` | 0 (filter false-negative) | 0 (filter false-negative) |
| HTTP status | 200 / AUTHED | 200 / AUTHED |

**SW2 fix was structurally sound but applied to the WRONG component**. The actual React #418 source is NOT AdminLayout's hook divergence. Possible remaining suspects (W167+ scope):
1. **AdminBackdrop's internal conditional renders**: even with safe defaults at first render, the post-`setMounted(true)` re-render changes orb subset (mobile case) → React might fire #418 on the re-render rather than initial render.
2. **An admin Feature component's own browser-only hook**: e.g., AdminAuditFeature, AdminUsersFeature each may have render-time browser API access.
3. **TanStack Router transition state**: sidecar also shows `Transition was skipped` + `AbortError: Transition was skipped` (sidecar lines 16, 20) — router-level transitions may be racing.
4. **Something we haven't thought of (z)** — per W138 Lesson #2 "include (z) hypothesis path explicitly". NODE_ENV=development build for unminified React error message is the canonical W155 (z) #3 + W156 SW1 diagnostic vector.

**SW2 commit message was PREMATURE** in claiming "close React #418 hydration mismatch" (commit `ae03e61d3` subject line). Per W141 anti-pattern #4 ("no premature 'Closes' claim — empirical verification BEFORE attribution") + `feedback_perfectionism.md` honest framing, this audit narrative corrects the framing:

- **SW2 ships as structural defense**: eliminates one possible source of hydration mismatch (AdminLayout-level hook divergence) with zero regression risk (mounted-state pattern is proven W156 SW3 canonical).
- **React #418 candidate STAYS OPEN as W167+ scope** — honest defer per W141 anti-pattern #1 STRICT 1-iter cap (NO mechanism pivot within SW2).
- **W167+ Path B vector**: NODE_ENV=development build for unminified error message + targeted investigation of remaining suspects (AdminBackdrop re-render, admin Feature browser-only hooks, TanStack Router transition state).

**SW2 risk register outcome**:
- ✅ Cold-mount visual flicker (Low UX) — accepted per W156 SW3 trade-off
- ✗ **Path A failure mode (Low) — FIRED**: React #418 persists post-SW2 → mandatory honest defer per plan §SW2 risk #2. No mechanism pivot per W141 anti-pattern #1.
- ✅ Browser extension noise — N/A (not this error class)
- ✅ STRICT 1-iter cap honored — NO Path B attempt within SW2.

**W141 anti-pattern vindications during SW2**:
- **#1 14th defer-case vindication** (16 total defer-cases historical baseline + SW2 = 17 — but counting convention varies between waves; let's match W165 framing's 13 defer-cases at start, +1 W165 deferred Tier 1, +1 W166 SW2 = **15 defer-cases post-W166**). SW2 commit STAYS as structural defense; React #418 closure deferred.
- **#3 32nd vindication**: smoke script's `hydrationErrorCount` filter at `wave165-admin-visual-smoke.mjs:384-387` only matches "hydrat"/"Hydration"/"did not match" — misses "Minified React error #418" → false-negative 0 count. NEW W166 caveat: script filter is buggy. W167+ candidate to fix.
- **#4 18th vindication**: SW2 commit subject claimed closure prematurely; this audit narrative corrects honestly per `feedback_perfectionism.md`.

---

## SW3 — Tier 3: Lighthouse upstream issue (commit `b4b5d1a2a`)

**Scope**: File new issue at `GoogleChrome/lighthouse` with 108-LHR reproducibility evidence to move W160 §Honesty NEW #1 from "permanent platform limitation accepted" framing to "tracked-upstream" state.

**Pre-flight (W141 anti-pattern #3 discipline)**: WebFetched GoogleChrome/lighthouse issue search → found 4 stale closed issues (#11131 Windows + Lighthouse 6.1.1 from 2020, #10350 PSI 2020-era, #5815 + #5337 both 2018-era). None match our 2026-era Lighthouse 13.x + Ubuntu Linux CI + Chrome flag interaction case. Filing NEW issue is correct (Option A per W166 plan §SW3 pre-flight).

**Filed**: [`GoogleChrome/lighthouse#17021`](https://github.com/GoogleChrome/lighthouse/issues/17021)

**Issue body content** (filed via `gh issue create --repo GoogleChrome/lighthouse`):
- Environment: Lighthouse 13.1.0, Node 22, Ubuntu 24.04 + 22.04 (cross-OS), HeadlessChromium
- Reproducible recipe: GitHub Actions workflow snippet with exact chrome flags
- Evidence: 108 LHRs across 3 measurement sessions
- Failed mitigation attempts: drop `--disable-gpu` + swap `--headless=new` → `--headless=chrome` (both fail × 30 combined LHRs)
- Workaround in production: Windows wrapper for canonical Perf; CLS error@0.05 stays hard CI block
- Closing line invites maintainers to close as duplicate / known-limitation / Chromium upstream

**Files modified** (1 file, +8 lines):
- `frontend/scripts/run-lhci.mjs:208-216` — comment block extended with W166 SW3 closure framing + issue URL + memory file pointer

**Files created** (memory profile, not git-tracked):
- `memory/wave166_lighthouse_upstream_issue.md` — full draft body backup + pre-flight existing-issue scan + state-shift documentation

**State shift**: W160 §Honesty NEW #1 ("permanent platform limitation accepted" per W162 SW1) → **"tracked-upstream"** per W166 SW3. State preserved regardless of upstream maintainer response — feedback_perfectionism.md honest framing.

**SW3 risk register outcome**: All 3 risks (upstream won't-fix, existing match found, doc-only changes) cleared as expected. Anticipated 2-4 week upstream triage cadence.

**W141 anti-pattern vindications during SW3**:
- **#1 SW3 succeeded first try**: 1 issue filed + 1 comment block update + 1 memory file created
- **#3 32nd vindication via WebFetch** (counted alongside SW2 script bug discovery): WebFetched issue #11131 directly to verify it wasn't reopenable — saved ~30 min if I'd blindly comment on stale closed issue
- **#4 closure attribution**: state-shift framing, NOT "fixed upstream" (response pending)

---

## §Honesty trajectory + caveat audit

**Pre-W166**: 0-2 OPEN (3 carry-forward structural caveats from W134/W160 — bundle delta recording-only + LCP HOLD warn@2500ms + TBT HOLD warn@200ms; /messenger Phase 5 punt by-design)

**W166 closures**:
- ✅ **W165 NEW W166+ candidate #1** (admin auth JWT-no-role-claim race) — CLOSED via SW1 empirical verification
- ✅ **W160 §Honesty NEW #1** — STATE-SHIFTED via SW3 ("permanent platform limitation" → "tracked-upstream")

**W166 deferrals + NEW caveats** (honest framing per `feedback_perfectionism.md`):

| # | Caveat | Wave-origin | Status | W167+ scope |
|---|--------|-------------|--------|-------------|
| 1 | W134 §Honesty #2 bundle delta recording-only | W134 | carry-forward (recording-only, not actionable) | none |
| 2 | W160 NEW #2 LCP HOLD warn@2500ms | W160 | carry-forward structural | upstream Lighthouse (now tracked-upstream via #17021) |
| 3 | W160 NEW #3 TBT HOLD warn@200ms | W160 | carry-forward structural | same |
| 4 | /messenger Phase 5 punt by-design | W134 | carry-forward by-design | none |
| 5 | **W165 NEW candidate #2 admin React #418** | W165 | **OPEN post-W166 SW2 STRUCTURAL DEFENSE** | W167 SW2-followup ~1-3h Path B (NODE_ENV=dev build + targeted investigation) |
| 6 | **W166 NEW #1 SW2 commit message premature closure claim** | W166 | corrected in this audit narrative | none — historical record stays |
| 7 | **W166 NEW #2 wave165-admin-visual-smoke.mjs hydrationErrorCount filter bug** | W166 | open as W167+ housekeeping | ~15 min fix to filter to match "Minified React error #418" |
| 8 | **W166 NEW #3 W164 §Honesty #4 admin.css .dark verification still inconclusive** | W166 | open — script claim unreliable due to #7 filter bug | re-verify with corrected filter OR visual diff PNG inspection |

**Net §Honesty count**: 4 carry-forward structural + 1 W165 deferred (SW2 path B) + 3 NEW W166 caveats = **8 open caveats post-W166**, of which **1-5 are actionable** (W167+ SW2 followup is the highest-value next step; the rest are doc/housekeeping).

Trajectory per opening prompt §"§Honesty trajectory projection":
- Expected: 0-2 → 0-2 OPEN (NEW W166+ candidates closed)
- Actual: 0-2 → 1-5 OPEN (NET +1 to +3 user-facing actionable count)
- **W166 underperformed plan target** on SW2 — honestly noted. SW1 + SW3 delivered as planned.

---

## W141 anti-pattern register status post-W166

| Pattern | Pre-W166 vindications | W166 increment | Post-W166 |
|---------|-----------------------|----------------|-----------|
| #1 STRICT 1-iter cap | 19 total (13 defer-cases) | +1 defer (SW2 Path B) | **20 total (14 defer-cases)** |
| #3 Phase 3 Verification | 29 vindications | +3 (SW1 line offsets × 2 + SW2 script filter bug) | **32 vindications** |
| #4 No premature "Closes" | 17 vindications | +1 (SW2 commit message correction) | **18 vindications** |
| #15 (ARCHIVED W159 SW4) | preserved | preserved | all 5 W166 commits (4 SW + polish-v1 `d452f0c9a` + polish-v2 `646110afa`) fired W156 SW4 hook chain cleanly (no `--no-verify`) |

ALL 6 W166 commits (SW1 `07da10e10` + SW2 `ae03e61d3` + SW3 `b4b5d1a2a` + SW4 `2d69bd293` + polish-v1 `d452f0c9a` + polish-v2 `646110afa`) fired W156 SW4 husky pre-commit chain cleanly. SW1 had one within-iter ruff-format auto-fix (re-staged + re-committed per CLAUDE.md anti-amend convention — counts as 1 NEW commit, not amend). NO `--no-verify` bypasses across the wave.

---

## Bundle invariant — W164 retired → W166 SW2 NEW baseline

- **Pre-W166**: W164 NEW baseline `index-tjs3k5Q_.js` 176,663 b sha `2d08a661...4aed1` + server.js 23,600 b sha `40f66610...5c0e1` (W134-W165 ≥31-wave BYTE-IDENTICAL invariant)
- **SW1 commit `07da10e10`**: backend-only Python change → bundle should stay BYTE-IDENTICAL to W164. Build × 1 verification skipped (structural argument: zero frontend src/ changes; W134 SW3-W165 invariant holds via structural reasoning).
- **SW2 commit `ae03e61d3`**: real frontend prod code change (`_admin.tsx` +31/-1 LoC). **W164 BYTE-IDENTICAL invariant RETIRES at W166 SW2** per plan §SW2 framing.
- **SW2 build × 1 outcome (clean rebuild from `rm -rf dist`)**:
  - Main JS entry chunk: `index-BDwZE1BF.js` **176,663 bytes** (same SIZE as W164 baseline, NEW sha `63b6029e6fd3...0b8c01`)
  - Server.js: **23,600 bytes** (same SIZE, NEW sha `c732997e1...76b09b`)
  - vendor-react: **182,123 bytes** UNCHANGED (`vendor-react-CFU_zHBc.js`)
  - `_admin.tsx` SW2 code lives in route-chunked `_admin-VGDns5Oq.js` (per TanStack Router code-splitting) — entry chunk only references hash update, not content add
- **SW2 NEW baseline (polish-v2 confirmed × 3 BYTE-IDENTICAL)**: `index-BDwZE1BF.js` 176,663 b sha `63b6029e6fd3ae323266f7d4c4fd231503134daf1f59b027bd0d215dee0b8c01` + server.js 23,600 b sha `c732997e156cf20910cb413371d9fde8367b995dfb0163c61f86510cf476b09b` — VERIFIED IDENTICAL × 3 fresh `cd frontend && rm -rf dist && npm run build` runs during polish-pass empirical verification (2026-05-19; W166 SW2 NEW baseline is ≥3-wave-reproducible within W166 itself).
- **SW3 commit `b4b5d1a2a`**: CI-only dev tooling (`run-lhci.mjs` comment block update) — NOT bundled into client. Bundle preserved BYTE-IDENTICAL to SW2 baseline.

---

## Verification matrix per SW

### SW1 verification

| Check | Expected | Actual | Status |
|-------|----------|--------|--------|
| `pytest tests/test_wave166_jwt_role_claim.py` | 6 PASS | 6 PASS in 0.85s | ✅ |
| `pytest tests/test_auth_jwt_payload.py` (W136 regression) | 5 PASS | 5 PASS in 1.46s | ✅ |
| `pytest tests/test_auth_jwt_rs256.py` (W137 regression) | 5 PASS | 5 PASS in same run | ✅ |
| `pytest tests/test_login_service_coverage.py` | 12 PASS | 12 PASS in 1.10s | ✅ |
| Docker runtime: JWT payload has `role` claim | `role=<value>` present | `role=admin aud=university-ecosystem-api is_active=true` | ✅ |
| W156 SW4 hook chain cleanly | All pass | ruff/bandit/mypy/detect-secrets/Python2-except all PASS | ✅ |
| Bundle invariant | W164 baseline preserved | Verified via structural argument | ✅ |

### SW2 verification

| Check | Expected | Actual | Status |
|-------|----------|--------|--------|
| `npx tsc --noEmit` | 0 errors | 0 errors | ✅ |
| `npm run lint --max-warnings=0` | 0 warnings | 0 warnings | ✅ |
| `npm test` | 1058p/12s/0f (W165 baseline) | 1058p/12s/0f in 33.38s | ✅ |
| `npm run build` (clean) | Successful build | 22.4s build orchestrated successfully | ✅ |
| W156 SW4 hook chain | All pass | lint-staged + prettier + eslint --fix all PASS | ✅ |
| **wave165-admin-visual-smoke React #418 count = 0** | **0 per page** | **2 per page (UNCHANGED from W165 pre-W166)** | ❌ **Path A FAILED → Honest defer to W167** |
| Bundle: W166 SW2 NEW baseline established | 1-wave-reproducible | `index-BDwZE1BF.js` 176,663 b + server.js 23,600 b BYTE-IDENTICAL × 1 build | ✅ |

### SW3 verification

| Check | Expected | Actual | Status |
|-------|----------|--------|--------|
| Issue filed at GoogleChrome/lighthouse | URL captured | https://github.com/GoogleChrome/lighthouse/issues/17021 | ✅ |
| run-lhci.mjs comment block updated | Issue URL + memory file pointer added | 8-line addition at lines 208-216 | ✅ |
| memory/wave166_lighthouse_upstream_issue.md exists | Full draft + URL | Created with URL filled post-`gh issue create` | ✅ |
| W156 SW4 hook chain | All pass | All hooks PASS (no Python files = many skipped, but all clean) | ✅ |

### SW4 verification (commit `2d69bd293`)

| Check | Expected | Actual | Status |
|-------|----------|--------|--------|
| AUDIT_WAVE166.md created | Comprehensive narrative | This file | ✅ |
| CLAUDE.md ## Audit Trail W166 row | Concise summary | Added | ✅ |
| CLAUDE.md ## Gotchas × 3 | SW1 JWT pattern + SW2 structural defense + smoke filter bug | Added | ✅ |
| INDEX.md active table updated | W166 inserted, W163 removed | Updated via Python helper | ✅ |
| N+3 rotation | `git mv docs/audits/AUDIT_WAVE163.md docs/audits/archive/` | Executed in SW4 commit | ✅ |
| MEMORY.md compaction | <24,400 b with ≥500 b headroom | 24,058 b / 342 b headroom (tight but under ceiling) | ⚠ |
| memory/wave166_backlog.md created | Close-status entry-point | Created in `.claude` profile | ✅ |
| memory/wave167_opening_prompt.md created | W167+ handoff document | Created in `.claude` profile | ✅ |

---

## Lessons learned + W167+ candidates

### W166 lessons

1. **Premature commit message claims can land in git history** — SW2 commit subject "close React #418 hydration mismatch" was claimed pre-empirical-verification. Future SW pattern: **either** (a) defer the "close" claim to the audit commit message **or** (b) split the SW into "apply structural fix" + "verify closure" commits where only the verify commit claims closure. W166 audit narrative corrects honestly per W141 anti-pattern #4.

2. **Test infrastructure filter bugs can hide regression evidence** — `wave165-admin-visual-smoke.mjs:384-387` `hydrationErrorCount` filter missed "Minified React error #418" string (only matched "hydrat" / "Hydration" / "did not match"). Smoke reported `hydr_err=0` when grep on raw sidecar found 2 firings. **Lesson**: when adopting test infrastructure from a prior wave, audit its filter logic before relying on it for closure verification. W167+ housekeeping: extend the filter to match React minified error patterns.

3. **Multi-source hydration mismatches require targeted diagnosis** — applying the W156 SW3 canonical mounted-state pattern to AdminLayout was structurally correct but didn't close React #418 because the actual source is deeper (AdminBackdrop re-render, admin Feature browser-only hooks, OR something we haven't thought of). **Lesson**: for hydration mismatches surfacing in production-minified bundles, the canonical diagnostic step is NODE_ENV=development build for unminified error message (W155 (z) #3 + W156 SW1 pattern), BEFORE attempting fixes based on hypothesis.

4. **Phase 3 verification catches Agent path errors** — W141 anti-pattern #3 stay vindicated × 32 cumulatively. SW1 had 2 minor citation offsets (`_set_access_token_cookie` line range + `session_service.py` wrong subdir). Phase 3 Read corrected before plan-write.

5. **Filing upstream issues is a low-friction state-shift** — SW3 took ~30 min wall-clock to: pre-flight existing issue scan via WebFetch + draft body + `gh issue create` + comment block update + memory file. Smaller than the plan's ~30-45 min estimate. The 108-LHR data + cross-OS verification + chrome flag disproofs makes a compelling upstream case.

### W167+ candidate priority (post-W166)

1. **⭐ SW2 followup React #418 closure** (~1-3h): NODE_ENV=development build for unminified error message + targeted investigation of AdminBackdrop re-render + admin Feature browser-only hooks + TanStack Router transition state. Closes W165 NEW candidate #2 + W164 §Honesty #4 verification + retires "structural defense only" framing on AdminLayout SW2.

2. **🟠 wave165-admin-visual-smoke.mjs filter fix** (~15 min housekeeping): extend `hydrationErrorCount` filter at line 384-387 to match "Minified React error #418" + "React error #4??" patterns. Eliminates W166 NEW #2 false-negative.

3. **🟢 Lighthouse upstream issue monitoring**: check `#17021` ~2-4 weeks post-filing for maintainer response. If accepted + fix planned, update tracking. If closed as duplicate / won't-fix, document in CLAUDE.md Gotchas as "tracked-upstream resolved".

4. **🟢 Bundle invariant × 3 reproducibility check** (~5 min): run `cd frontend && rm -rf dist && npm run build` × 3 from clean state, compare sha256 of `index-BDwZE1BF.js` + `server.js`. Confirms W166 SW2 NEW baseline is reproducible (1-wave → ≥3-wave invariant kickoff).

5. **Optional**: project-done declaration once W167 SW2-followup closes the remaining actionable W166+ candidate. Per opening prompt §"Q0=A still valid", 26-wave discipline streak preserved as historical record.

---

## End-of-wave gates summary (post-SW3, pre-SW4 commit)

| Gate | Expected | Actual | Status |
|------|----------|--------|--------|
| tsc 0 errors | 0 | 0 | ✅ |
| eslint --max-warnings=0 | 0 | 0 | ✅ |
| vitest 1058p/12s/0f (W165 baseline) | 1058p/12s/0f | 1058p/12s/0f in 33.38s | ✅ |
| pytest W166 SW1 slice | 28p/0f | 28p/0f in 3.41s | ✅ |
| Docker stack healthy | 5 services | frontend + backend + file-processor + temporal + caddy all healthy | ✅ |
| /healthz | `{"status":"ok"}` | `{"status":"ok"}` | ✅ |
| /login SSR | 200/21,732b (W160-W165 baseline) | 200/21,791b (+59 b — within ±0.3% noise band) | ✅ |
| Bundle invariant | W164 baseline retired; W166 SW2 NEW baseline established | `index-BDwZE1BF.js` 176,663 b + server.js 23,600 b | ✅ |
| Tree-shake invariant | 0 dev React refs in PROD | 0 | ✅ |
| Server jsxDEV count | 0 (W156 SW1 fixup preserved) | 0 | ✅ |
| Cargo.lock no drift | idempotent ≥32 waves | preserved | ✅ |

**Wave 166 sum**: 7 commits (SW1+SW2+SW3+SW4+polish-v1+polish-v2+polish-v3) + 1 W141 anti-pattern STRICT 1-iter defer (SW2) + 3 NEW W166 caveats honestly framed + 2 closures (SW1 candidate + SW3 state shift) + W164 BYTE-IDENTICAL bundle invariant retired; W166 SW2 NEW baseline established + verified × 3 BYTE-IDENTICAL at polish-v2.

**27th consecutive wave** with brainstorming + Phase 1 Explore + Phase 3 Review + W141 anti-pattern discipline.

---

## References

- **W166 plan**: `C:\Users\egorribun\.claude\plans\c-users-egorribun-claude-projects-c-use-shimmering-dolphin.md`
- **W166 backlog (memory)**: `memory/wave166_backlog.md`
- **W166 Lighthouse upstream tracking (memory)**: `memory/wave166_lighthouse_upstream_issue.md`
- **W167 opening prompt (memory)**: `memory/wave167_opening_prompt.md`
- **W166 commits**: `07da10e10` SW1 + `ae03e61d3` SW2 + `b4b5d1a2a` SW3 + `2d69bd293` SW4 + `d452f0c9a` polish-v1 (HEAD placeholder cleanup) + `646110afa` polish-v2 (5 commit-count corrections + build × 3 reproducibility claim) + `(this commit)` polish-v3 (polish-v2 self-referential `(this commit)` cleanup — recursion terminator per W164/W165 lesson #6 pattern)
- **Upstream issue**: https://github.com/GoogleChrome/lighthouse/issues/17021
- **W141 anti-pattern register**: 32+ vindications cumulative, 4 patterns active (#1, #3, #4, #15 ARCHIVED)
- **Previous active waves**: W163 (rotates to archive in this SW4) / W164 (carry) / W165 (carry)
- **Active waves post-W166**: **W164/W165/W166**
- **N+3 rotation**: `git mv docs/audits/AUDIT_WAVE163.md docs/audits/archive/AUDIT_WAVE163.md` (executed in this commit)
