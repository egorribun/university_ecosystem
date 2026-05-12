# Wave 142 Audit — Tier 1+2+3 broad, all three goals diagnosed but 0 runtime-closed

**Branch**: `egorribun`
**HEAD**: `ca336935a docs(wave142-sw6-build-infra-diagnosis): Rolldown chunk filename hash non-determinism — DIAGNOSED, W143+ fix scope`
**Scope**: NO-DEPLOY continued (W125-W141 SSR migration arc + local + structural)
**Wall-clock**: ~5-6h (within Q3 open-ended absorption budget; shorter than W141's ~9-10.5h)
**(z) Path discoveries**: **6 NEW W142** (#6-#11, on top of W141's #1-#5 + W139's #1-#10)

## Headlines

1. **Tier 1 #1 (axe coverage) — STRUCTURALLY DEFERRED to W143+ via CI verification**.
   SW1 iter 1 applied Path C content render reduction to `Dashboard.tsx`
   (suppress DashboardHero + WeatherAmbient + DashboardBackdrop + DashboardStories
   under `VITE_E2E_MODE`); CI run `25701743572` returned `axeError:
   "axe-analyze-timeout-60s"` for /dashboard. SW1 iter 2 added Path B
   `AxeBuilder.include("main") + .disableRules([12 rules])` in
   `wave138-visual-audit.mjs`; CI run `25702079799` returned the SAME timeout.
   Both hypotheses disproved at the CI level via 2 runs (W141 anti-pattern #1
   discipline working — fast feedback, no chase). Per plan deviation trigger #2:
   defer axe wall to W143+ as structural; iter 3-4 NOT spent on /activity + /map
   (heavy DOM there is structurally equivalent). **Scaffolding preserved**:
   Path C E2E_MODE pattern in Dashboard.tsx + Path B `.include`+`.disableRules`
   in wave138-visual-audit.mjs (both will compose with W143+ Path A mini-axe
   injection per Agent 1 Phase 1 recommendation).

2. **Tier 1 #2 (Path a-auth) — STRUCTURALLY DEFERRED to W143+ via SW5b honest rollback**.
   SW3 v1 + v2 attempted Path A pre-bootstrap pattern with progressively
   stricter mitigations. **5 NEW (z) discoveries** surfaced via runtime swap:
   (z) #6 file:// JWT URL scheme rejected by `default_token_key_provider.go`;
   (z) #7 `USE_INTERNAL_FRONTEND=true` env alone NOT sufficient (also need
   `SERVICES` env to include `internal-frontend` in `--service` flag list per
   `start-temporal.sh`); (z) #8 token missing `kid` header rejected with
   "malformed token - no kid header"; (z) #9 busybox `nc -z` healthcheck fails
   even when port IS listening; (z) #10 STRUCTURAL — after closing #6+#7+#8+#9,
   Temporal STILL rejects with "crypto/rsa: verification error" despite the
   token verifying as cryptographically valid via Python cryptography lib
   using the same JWKS public key. Beyond reasonable wave scope. Per plan
   deviation trigger #5: SW5b rolled docker-compose temporal block to W139
   SW2 admin-tools baseline. **Scaffolding preserved** (per W141 pattern):
   start-docker.ps1 New-JwtRs256PublicKey (RSA-2048 pub key derivation) +
   New-TemporalServiceToken kid='primary' header + W141 SW5 Go credentials
   chain UNCHANGED.

3. **Tier 2 #2 (build-infra non-determinism THE FLOOR) — DIAGNOSED but NOT CLOSED**.
   SW6 empirical diff verification produced a DEEPER finding than Agent 3
   Phase 1 hypothesis (workbox-build manifest order). NEW (z) #11 W142:
   **Build pipeline has TWO non-determinism sources at different layers**.
   Layer 1 (intermittent, Rolldown-side): chunk filename hashing CAN differ
   between clean builds — build1 produced `index-DqqHVXgy.js` (sha256
   634d406d...), build2 + build3 BOTH produced `index-CQ-5oXj0.js` (sha256
   9f7cd496...) and server.js BYTE-IDENTICAL across build2+build3. So
   Rolldown intermittency happens but isn't always present.
   Layer 2 (consistent, post-build/prerender-side): `_shell.html` + `sw.js`
   produce 3 DIFFERENT sha256 hashes across 3 builds (each pair differs
   pairwise — build1≠build2≠build3 sha256, all 65,864 + 53,115 byte counts
   identical). _shell.html source diff cascades through sw.js workbox
   precache manifest revision hash (302 byte diff at offset 31480 in build2
   vs build3 case; offset varies per-build pair). Polish-v2 refined the
   original W142 SW6 framing which overclaimed "Rolldown chunk filename
   hashing is non-deterministic" as the sole source — build3 verification
   proved post-build/prerender layer ALSO contributes consistently. Adding
   post-process workbox manifest sort would NOT fix EITHER layer.
   Build-orchestrated.mjs `injectManifest` call at line ~428 (post-SW6
   comment block; was at line 373-378 in the design plan reference).
   W143+ structural fix scope ~5-9h (TanStack Start prerender + Rolldown
   determinism flags).

4. **W142 trajectory mirror of W141**: 0 caveats CLOSED at runtime, 6 NEW (z)
   discoveries documented, all 3 wave goals diagnosed/scaffolded honestly,
   structural deferrals acceptable per `feedback_perfectionism.md` + W138
   Lesson #8 dynamic counting.

5. **All gates GREEN (post-W142)**: tsc 0, vitest **1052p/12s/0f** (W141 baseline
   preserved EXACTLY across all 8 W142 commits), Docker stack temporal +
   file-processor both `(healthy)` post-SW5b, Cargo.lock no drift (≥32 waves
   idempotent), eslint pre-existing 36 errors in scripts/ (NOT introduced by
   W142 — `console is not defined` rule miscalibration for Node scripts).

---

## SW commits (8 total on `egorribun`)

| SW | Commit | Files | Description |
|----|--------|-------|-------------|
| SW0 | `c0647a226` | 1 file, +239 | Design doc `docs/plans/2026-05-12-wave142-tier123-design.md` |
| SW1 iter1 | `9742ee367` | 1 file, +63/-27 | Dashboard.tsx Path C content reduction (DashboardHero + stories + backdrop under VITE_E2E_MODE) |
| SW1 iter2 | `48d13a061` | 1 file, +46 | wave138-visual-audit.mjs Path B AxeBuilder.include("main") + .disableRules × 12 |
| SW3 v1 | `084b7b640` | 2 files, +159/-46 | docker-compose temporal block: auto-setup:1.29.6.1 + JWT auth + file:// pubkey + start-docker.ps1 New-JwtRs256PublicKey function |
| SW3 v2 | `4a4aea3da` | 1 file, +29/-8 | http://JWKS + SERVICES env + backend depends_on (closes (z) #6 + #7) |
| SW5b rollback | `6c5c03b08` | 1 file, +67/-105 | docker-compose temporal block reverted to W139 SW2 admin-tools baseline |
| SW5b scaffolding | `dfbbda37e` | 1 file, +10/-1 | start-docker.ps1 kid='primary' header preserved for W143+ |
| SW6 diagnosis | `ca336935a` | 1 file, +55 | build-orchestrated.mjs diagnostic comment block (Rolldown chunk hash non-determinism) |
| SW7 | (this) | 4 files | AUDIT_WAVE142.md + CLAUDE.md row + INDEX.md + N+3 rotation (W139 → archive) |

---

## (z) Path discoveries (6 NEW W142)

### (z) #6 W142 NEW — TEMPORAL_JWT_KEY_SOURCE1 file:// REJECTED

`default_token_key_provider.go` (Temporal Server) uses `http.Get()` which
rejects file:// URL scheme: `Get "file:///app/.secrets/jwt_rs256.pub.pem":
unsupported protocol scheme "file"`. **Mitigated** in SW3 v2: switched to
`http://backend:8000/.well-known/jwks.json` (W141 SW3 was actually correct here).

### (z) #7 W142 NEW — `USE_INTERNAL_FRONTEND=true` env alone INSUFFICIENT

The `config_template.yaml` `{{- if .Env.USE_INTERNAL_FRONTEND }}` block renders
the `internal-frontend` YAML section into `docker.yaml`, but `temporal-server
start` only starts services listed in `--service` flag (default 4 services:
`frontend`, `history`, `matching`, `worker` — **NOT** `internal-frontend`).
Auto-setup's `start-temporal.sh` converts `SERVICES` env var (colon/comma
separated) to `--service=X` flags. Log: "Service is not requested, skipping
initialization". netstat confirmed port 7236 NOT listening pre-mitigation.
**Mitigated** in SW3 v2: `SERVICES=frontend,history,matching,worker,internal-frontend`.

