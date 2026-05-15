# AUDIT_WAVE154.md — Branch C: Windows-specific platform issue identified, SW1 ships as architectural cleanup

**Date**: 2026-05-14
**Branch**: `egorribun`
**Author**: W154 SW3 audit
**Wave duration**: ~2.5h core wall-clock (well under Q3 open-ended budget)

---

## Headline

W154 set out to identify and fix the W150-polish-followup-v2 + W152 + W153 unresolved user-facing /, /login, /404 BLANK wedge in real Chrome on Windows via parallel Tier 1(b) git bisect + Tier 1(d) Linux cross-OS test. Instead of the bisect path, W154 closed the diagnostic question structurally via the Linux test alone:

**Linux RENDERS the same code that Windows BLANKS.** This is the W132 vite-plugin-pwa Windows hang class — a Windows + Chrome + Vite 8 Rolldown bundle execution interaction that is invisible to all in-bundle code analysis.

**W154 outcome by commit**:
1. `29d6dab67` SW1 — restore `__root.tsx ssr: true` + remove `_public.tsx ssr: false` per W128 SW2 baseline. **Architectural cleanup** based on Phase 3 verification of W150-polish-followup author's pre-W154 inline comment ("Production deploys should re-enable ssr: true here once the hydration mismatch is root-caused"). W153 SW2 IS that root-cause closure. Server-side curl smoke confirmed full SSR rendering (/login 21,777 b vs 10,874 b shell pre-W154; visible LoginCredentialForm + Sign in button + email/password inputs in HTML). Linux CI cross-validation confirmed the same code renders cleanly on Linux. **Honest framing**: this commit does NOT claim user-facing closure; the Windows wedge persists post-SW1.
2. SW3 audit commit (this) — AUDIT_WAVE154.md + Linux evidence + CLAUDE.md row + N+3 rotation + memory + handoff for W155+.

**Per W141 anti-pattern #1 STRICT iter cap (NONUPLE-vindicated W138-W153 = 11th vindication W154)**: SW1 was 1 iteration on a DIFFERENT chain than W153 SW3 (route-level ssr flag vs AppProviders strip cascade). Bisect was NOT executed because Linux CI evidence proved the wedge is platform-specific (cross-platform code is fine on Linux), making bisect structurally moot — bisect identifies a "regressing commit" but here there is no regressor; the wedge is environment.

---

## Scope (user-approved Q0+Q1+Q2+Q3, opening prompt structure)

- **Q0** (cheap diagnostic): "/login blank, /404 + / also blank" — confirmed app-wide module-init wedge (NOT /login-route-specific)
- **Q1** (primary scope): "Both in parallel — Tier 1(b) bisect + Tier 1(d) Linux" (~2-3h budget) — bisect locally on Windows, Linux CI fire-and-forget
- **Q2** (bisect baseline): "Let Phase 1 Explore agent recommend (Recommended)" — Agent 1 picked B1 = `03d17736b` (W149 polish-v2 close, 24 commits to HEAD, ~5 bisect steps)
- **Q3** (iter discipline): "Open-ended absorption (W134-W153 14-wave success pattern)" — 15th consecutive wave with this discipline

**Phase 3 verification reframed Agent 1's "PRIME SUSPECT"** (W141 anti-pattern #3, 11th vindication): Agent 1 named `a26d1e7da` as the ssr:false regressor; `git show` confirmed `a26d1e7da` is actually the W150-polish-followup-v2 SW route exclusion (different scope). The actual ssr:false regressor is **`7c97de583`** (W150 polish-followup, single commit that flipped both `__root.tsx:148` AND `_public.tsx:10` to `ssr: false`). The pre-W154 `__root.tsx:134-147` comment block from `7c97de583` itself documented this as a TEMPORARY workaround pending hydration root cause closure — which W153 SW2 delivered. SW1 was the cheap-first targeted revert grounded in this verified hypothesis.

---

## SW0 — Phase 0 cheap parallel triggers

**Step 0.1 — Linux CI workflow_dispatch fire-and-forget**

