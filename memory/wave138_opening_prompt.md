# Wave 138 — opening prompt (NO-DEPLOY scope continued)

## State at session start

**Wave 137 CLOSED** (2026-05-08) — Tier 1 + Tier 2 + Tier 3 + Tier 4 per
user-approved 3-question AskUserQuestion (Q1=Tier 1+2+3+4, Q2=(a) Backend
RS256 in dev, Q3=Not bounded full-depth pivot).

W137 closes **3 of 6 W136 §Honesty caveats** (W135 #9 fully via 8 SSR
routes 200 + AUTHED + 0 hydration errors through real Caddy → SSR →
gateway → backend chain; W136 #4 issue-filing prep; W136 #5 partial via
SW5 + SW6) + introduces **4 NEW caveats from real polish-pass
discoveries** + carries **3 from W134/W136** = **7 caveats total**.

The plan target was "drops to ~3 caveats" but the real polish-pass
discoveries (especially the W134-W136 reproducibility-claim mask)
increased the count instead. Per W136 Lesson #7, this is acceptable —
empirical findings disprove plan assumptions.

### 10 git commits ahead of W136 close (`10891f1a7` — W137 prompt update)

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
8. `c95acfe8a` SW5-honesty `docs(wave137-sw5-honesty)` —
   file-processor temporal-localhost dev limit (1 file +19)
9. `b0819053a` SW7 `docs(wave137-sw7-upstream-issues)` — 3 issue
   templates (1 file +258)
10. SW8 `docs(wave137-sw8-audit-handoff)` — AUDIT_WAVE137 + memory +
    N+3 rotation + W138 prompt (TBD when SW8 commits)

Verify session-start: `git log --oneline 10891f1a7..HEAD | wc -l` → **10**
(matches expected post-SW8; if different, investigate before brainstorming).

```bash
git status --short  # Should be clean working tree
ls docs/audits/AUDIT_WAVE*.md  # Should be 3 files: W135/W136/W137
ls docs/audits/archive/AUDIT_WAVE*.md | wc -l  # Should be 23 (W112-W134)
wc -c memory/MEMORY.md  # Should be < 24,400 bytes (auto-load threshold)
```

---

## Bundle baseline post-W137 (CORRECTED via Dockerfile dist-clear fix)

```
dist/client/assets/index-tGuQB5EY.js  TBD bytes (NEW post-W137 fresh build)
dist/client/_shell.html                TBD bytes
dist/client/sw.js                      placeholder (workbox-build skip)
dist/server/server.js                  39,371 bytes (was 39,373 W135-W136)
```

**🚨 CRITICAL §Honesty for W138**: the W134-W136 "BYTE-IDENTICAL build × 3
reproducibility" claim was structurally broken (W137 §Honesty #4 finding).
Same hash because the Docker watch+kill workaround exited immediately on
host-cached `frontend/dist/server/server.js`. W137 SW4-prep fixed via
`rm -rf dist;` before npm run build. **Real W137 baseline going forward**:
`index-tGuQB5EY.js` (NOT `index-DqqHVXgy.js` from W135-W136).

W138 Tier 1 candidate: re-establish CORRECT build × 3 reproducibility
with the corrected Dockerfile (~30 min).

---

## NO-DEPLOY scope continued (W134/W135/W136/W137 carried forward)

Cluster deployment NOT pursued. Goal: "fully working + visually +
internally flawless локально + структурно". Cluster-dependent items
remain removed (Phase 6 actual rollout, RUM wiring, Caddy weight flip
live test, kubectl apply, etc.).