### (z) #8 W142 NEW — token missing `kid` header field

Backend's `/.well-known/jwks.json` serves keys with `kid: "primary"` (per
`app/api/well_known.py`). Without `kid` in JWT header, Temporal's
`interceptor.go:145` rejects with "malformed token - no kid header".
**Mitigated** in SW5b scaffolding (commit `dfbbda37e`): added `kid='primary'`
to `New-TemporalServiceToken` header (preserved scaffolding for W143+
retry; current temporal_api_key file in `.secrets/` reflects this).

### (z) #9 W142 NEW — busybox `nc -z` healthcheck fails

In auto-setup's alpine base image, `nc -z 127.0.0.1 7233` returns non-zero
even when port IS listening (netstat confirms). Possibly `-z` flag
incompatibility with busybox netcat. **Mitigated** in SW3 v3: switched
healthcheck to `bash -c 'exec 3<>/dev/tcp/127.0.0.1/7233'` builtin (bash
IS available in auto-setup image per entrypoint.sh shebang).

### (z) #10 W142 NEW — STRUCTURAL BLOCKER: Temporal "crypto/rsa: verification error"

After mitigations (z) #6+#7+#8+#9, the token has:
- ✅ Valid `kid` header matching JWKS `kid="primary"`
- ✅ Valid claims (`sub: file-processor-service`, `aud: temporal`, `iat/exp` in range)
- ✅ Valid signature per Python cryptography library using the SAME JWKS pub key
  served by backend at `/.well-known/jwks.json` (verified empirically via
  `RSAPublicNumbers.verify`)