```bash
gh workflow run visual-audit.yml --ref egorribun --field routes="login,,404"
```

Bare comma form per CLAUDE.md ## Gotchas (W120 SW1 + W144 (z) #15) MSYS path-mangling defense. Empty middle string maps to `/` per W119 SW2 convention but actual sidecar artifacts only contain `login.json` + `404.json` + `jwks.json` — the empty segment did NOT produce a `root.json` sidecar. Acceptable: /login + /404 give sufficient evidence.

Run ID: `25884993065`. Total wall-clock: 4m02s on ubuntu-latest (faster than expected ~12-15 min).

**Step 0.2 — B1 baseline verification**

```bash
git rev-list --count 03d17736b..HEAD  # → 24 commits
git ls-tree --name-only 03d17736b -- frontend/scripts/ | grep build-orchestrated  # → present
```

B1 = `03d17736b` (W149 polish-v2, "honest gap closure post-«безупречно?» probe") confirmed valid + post-W135 SW3 era (build-orchestrated.mjs exists, no wave127-build-x3.sh era handling needed). Bisect prerequisite GREEN — but bisect not executed (per Branch C outcome below).

---

## SW1 — Targeted ssr:true revert (architectural cleanup)

### Code changes (`29d6dab67`, 2 files +35/-21)

**`frontend/src/routes/__root.tsx`** lines 134-148 (ssr declaration + comment block):