W125-W133 SSR migration arc remains shipped + locally verified +
structurally correct. **W137 verification proves end-to-end SSR auth-
at-edge works through real Docker chain** (the W135 §Honesty #9 closure).

---

## Gates baseline (preserved through W137 + verified post-SW4)

| Gate | Value | Polish status |
|------|-------|---------------|
| `npx tsc --noEmit` | 0 errors | TBD (run in W138 polish) |
| `npm run lint` (max-warnings=0) | 0 errors / 0 warnings | TBD |
| `npx vitest run` single | TBD (W136 baseline 1052p / 12s / 0f) | TBD |
| Cross-session vitest 5-run | TBD | TBD |
| pytest backend slice | **255p / 0f** (extended slice + 5 new W137 SW1 RS256 contract tests) | SW1 ✓ |
| `npm audit` | TBD (W119 SW5 + W130 SW4 baseline 0 vulns) | TBD |
| Cargo.lock no drift | working tree clean | implicit ✓ |
| i18n parity | TBD (W136 baseline 18 tests) | TBD |
| Tree-shake invariant | TBD post-W137 fresh build | TBD |
| Build × 3 reproducibility | NEW BASELINE post-W137 fix | TBD via W138 polish |
| Real Docker chain authed flow (8 SSR routes) | **8/8 200 + AUTHED + 0 hydration errors** | SW4 ✓ NEW |
| W137 SW1 RS256 contract tests | **5p / 0f** | SW1 ✓ NEW |
| tempo-healthprobe + loki-healthprobe | **(healthy)** | SW6 ✓ NEW |
| file-processor healthy | **DEFERRED** (temporal-localhost dev limit) | SW5 §Honesty NEW |
| Active waves (N+3) | W135/W136/W137 | SW8 ✓ |
| Archive directory | 23 entries W112-W134 | SW8 ✓ |

---

## SSR routes (8 total — preserved through W137; FULL VERIFICATION post-SW4)

W137 SW4 verified ALL 8 SSR routes work end-to-end through real Docker
chain via authed Playwright smoke. This is the FIRST wave to verify
the full SSR migration arc end-to-end with real cookies.

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

Remaining `ssr: false`: 2 (messenger × 2 — heavy WebSocket + IndexedDB
at render time, deferred indefinitely under no-deploy).

`/map` + `/activity` preserved at `ssr: 'data-only'` (W127 SW6
annotations under permissive parent `_auth.tsx ssr: true`).

---

## Wave 138 candidates (post-W137)

### Tier 1 — HIGH priority (W137 §Honesty closure)

- **Build × N reproducibility re-establishment** (~30 min). Re-run
  `start-docker.ps1 -Build` × 3 from clean state with the corrected
  `frontend.Dockerfile` (W137 SW4-prep `rm -rf dist;` fix). Assert
  byte-identical hashes for `dist/client/assets/index-*.js` +
  `_shell.html` + `dist/server/server.js`. This is the structurally-
  correct version of the W134-W136 claim. Closes W137 §Honesty #4.

- **file-processor temporal-localhost** (~2-3h structural OR ~30 min
  doc-accept). Rebind temporal to 0.0.0.0 with auth (changes P0-03
  trade-off; needs Temporal token-based auth setup) OR move
  file-processor → host network for dev (network_mode: host) OR
  explicitly accept dev-stack limitation + document. Closes W137
  §Honesty #5.

- **vite-plugin-pwa workbox-build sw.js**: 1 console error per route
  on /dashboard etc. is the Service Worker registration failure
  (placeholder sw.js because workbox-build skipped in watch+kill
  workaround). Closing path: either fix the build-orchestrated
  workaround structurally OR upstream rolldown hang fix lands.

### Tier 2 — Per-page visual audit (NEW FEASIBILITY post-W137)

- **/dashboard visual audit** (~0.5-1 wave). Per W125 SSR design's Phase
  6 ramp + W137 SW4 closure: NOW FEASIBLE to run real Playwright authed
  smoke + LHCI baseline + axe-core a11y on each SSR route in turn.
  Recommend starting with /dashboard (highest traffic, most complex).

- Other 7 SSR routes' visual audits — opportunistic.

### Tier 3 — Inherited tech-debt (carry-forward from W134/W135/W136)

- Test infrastructure expansion: a11y-public WebKit OOM (W115 SW1),
  mobile-webkit /404 (W116 SW1).
- LHCI gate ratchet on REAL W137 baseline (now feasible).
- a11y deep-audit cross-browser.
- i18n parity consolidation.
- Storybook/Chromatic activation (requires user-side
  `CHROMATIC_PROJECT_TOKEN` secret + `vars.CHROMATIC_ENABLED=true`).
- Playwright /login screenshot fragility (W136 SW3 honest deferral) —
  VITE_E2E_MODE-style flag refactor (~30 min).

### Tier 4 — Pre-existing carry-forward (NOT closeable without
                                          structural change)