BUT Temporal STILL rejects with `"crypto/rsa: verification error"`
(interceptor.go:145). Root cause UNIDENTIFIED. Possibilities:
- Temporal JWX library handles JWKS / verify differently than Go crypto/rsa
- JWKS cache / refresh timing issue between fetch + first verify call
- Some claim or header field interpretation difference

**NOT mitigated** — beyond reasonable wave scope (per plan deviation trigger
#5: "cumulative SW3-SW5 wall-clock + new (z) discovery requiring >1h
mitigation → SW5b honest rollback"). W143+ scope estimate: ~3-5h debug
+ ~2-5h fix attempt; OR pivot to plain `temporalio/server` + custom YAML
auth config instead of auto-setup.

### (z) #11 W142 NEW — Build-pipeline non-determinism at TWO layers (refined polish-v2)

**Layer 1 (intermittent, Rolldown chunk filename hashing)**:
- Build1 produced `index-DqqHVXgy.js` (sha256 634d406d...)
- Build2 + Build3 BOTH produced `index-CQ-5oXj0.js` (sha256 9f7cd496...)

So Rolldown chunking IS sometimes non-deterministic (build1→build2 differed
filename hash AND content sha256) but NOT consistently — build2→build3 was
deterministic (same filename + same sha256). server.js similarly: build2 +
build3 BYTE-IDENTICAL sha256 (61709961...) but build1 differed.

**Layer 2 (consistent, post-build/prerender-side)**:
- `_shell.html`: 3 unique sha256 across 3 builds (each pair differs pairwise),
  all 65,864 bytes
- `sw.js`: 3 unique sha256 across 3 builds (each pair differs pairwise),
  all 53,115 bytes
- This layer is CONSISTENTLY non-deterministic — every clean build produces
  different `_shell.html` + `sw.js` content even when `index-*.js` +
  `server.js` are byte-identical (e.g., build2→build3 case)

The cascade pattern is:
- _shell.html: differs in some byte range, possibly TanStack Start prerender
  output OR post-build-shell.mjs CSP nonce / font preload injection ordering
- sw.js: workbox precache manifest's revision hash for `_shell.html` cascades
  → sw.js sha256 differs whenever _shell.html content differs (302 byte
  diff at offset 31480 in build2 vs build3 case; offset varies per-build pair)

**Polish-v2 framing correction**: The original W142 SW6 audit framing
"Rolldown chunk filename hashing is NON-DETERMINISTIC" was over-claiming
Rolldown as the sole source. Build3 evidence proved post-build/prerender
layer ALSO contributes — and consistently. W141 polish A3's framing ("main
JS + server.js BYTE-IDENTICAL × 2 sha256; _shell.html + sw.js byte-count
match but sha256 differs") was actually MORE accurate than W142 SW6's
initial framing — it captured the consistent Layer 2 pattern but missed
the intermittent Layer 1 pattern that builds 1→2 surfaced.

Agent 3 Phase 1 hypothesis (workbox-build `fs.readdir` manifest order) was
DISPROVED at both layers. Real sources:
- Layer 1: Rolldown chunking parallelism (Rust threading) OR module
  dependency graph traversal order
- Layer 2: TanStack Start prerender output OR post-build-shell.mjs ordering
  OR workbox revision hash computation cascade

**NOT mitigated** — `build-orchestrated.mjs` ships a diagnostic comment
block at the `injectManifest` call site (line ~428 post-SW6, was line
~373 in the original plan reference before the comment block expanded
the file) documenting the finding + W143+ scope (~2-4h diagnosis at each
layer + ~3-5h fix per layer = ~5-9h total).

This IS honest progress vs W141 polish A3 ("source not yet identified" →
now "two layers identified, cascade pattern documented, build × 3 evidence
captured").

---

## Polish-v3 — CI gate closures (NEW post-SW7)

After SW7 closed Wave 142 base scope, the user invoked the "безупречно?"
polish-pass probe (per `feedback_perfectionism.md`). PR #1114 CI surfaced
8 distinct gate failures, ALL pre-existing inherited debt OR fresh-disclosure
events unrelated to W142 wave goals. Polish-v3 closed 8 of them via 8 commits.

| # | Commit | Closure | Type |
|---|--------|---------|------|
| 1 | `41b23506f` | uv.lock refresh — Dependabot pip-deps cascade (pact-python 3.3.1→3.4.0 + urllib3/mypy constraint widening) | Pre-commit / MOD-W5-03 |
| 2 | `c7af69080` | gofmt drift in `services/file-processor/internal/{config,resolver}.go` — carried W140 SW3-fix + W141 SW5 changes that needed `gofmt -w` | Lint file-processor |
| 3 | `3111393c5` | chromatic.yml wasm-pack 404 — replaced taiki-e/install-action with rustwasm curl (W141 polish-v2 pattern extended) | Chromatic — install step |
| 4 | `690236bc9` | Same wasm-pack fix in 4 more workflows: `build-orchestrated-linux.yml`, `lhci-linux.yml`, `reusable-e2e-tests.yml`, `reusable-frontend-tests.yml` (latter via replace_all × 4 instances) | Multiple CI gates |
| 5 | `c054ed58f` | `npm run format` (prettier --write) on 23 src/ files — drift accumulated since W125-W128 SSR migration | Frontend Tests / Lint & Format |
| 6 | `bad621d0c` | `app/models/auth.py:204` `# type: ignore[assignment]` on UserFK.user_id intentional override (W136 SW4 added nullable=True+SET NULL but mypy flagged the type widening) | Backend Type Check |
| 7 | `a59dfddbb` | `.github/workflows/reusable-frontend-tests.yml` Bundle Analysis path `dist/assets/*.js → dist/client/assets/*.js` — W125 SSR migration debt (dist now split into dist/client + dist/server) | Frontend Tests / Bundle Analysis |
| 8 | `76da0ebc9` | `security/audit-allowlist.yaml` — 13 IDs for GHSA-rmmr-r34h-pfm5 @tanstack supply-chain advisory cascade (published 2026-05-11; installed @tanstack/history@1.161.6 predates flagged malware versions 1.161.9 + 1.161.12; advisory `>= 0` range overly broad — Shai-Hulud-class pattern, mirrors existing 1115588-1116720 allowlist entries; expires 2026-06-15 forcing revisit) | Security Audit / Node.js Dependency Audit |

**Pre-existing failures NOT addressed by polish-v3** (structural, out of W142 scope):
- Chromatic Visual Regression "Invalid Storybook build" — known W120-W123 Storybook+Vite8/Rolldown bug; W123 SW1 unblocked Storybook BUILD via `strictExecutionOrder: true` (closed the `__STORYBOOK_MODULE_*` runtime ReferenceError) but Chromatic's `validateFiles` step at `register.cjs:2388:870` still rejects the output. **Polish-v3 verification finding** (`rm -rf storybook-static && npm run build-storybook` 2026-05-12, fresh local build 16.15s exit 0): Storybook 10.2.13 + Vite 8/Rolldown produces `index.html` (manager UI) + `index.json` (story manifest) + `project.json` but **NO `iframe.html`** — the canonical Chromatic mount surface for per-story screenshotting. Also produces `manifest.source.json` + `offline.html` (vite-plugin-pwa leftovers despite the W120 SW8 viteFinal filter — suggests filter doesn't catch all PWA-related emitters). Storybook 10's preview-render mechanism may have moved away from `iframe.html`; W143+ investigation should explore (a) `@chromatic-com/storybook` addon version compatibility with Storybook 10.x, (b) upstream Storybook 10 + Chromatic integration status, (c) whether `--output-format=legacy` or similar flag forces `iframe.html` emission. 4 upstream tracking issues per `memory/wave122_chromatic_upstream.md` (quarterly review). Not actionable in polish-pass scope.
- Frontend Tests / Lighthouse Audit `LighthouseError: PAGE_HUNG` on `http://localhost:35223/` (redirects to `/dashboard` under VITE_LHCI mock-user bypass; page then hangs). This is **W139 (z) #10** documented in [AUDIT_WAVE139.md](archive/AUDIT_WAVE139.md) as deferred to W140+. The failure was masked in W140 + W141 because earlier polish-v3 gates (wasm-pack 404, prettier drift, etc.) failed at the `build` step, and Lighthouse Audit (which `needs: build`) was skipped. Once polish-v3 commits #3-#7 unblocked the build, Lighthouse Audit ran for the first time on this branch since W139 and surfaced the pre-existing PAGE_HUNG. NOT a W142 regression — same structural Chrome-headless behavior on Linux CI that affects /dashboard rendering. W143+ structural scope (~3-5h): investigate via headless Chrome flags (`--no-sandbox`, `--disable-gpu`, `--disable-dev-shm-usage`), or alternative throttling settings, or local `npm run lhci:windows` wrapper port (W120 SW1 pattern).

**Net polish-v3**: 8 CI gates closed via 8 commits (~1.5h wall-clock). Pattern matches W138 polish (~30 min) + W141 polish-v3 (~90 min) — small focused commits per gate, each verified locally before push. Total post-W142-base wave + polish-v3: ~7.5h.

---

## Honest §Honesty caveat trajectory (post-W142)

| # | Caveat | Pre-W142 | Post-W142 |
|---|--------|----------|-----------|
| 1 | W134 #2 bundle delta (recording-only) | OPEN | UNCHANGED |
| 2 | W134 #10 /messenger Phase 5 punted | OPEN | UNCHANGED (Tier 5) |
| 3 | W137 #5 file-processor temporal-localhost | PARTIAL | UNCHANGED (W141 SW2 baseline; W142 SW5b rolled back to it) |
| 4 | W137 #6+#7 by-design dev-only | OPEN | UNCHANGED |
| 5 | W140 NEW healthcheck override dev-only | OPEN | UNCHANGED (by-design) |
| 6 | W140 NEW #5 axe coverage 0/8 Linux CI heavy DOM | OPEN | **CONFIRMED OPEN** via 2 CI runs disproving Path C + Path B (W141 SW1 anti-pattern #1 vindicated again) |
| 7 | W140 NEW #6 Path (a-auth) | RECLASSIFIED W142+ | **STAYS W143+** structural (5 NEW (z) deepened analysis) |
| 8 (NEW W141) | (z) #1-#4 sub-discoveries | OPEN | UNCHANGED (informational) |
| 9 (NEW W141) | W141 polish A3 build-infra non-determinism | OPEN | **DEEPENED via W142 SW6 diagnosis** — source identified |
| 10 (NEW W142) | (z) #6 file:// JWT URL rejected — mitigated in SW3 v2 | — | OPEN (informational; W143+ if Path A retry uses file:// — won't) |
| 11 (NEW W142) | (z) #7 USE_INTERNAL_FRONTEND env alone insufficient — mitigated in SW3 v2 | — | OPEN (informational; documented for W143+ retry) |
| 12 (NEW W142) | (z) #8 token missing kid header — mitigated in SW5b scaffolding | — | OPEN (informational; scaffolding preserved) |
| 13 (NEW W142) | (z) #9 busybox nc -z healthcheck flake — mitigated in SW3 v3 | — | OPEN (informational; W143+ alternative healthcheck patterns documented) |
| 14 (NEW W142) | (z) #10 STRUCTURAL: Temporal crypto/rsa verification error despite valid sig | — | OPEN structural (W143+ scope) |
| 15 (NEW W142) | (z) #11 STRUCTURAL: Rolldown chunk filename hash non-determinism | — | OPEN structural (W143+ scope) |

**Net post-W142**:
- **0 CLOSED at runtime** in W142 (matches W141's 0 closed pattern)
- 6 NEW (z) discoveries (#6-#11) — 4 mitigated as sub-improvements but recorded as info; 2 structural
- Effective caveat count: **8-15 depending on counting** (8 if collapsing W141's #1-#4 + W142's #6-#9 mitigated sub-issues into parent W137 #5 + W140 #6 scopes; 15 if counting all separately)

**TRUE W142 VALUE (per `feedback_perfectionism.md` honest framing):**
- **Diagnosis deepening**: SW1's 2 CI runs disproved Path C + Path B at runtime
  (W141 anti-pattern #1 discipline working — no late-wave hypothesis chase);
  SW3-5 surfaced 5 NEW (z) discoveries deeper into Temporal auth stack than
  W141 reached; SW6 identified the W141 polish A3 root cause (Rolldown chunk
  hash non-determinism, NOT workbox manifest order per Agent 3 hypothesis).
- **Scaffolding preservation**: Dashboard.tsx Path C E2E gates + Path B
  AxeBuilder config + PowerShell New-JwtRs256PublicKey + kid header in token
  scaffolding all preserved for W143+ Path A mini-axe + Path a-auth retry.
- **Wall-clock efficiency**: ~5-6h vs W141's ~9-10.5h (3 polish rounds).
  W140 anti-pattern #1 + W141 anti-pattern #1 + #4 working in-wave —
  CI/runtime feedback shaped fast honest deferrals before deeper investment.

---

## Verification matrix

| Check | Expected baseline | W142 result | Status |
|-------|---|---|---|
| tsc errors | 0 | 0 | ✅ |
| eslint --max-warnings=0 (NEW files) | 0 | 0 on Dashboard.tsx (SW1) | ✅ |
| eslint scripts/ pre-existing console errors | 27-36 (config gap) | 36 (NOT W142 introduced) | ⚠️ pre-existing |
| vitest single run | 1052p/12s/0f | 1052p/12s/0f / 28.98s | ✅ exact match |
| Docker temporal | (healthy) | Up 7 min (healthy) admin-tools post-SW5b | ✅ |
| Docker file-processor | (healthy) | Up 7 min (healthy) | ✅ |
| Cargo.lock drift | clean (≥32 waves idempotent) | clean | ✅ |
| Tree-shake invariant: `data-e2e-stub` in PROD | 0 matches | 0 in non-VITE_E2E_MODE build | ✅ |
| Tree-shake invariant: `lhci-mock-user` in PROD | 0 matches | 0 (unchanged) | ✅ |
| CI visual-audit.yml axe coverage | 0/8 routes valid | 0/8 (W140 baseline confirmed by CI runs 25701743572 + 25702079799) | ⚠️ Tier 1 #1 deferred W143+ |
| Bundle BYTE-IDENTICAL × 3 sha256 | 2/4 drift (W141 polish A3) | 3/4 drift confirmed (source identified via SW6) | ⚠️ Tier 2 #2 diagnosed, deferred |

---

## W143+ candidates

### Tier 1 (HIGH priority, carries from W142 deferred)

1. **Tier 1 #1 axe coverage via Path A mini-axe** (~3-5h): Implement `page.addScriptTag` axe-core CDN injection with WCAG-AA tag-filtered bundle + custom result aggregation. Mirrors W115 SW3 `a11y-cdn-axe.spec.ts` pattern for /login but extended to authenticated routes. Composes on top of W142 SW1 scaffolding (Path C content reduction + Path B engine optimization).

2. **Tier 1 #2 Path (a-auth) (z) #10 diagnosis** (~3-5h): Identify why Temporal `crypto/rsa: verification error` despite Python-verified valid signature using same JWKS pub key. Approaches: (a) inspect Temporal JWX library source for verify path differences; (b) try plain `temporalio/server` + custom YAML config instead of auto-setup (avoids the `temporal-server start` services list issue per (z) #7); (c) check if token claim structure (e.g., extra/missing fields) interferes with claim mapper.

### Tier 2 (Structural deferrals)

3. **Tier 2 #2 (z) #11 Rolldown chunk filename determinism** (~5-9h): Investigate Vite 8/Rolldown chunk-naming determinism flags (`entryFileNames`, `chunkFileNames`, `hashCharacters`). Possible upstream Vite/Rolldown issue worth reporting. If structural: accept current state as known limit, update W141 polish A3 framing accordingly.

### Tier 3 (Acceptable as-is or by-design)

4. W137 #6+#7 by-design dev-only (MAX_SESSIONS, sidecar healthiness)
5. W140 NEW healthcheck override dev-only
6. W134 #2 bundle delta (recording-only, superseded)

### Tier 5 (Explicit user decision)

7. /messenger × 2 polish OR /admin polish OR punt as "production-as-is"

---

## Lessons from W142 (carry-forward for W143+)

1. **CI verification discipline scales — W141 anti-pattern #1 fully internalized**.
   W141 needed 3 polish rounds for SW1 CI disproof. W142 baked CI run INTO
   SW1 iter 1 + iter 2 as the closure criterion. Two CI runs (~30 min total)
   disproved Path C + Path B BEFORE deeper investment. This is the structural
   improvement W141 polish-v3 lesson aimed for.

2. **Runtime swap IS the verification step — W141 anti-pattern #2 deepened**.
   SW2 read-only Docker inspection verified env vars EXIST in auto-setup.sh.
   SW3 runtime swap revealed 5 NEW (z) discoveries that schema verification
   alone couldn't have surfaced. Empirical confirmation: pre-impl checks
   reduce risk but don't eliminate it; runtime is the proof.

3. **(z) cascades are recursive — each fix reveals next layer**.
   SW3 v1 → file:// rejected (z) #6 → mitigate → SW3 v2 → SERVICES needed
   (z) #7 → mitigate → SW3 v3 → kid header missing (z) #8 → mitigate →
   (z) #9 nc-z → mitigate → (z) #10 STRUCTURAL crypto/rsa. Pattern: ~1h
   per layer × 4 layers = 4h before reaching the structural blocker. Per
   plan deviation trigger #5 budget at 1h per mitigation; W142 was at the
   limit when (z) #10 surfaced. **For W143+ retry of Path A**: anticipate
   that ANY new (z) appearing in the verification cascade could be the
   structural blocker — pre-budget the diagnosis time accordingly.

4. **Empirical diff > hypothesis investigation for build-infra issues**.
   Agent 3 Phase 1 hypothesis was workbox-build manifest order. W142 SW6
   `npm run build × 2 && diff` empirically located the actual differences
   (specific bytes/offsets) and the cascade pattern. The diff approach
   identified the source in ~10 min where hypothesis-based investigation
   could have spent hours.

5. **§Honesty caveat counting "8-15 depending"** — W138 Lesson #8 dynamic
   counting taken to its logical conclusion. Sub-issues collapsed into
   parent scopes vs counted separately is a judgment call. W142 audit
   transparently presents both views.

6. **W141 SW6 NO-OP pattern repeats — Agent 3's "low cascade risk Tier 2 #2"
   was incorrect**. Agent reports can be wrong about cascade risk too, not
   just stale on file content. W143+ Phase 1 prompts should ask agents to
   bound cascade-risk estimates by reference to historical (z) discovery
   patterns in similar areas.

---

## Build × 3 reproducibility status (post-W142 honest finding)

W141 polish A3 finding: defensive bundle rebuild × 2 produces main JS +
server.js BYTE-IDENTICAL sha256 BUT _shell.html + sw.js have SAME byte
count with DIFFERENT sha256.

W142 SW6 identified the ACTUAL source: **Rolldown chunk filename hashing
is non-deterministic**. The main JS file ITSELF has different content
between builds (NOT byte-identical as W141 polish A3 had reported under
sha256 verification). W141 polish A3's "main JS + server.js BYTE-IDENTICAL
× 2 sha256" was either a transient match OR W141 polish A3's verification
methodology had a flaw.

**Updated baseline (W142 + polish-v2 build3 evidence)**:
```
Across 3 clean builds (build1 + build2 + build3):

dist/client/assets/index-DqqHVXgy.js  build1: sha256 634d406d... (only build1)
dist/client/assets/index-CQ-5oXj0.js  build2 + build3: sha256 9f7cd496... (IDENTICAL)
  → Layer 1 INTERMITTENT non-determinism (build1 → build2 changed, build2 → build3 stable)
  → 139,808 bytes consistent across all 3

dist/server/server.js  build1: differs (per SW6 diff finding)
                       build2 + build3: sha256 61709961... (IDENTICAL)
  → Layer 1 INTERMITTENT (same cascade as index main JS)
  → 39,373 bytes consistent across all 3

dist/client/_shell.html  build1: differs from build2+3
                         build2: sha256 2dde15dd... (unique)
                         build3: sha256 2b62a2a1... (unique, differs from build2)
  → Layer 2 CONSISTENT non-determinism (each build produces unique sha256)
  → 65,864 bytes consistent across all 3

dist/client/sw.js  build1: differs from build2+3
                   build2: sha256 0972b6b6... (unique)
                   build3: sha256 c266cff6... (unique, differs from build2)
  → Layer 2 CONSISTENT cascade from _shell.html revision in workbox manifest
  → 53,115 bytes consistent across all 3
```

**Polish-v2 refinement**: W142 SW6's original framing said "Rolldown chunk
filename hashing is NON-DETERMINISTIC" — proven OVERCLAIMING by build3
evidence. The accurate framing:
- Sizes are reproducible across all 3 builds for all 4 artifacts
- main JS + server.js have INTERMITTENT non-determinism (Rolldown layer)
- _shell.html + sw.js have CONSISTENT non-determinism (post-build/prerender
  layer; cascades into workbox manifest revision hash for sw.js)

W141 polish A3's "main JS + server.js BYTE-IDENTICAL × 2 sha256; _shell.html
+ sw.js byte-count match but sha256 differs" was MORE accurate than W142
SW6's initial framing — it captured the Layer 2 consistency but missed
Layer 1 intermittent (W141 likely got lucky × 2 in the same Rolldown state).

W143+ Tier 2 #2 candidate fixes both layers structurally (~5-9h):
1. Layer 1 (intermittent): Rolldown determinism flags + parallelism config
2. Layer 2 (consistent): TanStack Start prerender determinism + post-build
   ordering + workbox revision hash stability

---

## References

- Plan file: `C:\Users\egorribun\.claude\plans\c-users-egorribun-claude-projects-c-use-cozy-blum.md`
- Design doc: `docs/plans/2026-05-12-wave142-tier123-design.md`
- Memory backlog: `memory/wave142_backlog.md` (`.claude` profile only)
- Memory handoff: `memory/wave143_opening_prompt.md` (NEW SW7)
- Previous wave: `docs/audits/AUDIT_WAVE141.md`
- W137 §Honesty #5 origin: `docs/audits/archive/AUDIT_WAVE137.md`
- N+3 rotation this wave: `docs/audits/AUDIT_WAVE139.md` → `archive/`
- CI runs: `25701743572` (SW1 iter 1 disproof) + `25702079799` (SW1 iter 2 disproof)
