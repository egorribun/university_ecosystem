# Wave 138 — opening prompt (NO-DEPLOY scope continued)

## State at session start

**Wave 137 CLOSED + POLISHED ×2** (2026-05-08) — Tier 1 + Tier 2 + Tier 3
+ Tier 4 per user-approved 3-question AskUserQuestion (Q1=Tier 1+2+3+4,
Q2=(a) Backend RS256 in dev, Q3=Not bounded full-depth pivot).

W137 closed **3 of 6 W136 §Honesty caveats** (W135 §Honesty #9 fully via
8 SSR routes 200 + AUTHED + 0 hydration errors through real Caddy →
frontend Node SSR → gateway → backend chain; W136 #4 issue-filing prep;
W136 #5 partial via SW5+SW6) + introduced **4 NEW caveats from real
polish-pass discoveries** + carries **3 from W134/W136** = **7 caveats
total**.

W137 surfaced a **STRUCTURAL pre-W137 BUG** that masked W134-W136
"BYTE-IDENTICAL build × 3 reproducibility" claims:
`frontend.Dockerfile`'s watch+kill workaround was exiting immediately
because host's `frontend/dist/server/server.js` was COPIED in via
`COPY frontend ./` (`.dockerignore` `dist/` only matches top-level, NOT
`frontend/dist/`). Polish-v2 refined the framing: LOCAL build × 3 was
ALWAYS reproducible (`index-DqqHVXgy.js` 139,808 — verified ×3 in
polish-v1); the DOCKER build was the spuriously-matching one (host-
cached LOCAL dist leaked through).

### 12 git commits ahead of W136 close (`9cc3a2789` polish-v2)

The W137 prompt-update commit `10891f1a7` was the entry point;
implementation commits begin at `e5bbf077a`:

1. `e5bbf077a` SW0 `docs(wave137-sw0-design)` — design doc only (1 file +231)
2. `b95d8d815` SW1 `feat(wave137-sw1-backend-rs256)` — RS256 enablement
   (3 files +385/-1; 5 new RS256 contract tests)
3. `97ecb4d99` SW2 `chore(wave137-sw2-secret-key-sync)` — .env↔.env.docker
   drift detect (1 file +27)
4. `62fa9eb04` SW3 `fix(wave137-sw3-vite-backend-origin)` — Docker
   build-arg fix (1 file +10/-1)
5. `730820405` SW4-prep `feat(wave137-sw4-authed-smoke-prep)` — Caddy
   /.well-known + smoke + Dockerfile dist clear (3 files +515)
6. `a5f251376` SW5+SW6 `chore(wave137-sw5-sw6-distroless-health)` —
   file-processor health-probe + tempo/loki sidecars (2 files +69/-10)
7. `8dccc9120` SW4-pass `feat(wave137-sw4-authed-smoke-pass)` — close
   §Honesty #9 (2 files +33/-3)
8. `c95acfe8a` SW5-honesty `docs(wave137-sw5-honesty)` — file-processor
   temporal-localhost dev limit (1 file +19)
9. `b0819053a` SW7 `docs(wave137-sw7-upstream-issues)` — 3 issue
   templates (1 file +258)
10. `6eac13f3e` SW8 `docs(wave137-sw8-audit-handoff)` — AUDIT_WAVE137 +
    W138 prompt + N+3 rotation (W134→archive) + MEMORY compaction
    (6 files +1017/-10)
11. `232eaeeab` polish-v1 `chore(wave137-polish)` — 11 verification
    gates + §Honesty #4 framing refinement (1 file +40/-4)
12. `4c6385460` polish-v2 `chore(wave137-polish-v2)` — cross-session
    vitest 5/5 + INDEX.md cleanup + sw.js compilation verified
    (2 files +8/-5)

Verify session-start: `git log --oneline 9cc3a2789..HEAD | wc -l` →
**12** (matches expected; if different, investigate before brainstorming).

```bash
git status --short  # Should be clean working tree
ls docs/audits/AUDIT_WAVE*.md  # Should be 3 files: W135/W136/W137
ls docs/audits/archive/AUDIT_WAVE*.md | wc -l  # Should be 23 (W112-W134)
wc -c memory/MEMORY.md  # Should be 23,306 bytes (< 24,400 auto-load threshold)
```

---

## Bundle baseline post-W137 (CORRECTED via Dockerfile dist-clear fix)

**LOCAL `npm run build` (build-orchestrated.mjs)** — verified BYTE-
IDENTICAL × 3 in polish-v1:

```
dist/client/assets/index-DqqHVXgy.js  139,808 bytes (LOCAL — VITE_BACKEND_ORIGIN unset → fallback localhost:8000 baked)
dist/client/_shell.html                65,864 bytes
dist/client/sw.js                      53,181 bytes (real Workbox 7.4.0; __WB_MANIFEST replaced — polish-v2 verified)
dist/server/server.js                  39,373 bytes
Workbox precache: 209 files / 4.80 MB
```

**DOCKER build via `start-docker.ps1 -Build`** — verified ×1 post-W137
fixes:

```
dist/client/assets/index-tGuQB5EY.js  ~139,XYZ bytes (DOCKER — VITE_BACKEND_ORIGIN=http://backend:8000 baked)
dist/server/server.js                  39,371 bytes (-2 vs LOCAL: URL string delta from "localhost:8000" → "backend:8000")
```

**🚨 W138 first task — Docker × 3 BYTE-IDENTICAL invariant**: re-run
`start-docker.ps1 -Build` × 3 from clean state with `rm -rf
frontend/dist` between runs to assert byte-identical hashes. Polish-v2
verified LOCAL × 3 reproducibility but deferred Docker × 3 to W138 per
critical-path plan. Estimate ~15-20 min.

The W134-W136 audit reports' "BYTE-IDENTICAL build × 3" claims should
be retroactively re-framed as "LOCAL build × 3 was always reproducible
(claim correct for LOCAL path); DOCKER build × 3 was spuriously
matching due to host-cache leakage; post-W137 Docker × 3 needs fresh
verification".

---

## NO-DEPLOY scope continued (W134/W135/W136/W137 carried forward)

Cluster deployment NOT pursued. Goal: "fully working + visually +
internally flawless локально + структурно". Cluster-dependent items
remain removed (Phase 6 actual rollout, RUM wiring, Caddy weight flip
live test, kubectl apply, etc.).

W125-W133 SSR migration arc remains shipped + locally verified +
structurally correct. **W137 SW4 verification proves end-to-end SSR
auth-at-edge works through real Docker chain** (the W135 §Honesty #9
closure) — this is the FIRST wave to verify the full SSR migration arc
end-to-end with real authed cookies.

---

## Gates baseline (preserved through W137 + polish-v1 + polish-v2)

| Gate | Value | Polish status |
|------|-------|---------------|
| `npx tsc --noEmit` | 0 errors | polish-v1 ✓ |
| `npm run lint` (max-warnings=0) | 0 errors / 0 warnings | polish-v1 ✓ |
| `npx vitest run` single | **1052p / 12s / 0f** | polish-v1 ✓ |
| Cross-session vitest 5-run | **5/5 × 1052p / 12s / 0f** (flake band = 0) | polish-v2 ✓ |
| pytest backend slice | **255p / 0f** (extended slice + 5 W137 SW1 RS256 contract tests + W131 cookie + W136 SW1+SW2+SW4) | polish-v1 ✓ |
| `npm audit` | **0 vulnerabilities** | polish-v1 ✓ |
| Cargo.lock no drift | working tree clean (≥ 27 waves idempotent) | polish-v1 ✓ |
| i18n parity | 18 tests passed (CLDR-aware EN/RU) | polish-v1 ✓ |
| Tree-shake invariant | 0 matches for `lhci-mock-user` in PROD `dist/client/assets/*.js` | polish-v1 ✓ |
| Build × 3 LOCAL BYTE-IDENTICAL | hash + sizes match across × 3 runs | polish-v1 ✓ |
| Build × 3 DOCKER BYTE-IDENTICAL | DEFERRED — W138 first task (~15-20 min) | ⚠ W138 |
| Real Docker chain authed flow (8 SSR routes) | **8/8 200 + AUTHED + 0 hydration errors + ~113 net req each** | SW4 ✓ NEW |
| W137 SW1 RS256 contract tests | **5p / 0f** | SW1 ✓ NEW |
| tempo-healthprobe + loki-healthprobe | `(healthy)` | SW6 ✓ NEW |
| file-processor healthcheck | **(unhealthy)** in dev (P0-03 temporal-localhost) — production K8s would work | SW5 §Honesty NEW |
| AUDIT_WAVE137 commit-stat | 11/11 W137 commits match audit doc claims via `git show --shortstat` | polish-v1 ✓ |
| MEMORY.md size | **23,306 bytes** (< 24,400 auto-load truncation) | SW8 ✓ |
| Memory link resolution | **27/27 references resolve** from `.claude/memory` auto-load source | polish-v1 ✓ |
| Active waves (N+3) | W135/W136/W137 | SW8 ✓ |
| Archive directory | 23 entries W112-W134 | SW8 ✓ |

---

## SSR routes (8 total — preserved through W137; FULL VERIFICATION post-SW4)

W137 SW4 verified ALL 8 SSR routes work end-to-end through real Docker
chain via authed Playwright smoke:

| Route | Status | HTTP | Auth | Hydr err | Net req |
|-------|--------|------|------|----------|---------|
| `/dashboard` | SSR | 200 | AUTHED | 0 | 113 |
| `/events` | SSR | 200 | AUTHED | 0 | 113 |
| `/news` | SSR | 200 | AUTHED | 0 | 113 |
| `/schedule` | SSR | 200 | AUTHED | 0 | 110 |
| `/profile` | SSR | 200 | AUTHED | 0 | 113 |
| `/settings` | SSR + tab=N | 200 | AUTHED | 0 | 114 |
| `/map` | SSR | 200 | AUTHED | 0 | 113 |
| `/activity` | SSR | 200 | AUTHED | 0 | 113 |

The 1 console error per route is **Service Worker `script evaluation
failed`** — sw.js IS correctly compiled (53,181 bytes Workbox 7.4.0;
__WB_MANIFEST replaced; polish-v2 verified) but evaluation fails in
browser. **Specific cause NOT investigated in W137**. Filed as W138
candidate (~1h).

Remaining `ssr: false`: 2 (messenger × 2 — heavy WebSocket + IndexedDB
at render time, deferred indefinitely under no-deploy "production-as-is").

`/map` + `/activity` preserved at `ssr: 'data-only'` (W127 SW6
annotations under permissive parent `_auth.tsx ssr: true` W128 SW2).

---

## Wave 138 candidates (post-W137)

### Tier 1 — HIGH priority (W137 §Honesty closures)

- **Build × 3 DOCKER reproducibility re-establishment** (~15-20 min,
  ⚠ critical-path quick-win). Re-run `start-docker.ps1 -Build` × 3 from
  clean state with `rm -rf frontend/dist` between runs (each Docker
  rebuild ~5-7 min cached; ~15-20 min total). Assert byte-identical
  hashes for `dist/client/assets/index-*.js` + `_shell.html` +
  `dist/server/server.js` + `dist/client/sw.js`. Closes W137 §Honesty
  #4 fully (post-fix Docker reproducibility verified). LOCAL × 3 was
  already verified in polish-v1.

- **Service Worker `script evaluation failed` investigation** (~1h,
  W137 polish-v2 finding). sw.js IS correctly compiled (53,181 bytes
  Workbox 7.4.0 with __WB_MANIFEST replaced — verified in BOTH local
  + Docker container). The browser-side registration error is from
  evaluation phase, not loading phase. Investigation paths: (a) CSP
  nonce/source restrictions on SW context; (b) Workbox runtime
  dependency missing in dev; (c) headless-Chrome-specific quirk; (d)
  service-worker-allowed header interaction. Reproduce via
  `frontend/scripts/wave137-authed-smoke.mjs` post Docker stack up.

- **file-processor temporal-localhost fix** (~2-3h structural OR
  ~30 min doc-accept, W137 §Honesty #5). Three paths:
  - **(a) Rebind temporal to 0.0.0.0 with token auth** (~2-3h):
    update temporal entrypoint to drop `--ip 127.0.0.1`; add token-
    based authentication so it's safe to expose on internal docker
    network; update file-processor + workers to authenticate.
    Restores P0-03 trade-off original intent (security WITHOUT
    cluster isolation).
  - **(b) file-processor host network** (~30-60 min): set
    `network_mode: host` on file-processor service so it can reach
    temporal:127.0.0.1:7233 directly. Breaks docker-compose service-
    name DNS for file-processor; downstream services accessing it
    must use host:port instead.
  - **(c) Document accept-as-dev-limitation** (~30 min): add to
    docker-compose.full.yml + CLAUDE.md as known limitation; backend
    workers that depend on file-processor get marked best-effort
    in dev. Production K8s (separate Temporal cluster with auth)
    remains unaffected.

### Tier 2 — Per-page visual audit (NEW FEASIBILITY post-W137)

- **/dashboard visual audit** (~0.5-1 wave). Per W125 SSR design's
  Phase 6 ramp + W137 SW4 closure: NOW FEASIBLE to run real Playwright
  authed smoke + LHCI baseline + axe-core a11y on each SSR route in
  turn. Recommend starting with /dashboard (highest traffic, most
  complex). Check: 0 axe violations, LHCI Performance/A11y/SEO
  thresholds met, React hydration clean.

- **Other 7 SSR routes' visual audits** — opportunistic. Pattern:
  one route per ~0.5-1 wave depending on findings.

### Tier 3 — Inherited tech-debt (carry-forward from W134/W135/W136)

- **Test infrastructure expansion** (W115 SW1 a11y-public WebKit OOM;
  W116 SW1 mobile-webkit /404).
- **LHCI gate ratchet on REAL W137 baseline** (now feasible — Docker
  build produces consistent fresh bundle). W120 SW2 last applied;
  W124 SW4 documented variance band.
- **a11y deep-audit cross-browser**.
- **i18n parity consolidation**.
- **Storybook/Chromatic activation** (requires user-side
  `CHROMATIC_PROJECT_TOKEN` secret + `vars.CHROMATIC_ENABLED=true`).
- **Playwright /login screenshot fragility** (W136 SW3 honest deferral;
  W136 §Honesty #6) — VITE_E2E_MODE-style flag refactor (~30 min).

### Tier 4 — Pre-existing carry-forward (NOT closeable without
                                          structural change)

- **W134 §Honesty #2 (bundle delta)** — superseded by W137 §Honesty
  #4. Real W137 baseline is `index-tGuQB5EY.js` (Docker) /
  `index-DqqHVXgy.js` (LOCAL, no VITE_BACKEND_ORIGIN baked).
- **W134 §Honesty #10 (/messenger Phase 5 punted)** — no-deploy
  decision unchanged. Tier 5 explicit user decision.
- **W137 sidecar healthiness ≠ container healthiness** for tempo+loki
  (by-design). Production K8s should use upstream's /ready via
  livenessProbe httpGet check.

### Tier 5 — Optional big scope (explicit user decision)

- **Messenger × 2 polish arc** (~5-7 waves). Per historical anchoring
  (Schedule 14, Map 23, Events 6, Activity 4, News 6, Dashboard ~10):
  messenger has heavy WebSocket + IndexedDB but smaller surface area
  than Map. Pursue OR punt.
- **/admin polish arc** (~3-5 waves). Admin tooling depth audit + UX
  polish. Lower-traffic page. Pursue OR punt.

### Filed upstream issues (W137 SW7) — pending external resolution

- rolldown/rolldown — build hangs post-prerender (MessagePort + Worker)
- chromedevtools/chrome-devtools-mcp — Windows headless heavy-DOM
  Accessibility.getFullAXTree + Runtime.evaluate timeout
- grafana/tempo + grafana/loki — distroless `--check-ready` CLI
  subcommand request

User files via `gh issue create` per `memory/wave137_upstream_issues.md`
filing instructions. Resolution timeline outside our control.

---

## Pragmatic recommendation (per `feedback_planning_estimates.md` style)

- **Best ROI immediate (Tier 1 quick-wins)**: **Build × 3 Docker
  reproducibility (~15-20 min) + Service Worker investigation
  (~1h)** = ~1.5-2h. Closes W137 §Honesty #4 fully + investigates the
  one remaining SW console error per route. Low scope, high
  closure-rate.

- **Best W138 starter combo (Tier 1 + Tier 2 partial)**: **Build × 3
  + Service Worker fix + /dashboard visual audit** = ~2-3h. Real
  per-page visual audit becomes the first feasible since SSR migration
  arc started in W125. High user-facing impact.

- **Most W137 §Honesty closures**: **Tier 1 + file-processor temporal
  rebind path (a)** = ~3-5h. Drops to ≤4 § Honesty caveats post-W138.

- **Tier 5 explicit decision**: confirm Messenger/Admin scope OR punt
  before W139+.

### Anti-pattern to avoid (from W137 polish lessons)

1. **Don't claim "build × N reproducibility" without verifying via
   fresh build from clean state**. The W134-W136 claim was structurally
   broken for 3 waves because the Dockerfile bug masked the failure.
   W138 must re-establish a CORRECT claim via:
   ```bash
   docker compose down
   rm -rf frontend/dist
   start-docker.ps1 -Build  # run #1 — capture hashes
   docker compose down
   rm -rf frontend/dist
   start-docker.ps1 -Build  # run #2
   docker compose down
   rm -rf frontend/dist
   start-docker.ps1 -Build  # run #3
   sha256sum dist/client/assets/index-*.js dist/server/server.js \
             dist/client/_shell.html dist/client/sw.js
   ```
   Assert all 3 sums match.

2. **Don't trust prior-wave audit framings as ground truth** — W137
   polish-v2 found the original "(placeholder per workbox-build skip)"
   framing for the SW console error was INCORRECT (sw.js is real).
   Verify framings empirically before accepting.

3. **chrome-devtools Windows wall extends to Playwright real Chrome
   on heavy DOM** (W137 SW4 finding). Default to `context.newPage()`
   per route + skip `page.evaluate(...)` body-snippet capture from the
   start of any visual smoke script.

---

## Anticipated AskUserQuestion 3-question pattern

(W133/W134/W135/W136/W137 success — 5 waves with same pattern; W138
should continue)

1. **Q1 — Primary scope tier**:
   - Tier 1 quick-wins (Build × 3 Docker + SW investigation ~1.5-2h)
   - Tier 1+2 (+ /dashboard visual audit ~2-3h) — recommended
   - Tier 1+2+3 (+ inherited tech-debt batch ~5-7h)
   - Tier 1 + file-processor temporal-localhost fix (Tier 1 §Honesty
     closure ~3-5h)
   - Tier 5 explicit decision (Messenger × 2 OR /admin OR punt)

2. **Q2 — Within chosen tier, sub-scope**: e.g.
   - Tier 1 → Service Worker investigation paths (CSP / runtime dep /
     headless quirk / Service-Worker-Allowed header)
   - Tier 1 file-processor → Path (a) temporal rebind+auth vs (b) host
     network vs (c) accept-as-dev-limit
   - Tier 2 → which SSR route first (/dashboard recommended; or pick
     by priority — Map / Activity due to /map+/activity ssr: 'data-only'
     specifically?)
   - Tier 3 → which inherited item (LHCI ratchet vs WebKit OOM vs
     Storybook activation vs Playwright /login fragility)

3. **Q3 — Architecture/design (if applicable)**:
   - Tier 1 SW investigation → if root-causing reveals CSP-related
     issue, consider plumbing nonce vs documenting acceptable trade-off
   - Tier 1 file-processor → if Path (a) reveals temporal token-auth
     setup complexity (~30-60 min beyond plan), how to handle in W138
     vs W139?
   - Tier 4 diagnostic budget if W138 surfaces more polish-pass
     surprises (per W136 Lesson #7 + W137 §Honesty #4 retroactive
     framing pattern)

---

## Read mandatory files in order (per `superpowers:using-superpowers`)

1. **`docs/audits/AUDIT_WAVE137.md`** — full SW0-SW7 narrative +
   verification matrix + § Honesty probe (7 caveats: 3 closed via
   implementation + 3 carry from W134/W136 + 4 NEW from W137 polish-
   pass discoveries) + lessons-learned + W138 candidates list at
   bottom + polish-v1 + polish-v2 sections
2. **`memory/wave137_backlog.md`** — close-status entry-point with
   commit references + § Honesty list
3. **`memory/wave137_upstream_issues.md`** — 3 GitHub issue templates
   ready for `gh issue create` (filing instructions at end)
4. **`memory/wave138_opening_prompt.md`** — this file
5. **`docs/plans/2026-05-08-wave137-tier1234-design.md`** — W137
   design doc + 3 Explore-agent findings (backend RS256 ready,
   VITE_BACKEND_ORIGIN trap, distroless workarounds)
6. **`docs/plans/2026-05-07-wave136-tier-1-2-3-design.md`** — W136
   design doc context (JWT (d) Hybrid via existing Redis pub/sub +
   build-orchestrated trace flow)
7. **`docs/plans/2026-05-01-wave125-ssr-design.md`** § Phase 5-6 —
   original SSR design source
8. **`CLAUDE.md`** ## Audit Trail W137 row + 8 new W137 gotchas:
   - Backend RS256 enabled in dev Docker (start-docker.ps1
     New-JwtRs256Key + .env.docker ALGORITHM=RS256)
   - VITE_BACKEND_ORIGIN baked at build time (Vite/Rolldown literal
     substitution; must be Docker build ARG, NOT runtime env)
   - frontend.Dockerfile rm -rf dist; before npm run build (closes
     W134-W136 watch+kill stale-cache trap)
   - W137 authed smoke 8 SSR routes via real Docker chain
   - tempo + loki sidecar healthcheck pattern (curl + network_mode)
   - file-processor temporal-localhost dev limit (P0-03 trade-off)
   - ALLOWED_HOSTS env (NOT TRUSTED_HOSTS) for TrustedHostMiddleware
   - Caddy /.well-known/* → backend route for RFC 8615 JWKS publishing
9. **`memory/MEMORY.md`** — auto-loaded; W137 row at top; W134
   collapsed to one-liner (rotated W137 SW8); W135/W136/W137 verbose
   in Active backlog; W134/W135 audit history compact
10. **`memory/feedback_perfectionism.md`** — anticipate "безупречно?"
    probe (60-90 min polish budget — W137 used ~105 min total polish-v1
    + polish-v2; expect similar for W138)
11. **`memory/feedback_planning_estimates.md`** — range estimates over
    single numbers; "production-grade polish" anchor 3-5h base +
    variance

---

## Skills to invoke immediately (per `superpowers:using-superpowers`)

- **`superpowers:brainstorming`** — invoke FIRST per W134/W135/W136/W137
  success pattern (3-question AskUserQuestion). MANDATORY before any
  creative work. DO NOT skip.
- **`superpowers:writing-plans`** — for plan file creation in plan
  mode after brainstorming
- **`superpowers:systematic-debugging`** — invoke if hitting bugs
  (W136 SW4 + SW5 + polish-v2 + W137 SW4 surfaced REAL bugs via
  reproduce-first pattern; expect more in W138 — Service Worker
  investigation is bug-hunting territory)
- **`superpowers:verification-before-completion`** — invoke BEFORE
  claiming SW completion (Iron Law: fresh evidence before claims;
  W137 polish surfaced spurious W134-W136 reproducibility claims)
- **`superpowers:executing-plans`** — invoke AFTER plan approval

---

## Use Context7 MCP (mandatory for library docs)

W138 likely Context7 lookups:
- **`vite-plugin-pwa`** (injectManifest semantics, GenerateSW vs
  injectManifest, runtime caching strategies) — for Tier 1 SW
  investigation
- **`workbox-build`** + **`workbox-core`** — Service Worker evaluation
  context (what runtime deps are needed, how registration vs
  activation differs)
- **`@temporalio/sdk` + Temporal documentation** — for Tier 1
  file-processor fix path (a) rebind with auth (token-based + mTLS
  options)
- **Playwright API** — page-per-route patterns for visual audit
  scripts in Tier 2 (already established pattern — verify nothing
  changed in latest Playwright)
- **chrome-devtools-mcp** — for any direct browser inspection if W138
  needs it (workaround: Playwright real Chrome via `channel: 'chrome'`
  for Windows wall avoidance)
- **`@axe-core/playwright`** — for Tier 2 a11y audits

Don't trust agent inferences without Context7 verification. W137 SW4
empirical findings disproved 3 plan assumptions (chrome-devtools wall
extends to Playwright real Chrome too, page.evaluate hangs on heavy
DOM, page-per-route IS the workaround).

---

## Lessons from W137 (carry-forward for W138+)

1. **Empirical findings disprove plan assumptions, ESPECIALLY when
   assumptions piggyback on prior waves' claims** — the W134-W136
   "BYTE-IDENTICAL build × 3" reproducibility claim was inherited as
   ground truth in W137 plan but turned out to be partially spurious
   (LOCAL was correct; Docker was masked). Treat prior-wave
   reproducibility claims as hypotheses, not truths, until re-verified
   with structural evidence (e.g. real fresh build from clean state vs
   cached).

2. **`docker compose build` cache cascading masks runtime issues** —
   the watch+kill workaround in `frontend.Dockerfile` looked correct
   at inspection but had a subtle race condition (host-cached dist/
   leaked through `.dockerignore`'s top-level-only `dist/` pattern).
   When adding watch+kill or similar build-orchestration patterns,
   also add explicit `rm -rf` before the build to force fresh state.
   Cross-check by examining build duration logs (6s vs 30s+ tells you
   which path was taken).

3. **Pre-existing security trade-offs surface as visible failures
   when adding healthchecks** — W137 SW5 made the file-processor
   temporal-localhost issue visible. When adding healthchecks to
   services that depend on other services with known dev-only
   restrictions, document the inheritance chain in the healthcheck
   comment.

4. **Sidecar healthcheck pattern works for distroless containers but
   breaks downstream depends_on semantics** — W137 SW6 demonstrated
   the trade-off. Document explicitly in compose comments. Future
   distroless services should consider in-image probe binary (multi-
   stage Dockerfile pattern from spicedb / file-processor) over
   sidecar where possible.

5. **Backend RS256 enablement was simpler than anticipated** — W137
   prompt anticipation said "expect Explore-agent discovery may
   reveal more steps" but existing infrastructure was mature: SW1
   ~2-3h estimate revised to ~1h actual. Deep Explore-agent
   investigations refine wall-clock estimates downward when
   infrastructure is more mature than assumed.

6. **VITE_BACKEND_ORIGIN build-arg trap is a recurring class of
   dev/prod env-var-baking asymmetry** — Vite/Rolldown literal
   substitution at build time means runtime env vars cannot override
   build-baked values. Maintain a canonical list of "build-time-baked
   vs runtime-read" env vars; SW3 establishes VITE_BACKEND_ORIGIN as
   build-time canonical.

7. **chrome-devtools Windows wall family extends to Playwright real
   Chrome too** — W137 SW4 confirmed `page.evaluate(...)` and reused-
   page navigation both hang on heavy DOM in Playwright real Chrome
   on Windows. The W129 §Honesty `new_page` workaround pattern +
   body-snippet removal fix ARE the standard Windows visual-smoke
   recipe. Future visual smoke scripts should default to page-per-
   route + skip-evaluate from the start, not opt-in.

8. **File-rotation discipline (memory dual-location convention)** —
   W137 SW7 + SW8 + polish-v1/v2 all keep memory files in user
   `.claude` profile + repo `memory/` for cross-machine sync. Verified
   post-SW8 + post-polish-v2 commits. Pattern recipe: always `cp` from
   `.claude/memory/<file>` → `repo/memory/<file>` after editing.

9. **Empirical verification refines audit framings post-fact** —
   W137 polish-v2 found the original SW console error framing
   "(placeholder per workbox-build skip)" was incorrect. sw.js is
   really compiled (53,181 bytes Workbox 7.4.0 with __WB_MANIFEST
   replaced). Post-fact framing refinements are acceptable when
   verification surfaces them; don't artificially preserve incorrect
   claims to maintain consistency.

---

## Build × 3 reproducibility discipline (post-W137 corrected baseline)

Pattern: run `npm run build` × 3 (now via build-orchestrated.mjs with
mtime fix from W136 SW5 + single-source PWA_INJECT_CONFIG from W136
SW6 + W137 SW4-prep `rm -rf dist` Dockerfile fix) AFTER each wave's
final commit (including docs-only commits + polish commits).

- **Code-changing SWs**: hash will differ from baseline (size delta
  should match closure size of new exports + import bookkeeping)
- **Docs-only SWs**: hash MUST match the previous code-changing SW's
  bundle exactly. Different hash = something silently touched the
  bundle
- **W138 first task**: re-establish CORRECT Docker × 3 reproducibility
  baseline (~15-20 min). Docker × 1 verified post-W137 fixes;
  Docker × 3 needs fresh runs from clean state.

Windows: build-orchestrated.mjs handles post-prerender hang via
mtime-gated kill-after-artifacts (W136 SW5). Frontend.Dockerfile (W137
SW4-prep) clears dist/ before npm run build to force fresh state. CI
Linux: same script via `build-orchestrated-linux.yml` workflow_dispatch
(W136 SW6).

---

## "безупречно?" probe response template (per `feedback_perfectionism.md`)

Anticipate "безупречно?" probe at any point user-facing claim is made.
Response template:

1. **DO NOT reassure** — это probe для honest self-audit + polish pass
2. **List claims explicitly** with evidence (concrete numbers, command outputs)
3. **Find gaps proactively**:
   - claimed without verifying? (run the verification)
   - defer'нул что actually closeable? (close it)
   - framing inaccurate? (re-frame honestly — W137 polish-v2 sw.js example)
4. **Run verifications skipped**:
   - re-run gates (full vitest, full pytest, lint, build × 3)
   - cross-check claims against `git show --shortstat`
   - run cross-session vitest 5-run
   - verify memory link resolution
5. **Re-classify §Honesty caveats**: CLOSED-via-polish vs REMAINING
   (structural / by-design / W139+)
6. **Commit polish pass separately** as `chore(waveNNN-polish)` or
   `chore(waveNNN-polish-vN)` for multi-round polish
7. **Honest answer**: "X of Y caveats closed via polish; Y-X remain as
   structural / by-design / W139+. Specific deferrals: [list]. Real
   'безупречно' requires [structural changes outside this wave's scope]."

W134 polish: ~30 min (1 round). W135 polish: ~15-20 min (1 round).
W136 polish: ~75 min total (polish-v1 ~30 min + polish-v2 ~30 min +
audit updates ~15 min; 2 rounds). W137 polish: ~105 min total
(polish-v1 ~75 min + polish-v2 ~30 min; 2 rounds with major framing
refinement). Scale to wave complexity; W138 likely 60-90 min.

---

## Pre-existing tooling that W138 may use

- **`frontend/scripts/wave137-authed-smoke.mjs`** (NEW W137 SW4):
  Playwright authed smoke with JWKS pre-check + JWT alg=RS256
  assertion + JWT payload claim assertions + page-per-route lifecycle.
  Proven post-W137 SW4 to verify all 8 SSR routes 200 + AUTHED + 0
  hydration errors through real Docker chain. Run via
  `node ./scripts/wave137-authed-smoke.mjs` from `frontend/` after
  Docker stack up. **Recommended foundation for W138 Tier 2 visual
  audits** — extend with axe-core + LHCI per route.
- **`frontend/scripts/wave136-polish-authed-smoke.mjs`** (W136 polish-v2):
  Earlier authed smoke pre-W137 RS256. Superseded by wave137 version
  but kept for reference.
- **`frontend/scripts/playwright-visual-smoke.mjs`** (W136 SW3):
  generic Playwright visual smoke for non-authed routes (/, /login,
  /404) with best-effort screenshot. Useful for public-route smoke +
  non-W138 work.
- **`frontend/scripts/wave136-hang-trace-agent.cjs`** (W136 SW5):
  NODE_OPTIONS --require diagnostic agent. Enable via
  `WAVE136_HANG_TRACE=1 npm run build`. Use to repro the hang for
  upstream issue file (already filed in W137 SW7).
- **`frontend/scripts/build-orchestrated.mjs`** (W135 SW3 + W136
  SW5+SW6 + W137 SW4-prep dist-clear via Dockerfile): the canonical
  `npm run build` entry point. Mtime-gated kill-after-artifacts.
  Single-source PWA config. Now safe under host-cached dist/ scenarios.
- **`frontend/scripts/lhci-windows-fallback.mjs`** (W120 SW1): LHCI on
  Windows bypassing EPERM. `npm run lhci:windows`. **Now feasible to
  use against real W137 baseline post Docker × 3 verification**.
- **`tests/test_auth_jwt_payload.py`** (W136 SW1, 5 tests): JWT
  contract test pattern.
- **`tests/test_auth_jwt_rs256.py`** (W137 SW1, 5 tests): RS256
  contract test pattern. Reuse if W138 adds more JWT-related code.
- **`tests/test_user_deactivation_revocation.py`** (W136 SW2, 6 tests):
  session revocation pattern.
- **`tests/test_failed_login_attempts.py`** (W136 SW4, 4 tests):
  schema contract test pattern.

---

## §Honesty caveats inherited (7 total post-W137)

| # | Caveat | Type | W138 closeable? |
|---|--------|------|---|
| 1 | W134 §Honesty #2 bundle delta — superseded by W137 #4 | Honest framing | NO (recording only) |
| 2 | W134 §Honesty #10 /messenger Phase 5 punted | By-design (no-deploy) | NO (Tier 5 explicit decision) |
| 3 | W136 §Honesty #6 Playwright /login screenshot fragility | Structural | YES (~30 min, VITE_E2E_MODE refactor) |
| 4 | W137 #4 W134-W136 reproducibility-claim mask retroactive | Honest framing (refined polish-v2) | Partially closed: LOCAL ×3 ✓, Docker ×3 W138 first task |
| 5 | W137 #5 file-processor temporal-localhost dev limit | Structural (P0-03) | YES (~2-3h structural OR ~30 min accept) |
| 6 | W137 MAX_SESSIONS dev override (5→50) | Documented dev-only | NO (production K8s keeps default) |
| 7 | W137 sidecar healthiness ≠ container healthiness | By-design | NO (custom Dockerfile builds = different scope) |

**Realistic W138 closure target**: 3-4 caveats can close via
implementation/polish (#3 + #4 fully + #5 path (a) or (c)). Net
caveat count after W138: ~3-4 (down from 7). Plan target should
reflect this realistically.

---

## Final pre-flight checklist (run at session start before brainstorming)

```bash
# 1. Working tree clean + 12 commits ahead of W136 close (polish-v2)
git status --short && git log --oneline 9cc3a2789..HEAD | wc -l  # → 12

# 2. Active waves W135/W136/W137 + archive 23 entries
ls docs/audits/AUDIT_WAVE*.md  # → 3 files
ls docs/audits/archive/AUDIT_WAVE*.md | wc -l  # → 23

# 3. MEMORY.md size + memory link resolution
wc -c memory/MEMORY.md  # → 23,306 bytes (< 24,400)
# Memory links: 27/27 resolve from .claude/memory (verified post polish-v1)

# 4. Bundle baseline (CORRECTED post-W137)
ls -la frontend/dist/client/assets/index-*.js \
       frontend/dist/client/_shell.html \
       frontend/dist/client/sw.js \
       frontend/dist/server/server.js
# LOCAL build (no VITE_BACKEND_ORIGIN): index-DqqHVXgy.js 139,808 +
#   _shell.html 65,864 + sw.js 53,181 + server.js 39,373
# DOCKER build (VITE_BACKEND_ORIGIN=http://backend:8000): index-tGuQB5EY.js
#   ~139,XYZ + server.js 39,371

# 5. Cargo.lock idempotent (≥ 27 waves)
git status frontend/rust-crypto/Cargo.lock frontend/wasm-sanitizer/Cargo.lock
# → working tree clean

# 6. Verify Docker stack state
docker ps --format "table {{.Names}}\t{{.Status}}" | head -25
# → 21+ containers Up; tempo-healthprobe + loki-healthprobe (healthy);
# → file-processor (unhealthy) is W137 SW5 §Honesty (P0-03 trade-off)

# 7. Verify W137 § Honesty polish-v2 invariants
find frontend/dist/client/assets -name "*.js" -exec grep -l "lhci-mock-user" {} +
# → 0 matches (PROD tree-shake invariant)

git log --oneline -1
# → most recent commit should be `4c6385460 chore(wave137-polish-v2): ...`
```

---

**Begin**: brainstorming → AskUserQuestion (3 questions: Q1 scope tier,
Q2 sub-scope, Q3 architecture if applicable) → plan file at
`C:\Users\egorribun\.claude\plans\<auto-generated>.md` → ExitPlanMode →
execute under approved plan.

Use TodoWrite for SW progression tracking. Mark chapters via
`mcp__ccd_session__mark_chapter` when transitioning between SWs (W136
+ W137 pattern). Invoke `superpowers:verification-before-completion`
BEFORE claiming SW completion (Iron Law: fresh evidence before claims;
W137 polish surfaced multi-wave spurious reproducibility claims).

Anticipate "безупречно?" probe post-final-SW — budget ~60-90 min
polish (potentially multi-round per W136 + W137 polish-v1 + polish-v2
pattern if scope is broad like Tier 1+2 or surfaces structural
findings).

If W138 picks **Tier 1 (Build × 3 Docker + Service Worker
investigation + file-processor temporal-localhost)**, expect:
(a) Docker × 3 reproducibility re-establishment is the lowest-risk
start (~15-20 min — quick verification, single command sequence);
(b) Service Worker investigation may surface CSP-related root cause
(W137 polish-v1 added CSP nonce placeholders to `_shell.html` via
post-build-shell.mjs — could be related);
(c) file-processor temporal fix path (a) rebind+auth surfaces token-
based authentication setup complexity (~30-60 min beyond core estimate
— budget pivot per W136 Lesson #7 + W137 §Honesty #4 retroactive
framing pattern);
(d) Per-page visual audit (Tier 2) needs `wave137-authed-smoke.mjs`
foundation extended with axe-core + LHCI hooks — not from scratch.

**Mid-wave pivot acceptable** per W136 Lesson #8: if Tier 1 file-
processor structural fix surfaces > 3h work, pivot to Path (c) accept-
as-dev-limit + document. W138 §Honesty caveat count target: ≤ 4
(down from 7) post W138 close.