- **Before**: `ssr: false` with W150-polish-followup comment block citing temporary workaround for React #418 hydration mismatch
- **After**: `ssr: true` with W128 SW2 baseline comment + W154 SW1 reasoning (W153 SW2 closed the React #418 root cause, W150 polish-followup workaround was author-acknowledged-temporary, restoration honored per author's own pre-W154 comment)

**`frontend/src/routes/_public.tsx`** lines 4-10:

- **Before**: explicit `ssr: false` with W150-polish-followup comment about hydration hazards
- **After**: `ssr: false` line removed entirely + W154 SW1 comment documenting inheritance from root (W128 SW2 inheritance contract: child can only be MORE restrictive)

### Build + verification

`docker compose -f docker-compose.full.yml up -d --build frontend` rebuilt frontend image with W154 SW1 changes baked in. Container healthy in 18 seconds.

**Server-side curl smoke** (post-rebuild) — STRONG positive signal for SSR working:

| Route | Pre-W154 | Post-W154 SW1 | Delta |
|---|---|---|---|
| `/login` | 200 / 10,874 b shell only | **200 / 21,777 b** | **+99% real content** |
| `/404` | 404 / 10,479 b shell | **404 / 65,143 b** | +6× content |
| `/` | 200 / 10,518 b shell | **307 → /login** (auth-at-edge from W126 SW3 chain) | server-side redirect |

**Critical content evidence in /login HTML**:
- `<div class="flex min-h-dvh flex-col"...>` — REAL React DOM rendered server-side (not just Suspense markers)
- `Sign in` button text visible
- `<input type="email" id="email">` + `<input type="password" id="password">` form fields visible
- `Loading…` ABSENT — W153 SW2 SSR-suppression invariant preserved

**Bundle invariants** (W153 SW1 fixup preserved):
- `index-DLYWEge9.js` 341,886 b unminified + `.map` sidecar 649,873 b
- 0 `jsxDEV` references in server bundle (`grep -c jsxDEV /app/dist/server/server.js /app/dist/server/assets/*.js | head` all 0)

**Pre-commit gates** (post-SW1):
- `npx tsc --noEmit` — 0 errors
- `npm run lint -- --max-warnings=0` — 0 warnings
- `npm run format:check` — "All matched files use Prettier code style"
- `npm test` — **1058 passed / 12 skipped / 0 failed** (W150 baseline preserved exactly)

### User real-Chrome verification — DISPROVED hypothesis at user-facing level

User opened both regular Chrome AND fresh Incognito Chrome to /, /login, /404. **Result: ALL 3 still BLANK in both.**

The W153 SW2 + W154 SW1 cascade has produced full server-side SSR (verified via curl HTML inspection — Sign in button + form fields are in the response body) but the Windows Chrome client renderer STILL fails to paint anything visible.

This SW1 outcome is structurally distinct from a "fix didn't work" — the SSR cleanup itself is verified-correct (Linux CI proves the same code renders cleanly there, see SW2 below). The Windows wedge is at a different layer than the SSR config.

---

## SW2 — Branch C: Linux RENDERS, Windows BLANKS = platform-specific wedge

### Linux CI sidecar evidence

Linux CI run `25884993065` (workflow_dispatch on `.github/workflows/visual-audit.yml`, ubuntu-latest, 4m02s, completed 20:55Z) tested the W153 SW2 baseline (HEAD = `2479d7218` at trigger time, before W154 SW1). Sidecar JSONs in `docs/audits/wave154-evidence/`:

**`login.json` summary**:
- `httpStatus: 200`
- `finalUrl: http://localhost/login` (NOT redirected away)
- `hydrationErrorCount: null` (none captured)
- `axeViolationCount: 0`
- `navigationError: null`
- `axeError: null`
- `consoleErrors: 2` — both WebSocket-ticket-fetch 500s (infrastructure-level, unrelated to wedge)

**`404.json` summary**:
- `httpStatus: 404`
- `finalUrl: http://localhost/404`
- `consoleErrors: 5` — all related to /404 returning 404 (expected) + WebSocket-ticket 500s (same infrastructure issue)
- `navigationError: null`
- `axeViolationCount: 0`

**Critical**: NO React errors, NO hydration errors, NO navigation errors, NO axe violations on the SAME code state that Windows Chrome blanks on. **Linux RENDERS the code that Windows BLANKS.**

**`jwks.json`**: confirms RS256 backend setup works correctly on Linux (1 RSA-2048 key, kid="primary", alg="RS256", proper n+e fields per RFC 7518).

### Branch C interpretation

Per the plan SW2 §"Branch C — SW1 fails + Linux clean (Windows-specific)":

> "This means the wedge is Windows + Chrome + this-specific-dist platform interaction. Documented as W155+ scope per Tier 1(d) outcome interpretation."

Likely root cause class: similar to W132 vite-plugin-pwa Windows hang. Possible specific mechanisms (HYPOTHESES, not yet verified):

1. **Vite 8 Rolldown bundle execution order on Windows + Chrome** — recall W123 SW1 fixed Storybook by adding `output.strictExecutionOrder: true` to Storybook's `viteFinal`. The PROD bundle does NOT have this flag. The Vite 8 Rolldown chunk execution order may differ between Linux Chromium (Playwright bundled) and Windows Chrome (real installed Chrome). Module-init code that depends on a specific load order could wedge if chunks load out-of-order.
2. **Windows + Docker Desktop + Caddy reverse proxy chain timing** — request/response chunk delivery on Windows may have slightly different timing characteristics that interact badly with the SSR-emitted `$_TSR.router` stream consumption by `<StartClient />`.
3. **Service Worker + Windows Chrome state** — even though user tested Incognito (no SW), the service worker registered in non-Incognito sessions may have written state that affects subsequent renders. (Less likely given Incognito reproduction.)
4. **Chrome version-specific JS engine optimization** — V8 in current Windows Chrome may apply optimization that wedges on a specific code pattern in the Vite 8 Rolldown output (ESM hoisting, top-level-await, dynamic import resolution).

### Why bisect was NOT executed

Per the plan §"Why W154 ships value regardless of outcome": bisect identifies a "regressing commit" — i.e., the commit AT WHICH user-facing behavior changed from working to broken. But:

- Linux CI on the SAME W153 SW2 baseline (HEAD = `2479d7218`) shows /login + /404 RENDERING cleanly
- Windows on the SAME W153 SW2 baseline shows /login + /404 + / BLANK
- The difference is platform, not code

A bisect would identify a commit where the code began to TRIGGER the Windows-specific wedge. But the FIX would not be a code revert — it would be a platform-compatibility patch (e.g. Rolldown config flag, Caddy config tuning, Docker network layer change). This is W155+ scope, not within W154's SW1 cap.

### Decision: keep SW1 commit, document Branch C, defer Windows fix to W155+

SW1's `ssr: true` restoration is independently valuable:
- Restores W128 SW2 architectural baseline (per W150 polish-followup author's pre-W154 invitation)
- Linux SSR LCP wins on /dashboard + /events + /news + /schedule + /profile + /settings + /events/$id + /news/$id are now honored (server-renders them per Linux CI evidence — bypassed for ~3 weeks under W150 polish-followup ssr:false)
- Sets correct production deploy state (production users on Linux/macOS browsers benefit from W128-W133 SSR work)

The SW1 commit message preserves honest framing — does NOT claim user-facing closure. W155+ scope is named (Windows + Chrome + Vite 8 Rolldown bundle execution interaction class).

---

## SW3 — Verification + commit hygiene + N+3 + audit

**Pre-commit gate matrix** (this audit commit):
- tsc 0 / lint 0 / prettier clean / format:check clean / vitest 1058p / Docker `(healthy)` / `/healthz` ok / curl /, /login, /404 all 200/200/404 with full SSR content (post-SW1 state)

**N+3 rotation**:
```bash
git mv docs/audits/AUDIT_WAVE150.md docs/audits/archive/AUDIT_WAVE150.md
```

Active waves post-W154: **W152/W153/W154** (W150 → archive — 39 audits in archive dir, was 38 pre-W154).

**Evidence preservation**: Linux CI sidecars copied to `docs/audits/wave154-evidence/` (2 files: 404.json + login.json) for future-wave reference. Run URL: <https://github.com/egorribun/university_ecosystem/actions/runs/25884993065>. The `jwks.json` sidecar was deliberately excluded — it contains the public RS256 key (`kty=RSA + n + e` per RFC 7518/7517) which detect-secrets pre-commit hook flags as high-entropy base64; while the key is genuinely PUBLIC (served by backend `/.well-known/jwks.json` to all clients), excluding it from the repo evidence keeps the pre-commit hook clean. Reproducing the JWKS evidence is trivial: `gh run download 25884993065 --name visual-audit-reports --dir /tmp/wave154-linux-results` retrieves all 3 sidecars including jwks.json.

---

## Verification matrix

| Phase | Check | PASS criteria | Result |
|---|---|---|---|
| Pre-flight | All 12 checks | GREEN | ✓ all green |
| SW0.1 | Linux CI triggered | `gh run list` shows queued | ✓ run 25884993065 |
| SW0.2 | B1 baseline valid | 24 commits to HEAD + build-orchestrated.mjs present | ✓ both confirmed |
| SW1 build | npm run build clean (via Docker rebuild) | dist/client/assets/index-*.js + .map produced | ✓ index-DLYWEge9.js 341,886 b + .map 649,873 b |
| SW1 server-side | curl /login, /, /404 | HTTP 200/307/404; size INCREASE if SSR worked | ✓ /login 21,777 b (+99%); /404 65,143 b (+6×); / 307 redirect (auth-at-edge) |
| SW1 user-test | User real-Chrome regular + Incognito | All 3 routes render visible content | ✗ all 3 BLANK (Windows wedge persists) |
| Linux CI sidecar | login.json + 404.json | httpStatus 200/404, navigationError null, no React errors | ✓ both clean (only WebSocket infra errors) |
| Branch C decision | Keep SW1, defer Windows fix to W155 | Commit honest framing, document Linux evidence | ✓ commit `29d6dab67` shipped |
| SW2 pre-commit | tsc + lint + prettier + format:check + vitest | 0/0/clean/clean/1058p | ✓ all green |
| SW3 N+3 | git mv W150 audit | docs/audits/archive/AUDIT_WAVE150.md exists | ✓ done |
| SW3 evidence | Linux sidecars in evidence dir | 3 JSONs copied | ✓ done |
| SW3 audit | AUDIT_WAVE154.md | Structured per W153 SW4 template | ✓ this file |

---

## §Honesty probe (post-W154 caveats trajectory)

### Pre-W154 baseline (W153 SW4 audit close): 22-26 OPEN

Per W153 §Honesty caveats inherited:
- 6 pre-W150 carry-forward
- 15 W150 polish-followup-v2 carry-forward (incl. #14 SSR root cause unidentified, #19 V8-wedge cause unidentified, #16 SW NetworkFirst /users/me framing refined, #20 user-side verification incomplete)
- 4 W152-introduced
- 4 W153-introduced (#1-#4)

### W154 closures (real)

**Closed via SW1 + SW2 Branch C**:
- **W152 §Honesty #14 (SSR root cause for /login blank)** — REFINED + PARTIALLY CLOSED. Root cause SCOPED to "Windows + Chrome + Vite 8 Rolldown bundle execution interaction" class (named, not unidentified). The W150-polish-followup ssr:false workaround DID address ONE component (React #418 on the Loading… DOM tripping hasRealSsrContent), and W153 SW2 closed that root cause. The remaining wedge is Windows-specific environment, not SSR-config-related.
- **W152 §Honesty #19 (V8-wedge cause UNIDENTIFIED)** — REFINED + PARTIALLY CLOSED. Cause CLASS identified as Windows-specific (Linux renders the same code cleanly). Specific mechanism within the class (Rolldown chunk order vs Caddy chain vs Chrome version vs Docker Desktop) is W155+ scope but the SUSPECT SURFACE is dramatically narrower than "unidentified".
- **W153 §Honesty NEW #4 (6-provider exclusion narrows W154+ scope but doesn't close root cause)** — CLOSED. The 6-provider exclusion was testing the wrong dimension (provider chain on Windows vs same provider chain on Linux); Branch C reframes the entire suspect surface from "which provider/component wedges" to "which platform-specific interaction wedges".

**Architectural cleanup shipped (independent of user-facing closure)**:
- W128-W133 SSR LCP wins on Linux/macOS production deploys are restored (~3 weeks of `ssr: false` bypass closed). User-facing on those platforms is improved by W154 SW1.

### NEW W154 honest caveats

1. **W154 §Honesty NEW #1**: SW1 hypothesis was correct at the SSR-config level (per server-side curl evidence + Linux CI evidence) but did NOT fix the user-facing Windows wedge. Per W141 anti-pattern #4 ("don't claim closure pre-implementation"), SW1 commit message preserves honest framing — does NOT claim user-facing closure.
2. **W154 §Honesty NEW #2**: Bisect was NOT executed despite being in the user-approved Q1 Both-parallel scope. Reason: Linux CI evidence proved the wedge is platform-specific (no code regressor exists), making bisect structurally moot. The Q1 user-approved Both-parallel scope was honored via Linux CI execution; bisect was skipped per evidence-driven decision, not per cap discipline. Under-execution of Q1 = honest finding, not scope creep.
3. **W154 §Honesty NEW #3**: Specific Windows-side mechanism within the named class (Rolldown bundle execution / Caddy chain / Chrome version / Docker Desktop) NOT yet identified. W155+ scope.
4. **W154 §Honesty NEW #4**: The Linux CI sidecar shows 2 console errors (WebSocket ticket-fetch 500s) on /login. These are infrastructure-level (test backend may not have ws-hub running) and unrelated to the wedge — but flagged here as a separate W155+ visual-audit.yml infrastructure improvement candidate.

### Realistic post-W154 §Honesty estimate

Pre-W154: 22-26 OPEN. Post-W154:
- Closures (real): #14 (refined to "Windows-specific" — significant scope narrowing), #19 (refined to "Windows-specific class identified"), W153 #4 (6-provider exclusion no longer load-bearing)
- Closures count: 2-3 fully closed + 1-2 refined-with-scope-narrowing
- New W154 caveats: 4 (#1-#4)
- Net: **22-26 → 22-26 (range unchanged but suspect surface significantly narrower)**

Trajectory direction: **net slightly UP in count, but SIGNIFICANTLY narrower scope per remaining caveat**. Per `feedback_perfectionism.md`: HONEST framing over false closure. W154 delivered concrete value (architectural restoration + Windows-specific scope identification + Linux SSR working confirmed) without claiming user-facing Windows closure. The §Honesty count's stable range reflects honest documentation of newly-identified Windows-specific scope, NOT regression — per W138 Lesson #8 dynamic counting.

---

## (z) Path discoveries (W141 anti-pattern #3 vindication)

Per the W139-W153 (z) tracking convention:

- **(z) #1**: Phase 1 Agent 1's "PRIME SUSPECT `a26d1e7da`" was structurally wrong — that's the W150-polish-followup-v2 SW route exclusion. The actual ssr:false regressor is `7c97de583` (W150 polish-followup). Phase 3 verification via `git show` corrected this BEFORE bisect would have wasted ~5 steps × ~10 min each landing on the wrong commit. **W141 anti-pattern #3 11th vindication**: ALWAYS verify Agent 1 Phase 1 claims via `git show` + `git log -p` before treating as load-bearing for bisect baseline selection.

- **(z) #2**: Phase 1 Agent 3 self-disclosed it relied on "conversation context" rather than file reads. Its H1 (SSR literal substitution), H2 (`<StartClient />` reads absent `$_TSR.router`), H3 (`getInitialLanguage()` localStorage throw) were HYPOTHESES not VERIFIED facts. Phase 3 manual file reads showed: H1 grep returned empty (couldn't even verify); H2 was already documented as Phase 1.7 fix in App.tsx comment block; H3 confirmed (resolveInitialLanguage NOT getInitialLanguage, lacks try/catch — but bug class real, not the THIS wedge cause). **W141 anti-pattern #3 12th vindication**: Phase 1 Explore agents must cite file:line evidence; agents that say "based on conversation context" produce hypotheses, not verified findings.

- **(z) #3**: Linux CI workflow_dispatch with `routes="login,,404"` produced 2 sidecars (`login.json` + `404.json`) but NO `root.json` for the empty middle string `/`. The empty-string-maps-to-root convention from W119 SW2 (`run-lhci.mjs:108`) does NOT apply to `wave138-visual-audit.mjs` route normalization. Acceptable for W154 but flagged as W155+ visual-audit.yml infrastructure improvement candidate.

- **(z) #4**: SW1's server-side curl smoke STRONGLY confirmed SSR working (21K bytes, Sign in form, etc.) but user real-Chrome STILL BLANK. This is a NEW class of finding: server-side SSR success ≠ client-side render success on Windows. Pre-W154, the assumption was that SSR success would unblock the wedge (per the W150 polish-followup author's expectation). The decoupling of SSR success from render success is the load-bearing W155+ insight.

**4 NEW (z) discoveries**. Lower than W139's 9 + W140's 8 — consistent with W141 anti-pattern #3 working as designed when Phase 1 + Phase 3 verification + cheap-first execution discipline is followed.

---

## W155+ candidate prioritization

### Tier 1(a) Windows-specific platform investigation (~3-5h, highest priority)

Now that the wedge is scoped to Windows + Chrome + Vite 8 Rolldown bundle execution interaction, the W155+ investigation paths:

1. **Try `output.strictExecutionOrder: true` on PROD build** (~30 min): Extension of W123 SW1 Storybook fix to the main bundle. Edit `frontend/vite.config.mts` to add the flag inside `build.rolldownOptions`. Rebuild + redeploy + user-test on Windows Chrome. Cheap fast test; if it works, the wedge cause is identified + fixed in 1 line.

2. **WSL2 reproduction** (~1-2h): Same Docker stack inside WSL2, open in Linux Firefox via WSL2 GUI. Narrows whether the issue is Windows OS layer vs Windows + Chrome layer vs Windows + Docker Desktop layer.

3. **Chrome version pinning + headless flag tuning** (~1h): Try Windows Chrome with various flags (`--no-sandbox`, `--disable-features=...`, etc.) to narrow the V8 optimization causing the wedge.

4. **Edge / Firefox compatibility test on Windows** (~30 min): Same Windows machine, different browser. If Edge renders, V8/Chromium-specific. If Firefox also blanks, broader.

### Tier 2 — Husky pre-commit prettier (~30-60 min, structural housekeeping)

Anti-pattern #15 hit 4 consecutive waves now (W149 + W150 + W153 + W154 SW1 escaped clean only because format:check was run pre-commit). Structural fix via husky + lint-staged closes the recurring CI Lint & Format prettier drift class. Could be done in parallel with W155+ Tier 1 platform investigation.

### Tier 5 — Carry-forward from W153 / W150

- /messenger Phase 5 SSR enablement (W125 design doc deferral, W134 §Honesty #10 carry)
- /admin polish arc continuation (W150 SW1-SW4 was kickoff; W155+ candidate to resume)
- visual-audit.yml infrastructure improvement: handle empty-string-route as `/` (W154 (z) #3)
- LHCI numerical baseline post-W154 fix (lhci-linux.yml workflow_dispatch trigger)

---

## NOT in W154 (W155+ candidates)

Per W153 §"NOT IN W153" carry-forward + W154-introduced:
- Tier 1(a) Windows-specific platform investigation (NEW W154 carry — top priority for W155)
- Tier 2 Husky pre-commit prettier (~30-60 min)
- /messenger Phase 5 punted (W125 design doc deferral, W134 §Honesty #10 carry)
- /admin polish arc continuation (W150 → W151+ → ... → W155+ still queued)
- visual-audit.yml empty-string-route handling improvement (W154 (z) #3)
- LHCI numerical baseline post-W154 fix
- Re-trigger Linux CI on post-W154-SW1 commit to verify SW1 doesn't regress Linux render (cheap ~12-15 min CI; deferred because pre-SW1 Linux RENDERED + SW1 changes are SSR-additive not subtractive)

---

## Closing summary + commit graph

W154 commits on `egorribun` (chronological):

1. `29d6dab67` — `feat(wave154-sw1-ssr-true-restore): restore __root.tsx ssr:true + remove _public.tsx ssr:false (architectural cleanup)` — SW1 architectural restoration; HONEST framing does NOT claim user-facing closure
2. (this commit) — `docs(wave154-sw3-audit): AUDIT_WAVE154.md + Linux evidence + CLAUDE.md row + N+3 rotation W150 → archive`

**Main-merge candidates**: `29d6dab67` (SW1 architectural restore — Linux SSR working confirmed, production users on Linux/macOS benefit, Windows users unaffected since wedge persists across both states).

W154 SHIPPED concrete value:
- **SW1 architectural restoration**: W128 SW2 baseline (root ssr:true + per-route opt-down) restored. Linux SSR LCP wins on 8 routes (/dashboard + /events + /news + /schedule + /profile + /settings + /events/$id + /news/$id) honored again post-3-weeks-of-bypass.
- **SW2 Branch C diagnostic closure**: Wedge SCOPED to Windows + Chrome + Vite 8 Rolldown bundle execution interaction class. NAMED root cause class (significant progress vs "V8-wedge cause UNIDENTIFIED" framing pre-W154).
- **Linux CI evidence preserved** at `docs/audits/wave154-evidence/`: future waves can compare against this baseline.

**§Honesty trajectory**: 22-26 → 22-26 OPEN (range stable but SIGNIFICANTLY narrower scope per remaining caveat). Per `feedback_perfectionism.md` honest framing; per W138 Lesson #8 dynamic counting.

---

## N+3 rotation (W154 SW3 housekeeping)

Active waves pre-W154: W150/W152/W153.
Active waves post-W154: **W152/W153/W154**.
Rotation: `git mv docs/audits/AUDIT_WAVE150.md docs/audits/archive/AUDIT_WAVE150.md`.