- **W134 §Honesty #2 (bundle delta)** — superseded by W137 §Honesty
  #4. Real W137 baseline is `index-tGuQB5EY.js` going forward.
- **W134 §Honesty #10 (/messenger Phase 5 punted)** — no-deploy
  decision unchanged. Tier 5 explicit user decision to pursue OR
  punt indefinitely.

### Tier 5 — Optional big scope (explicit user decision)

- **Messenger × 2 polish arc** (~5-7 waves). Per historical anchoring
  (Schedule 14, Map 23, Events 6, Activity 4, News 6, Dashboard ~10):
  messenger has heavy WebSocket + IndexedDB but smaller surface area
  than Map. Pursue OR punt.
- **/admin polish arc** (~3-5 waves). Admin tooling depth audit + UX
  polish. Lower-traffic page. Pursue OR punt.

### Filed upstream issues (SW7) — pending external resolution

- rolldown/rolldown (build hang)
- chromedevtools/chrome-devtools-mcp (Windows headless heavy-DOM eval)
- grafana/tempo + grafana/loki (distroless health CLI)

User files via `gh issue create` per `memory/wave137_upstream_issues.md`
filing instructions.

---

## Pragmatic recommendation (per `feedback_planning_estimates.md` style)

- **Best ROI immediate**: **Tier 1 (build × 3 reproducibility +
  vite-plugin-pwa sw.js)** (~1-2h combined). Closes W137 §Honesty #4
  + vite-plugin-pwa + restores trustworthy reproducibility claim.

- **Best W138 starter combo**: **Tier 1 + Tier 2 (build × 3 +
  vite-plugin-pwa + /dashboard visual audit)** (~2-3h combined).
  Real per-page visual audit becomes the first feasible since SSR
  migration arc started in W125. High user-facing impact.

- **Closes most § Honesty deferrals**: **Tier 1 + Tier 3 (multi-cross-
  cutting)** (~5-7h). Drops to ≤4 § Honesty caveats post-W138.

- **Tier 5 explicit decision**: confirm Messenger/Admin scope OR punt
  before W139+.

### Anti-pattern to avoid (from W137 polish lesson)

Don't claim "build × N reproducibility" without verifying via fresh
build from clean state. The W134-W136 claim was structurally broken
for 3 waves because the Dockerfile bug masked the failure. W138 must
re-establish a CORRECT claim via:
1. `docker compose down`
2. `rm -rf frontend/dist`
3. `start-docker.ps1 -Build` × 3 (separately each time)
4. `sha256sum dist/client/assets/index-*.js dist/server/server.js _shell.html`
5. Assert all 3 sums match.

---

## Anticipated AskUserQuestion 3-question pattern

(W133/W134/W135/W136/W137 success — 5 waves with same pattern)

1. **Q1 — Primary scope tier**: Tier 1 (build × 3 + vite-plugin-pwa
   ~1-2h) vs Tier 1+2 (+ /dashboard visual audit ~2-3h) vs Tier 1+3
   (+ multi-cross-cutting ~5-7h) vs Tier 4 (cross-cutting w/o W137
   §Honesty closures) vs Tier 5 (Messenger/Admin OR punt).

2. **Q2 — Within chosen tier, sub-scope**: e.g.
   - Tier 1 → file-processor temporal fix path (a) rebind 0.0.0.0
     with auth vs (b) host network vs (c) accept-as-dev-limit
   - Tier 2 → which page first (/dashboard recommended; or pick by
     priority)
   - Tier 3 → which inherited item (LHCI ratchet vs WebKit OOM vs
     Storybook activation)

3. **Q3 — Architecture/design (if applicable)**:
   - Tier 1 → if vite-plugin-pwa fix surfaces unrelated build-orchestrated
     issues (similar to W137 SW4-prep Dockerfile dist-clear discovery),
     how to handle in W138 vs W139?
   - Tier 4 → diagnostic budget if W138 surfaces more polish-pass
     surprises (per W136 Lesson #7)

---

## Read mandatory files in order (per `superpowers:using-superpowers`)

1. **`docs/audits/AUDIT_WAVE137.md`** — full SW0-SW7 narrative +
   verification matrix + § Honesty probe (7 caveats: 3 closed via
   implementation + 3 carry from W134/W136 + 4 NEW from W137 polish-
   pass discoveries) + lessons-learned + W138 candidates list at
   bottom.
2. **`memory/wave137_backlog.md`** — close-status entry-point with
   commit references + § Honesty caveats list.
3. **`memory/wave137_upstream_issues.md`** — 3 GitHub issue templates
   ready for `gh issue create` (filing instructions at end).
4. **`memory/wave138_opening_prompt.md`** — this file.
5. **`docs/plans/2026-05-08-wave137-tier1234-design.md`** — W137
   design doc + 3 Explore-agent findings (backend RS256 ready,
   VITE_BACKEND_ORIGIN trap, distroless workarounds).
6. **`CLAUDE.md`** ## Audit Trail W137 row + new gotchas:
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
7. **`memory/MEMORY.md`** — auto-loaded; W137 row at top; W134
   collapsed to one-liner (rotated W137 SW8); W135/W136/W137 verbose
   in Active backlog.
8. **`memory/feedback_perfectionism.md`** — anticipate "безупречно?"
   probe (60-90 min polish budget — W137 used ~75 min total
   diagnostic across SW1-SW4).
9. **`memory/feedback_planning_estimates.md`** — range estimates over
   single numbers; "production-grade polish" anchor 3-5h base +
   variance.

---

## Skills to invoke immediately (per `superpowers:using-superpowers`)

- **`superpowers:brainstorming`** — invoke FIRST per W134/W135/W136/W137
  success pattern (3-question AskUserQuestion). MANDATORY before any
  creative work. DO NOT skip.
- **`superpowers:writing-plans`** — for plan file creation in plan
  mode after brainstorming.
- **`superpowers:systematic-debugging`** — invoke if hitting bugs
  (W136 SW4 + SW5 + polish-v2 + W137 SW4 surfaced REAL bugs via
  reproduce-first pattern; expect more in W138 if Tier 1 work hits
  unrelated upstream issues).
- **`superpowers:verification-before-completion`** — invoke BEFORE
  claiming SW completion (Iron Law: fresh evidence before claims;
  W137 polish surfaced spurious W134-W136 reproducibility claims).
- **`superpowers:executing-plans`** — invoke AFTER plan approval.

---

## Use Context7 MCP (mandatory for library docs)

W138 likely Context7 lookups:
- **`vite-plugin-pwa`** (injectManifest semantics, GenerateSW vs
  injectManifest) — for Tier 1 sw.js fix path
- **`workbox-build`** + **`@rolldown/plugin-babel`** — for hang-trace
  upstream investigation (if rolldown/rolldown issue advances)
- **`@temporalio/sdk`** + Temporal documentation — for Tier 1
  file-processor fix path (a) rebind with auth
- **Playwright API** — page-per-route patterns for visual audit
  scripts in Tier 2

Don't trust agent inferences without Context7 verification. W137 SW4
empirical findings disproved 3 plan assumptions (chrome-devtools wall
extends to Playwright real Chrome too, page.evaluate hangs on heavy
DOM, page-per-route IS the workaround).

---

## Lessons from W137 (carry-forward for W138+)

1. **Empirical findings disprove plan assumptions, ESPECIALLY when
   assumptions piggyback on prior waves' claims** — the W134-W136
   "BYTE-IDENTICAL build × 3" reproducibility claim was inherited as
   ground truth in W137 plan but turned out to be spurious. Treat
   prior-wave reproducibility claims as hypotheses, not truths, until
   re-verified with structural evidence.

2. **`docker compose build` cache cascading masks runtime issues** —
   the watch+kill workaround in `frontend.Dockerfile` looked correct
   at inspection but had a subtle race condition. When adding
   watch+kill or similar build-orchestration patterns, also add
   explicit `rm -rf` before the build to force fresh state. Cross-
   check by examining build duration logs (6s vs 30s+ tells you
   which path was taken).

3. **Pre-existing security trade-offs surface as visible failures
   when adding healthchecks** — W137 SW5 made the file-processor
   temporal-localhost issue visible. When adding healthchecks to
   services that depend on other services with known dev-only
   restrictions, document the inheritance chain in the healthcheck
   comment.

4. **Sidecar healthcheck pattern works for distroless containers but
   breaks downstream depends_on semantics** — W137 SW6 demonstrated
   the trade-off. Document explicitly in compose comments.

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
   W137 SW7 + SW8 both keep memory files in user `.claude` profile +
   repo `memory/` for cross-machine sync. Verified post-SW7 commit.

---

## Final pre-flight checklist (run at session start before brainstorming)

```bash
# 1. Working tree clean + 10 commits ahead of W136 close
git status --short && git log --oneline 10891f1a7..HEAD | wc -l  # → 10

# 2. Active waves W135/W136/W137 + archive 23 entries
ls docs/audits/AUDIT_WAVE*.md  # → 3 files
ls docs/audits/archive/AUDIT_WAVE*.md | wc -l  # → 23

# 3. MEMORY.md size
wc -c memory/MEMORY.md  # → < 24,400 bytes

# 4. Bundle baseline (CORRECTED post-W137)
ls -la frontend/dist/client/assets/index-*.js \
       frontend/dist/client/_shell.html \
       frontend/dist/client/sw.js \
       frontend/dist/server/server.js
# → index-tGuQB5EY.js (or newer if W138 changes bundle) + server.js 39,371

# 5. Cargo.lock idempotent (≥ 27 waves)
git status frontend/rust-crypto/Cargo.lock frontend/wasm-sanitizer/Cargo.lock
# → working tree clean

# 6. Verify Docker stack state
docker ps --format "table {{.Names}}\t{{.Status}}" | head -25
# → 21+ containers Up; tempo-healthprobe + loki-healthprobe (healthy);
# → file-processor (unhealthy) is documented W137 SW5 §Honesty
```

---

**Begin**: brainstorming → AskUserQuestion (3 questions: Q1 scope tier,
Q2 sub-scope, Q3 architecture if applicable) → plan file at
`C:\Users\egorribun\.claude\plans\<auto-generated>.md` → ExitPlanMode →
execute under approved plan.

Use TodoWrite for SW progression tracking. Mark chapters via
`mcp__ccd_session__mark_chapter` when transitioning between SWs.
Invoke `superpowers:verification-before-completion` BEFORE claiming SW
completion (Iron Law: fresh evidence before claims; W137 polish
surfaced multi-wave spurious reproducibility claims).

Anticipate "безупречно?" probe post-final-SW — budget ~60-90 min
polish (potentially multi-round if W138 hits structural surprises).

If W138 picks Tier 1, expect: (a) build × 3 reproducibility re-
establishment is the lowest-risk start (~30 min); (b) file-processor
temporal fix path may surface authentication setup complexity (~2-3h
for proper auth, ~30 min for documented accept); (c) vite-plugin-pwa
sw.js fix may interact with the rolldown upstream hang issue.
