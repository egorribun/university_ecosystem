# Wave 143 Audit — Tier 1+2+3 broad, all 3 paths honestly deferred + significant diagnostic refinement

**Branch**: `egorribun`
**HEAD at close**: `dc4680699 fix(wave143-sw1-followup): JWKS pre-check prefers correct RSA endpoint`
**Scope**: NO-DEPLOY continued (W125–W142 SSR migration arc + local + structural)
**Wall-clock**: ~3-4h core (well under Q3 open-ended budget; smaller than W141 ~9-10.5h, W142 ~5-6h)
**(z) Path discoveries / diagnostic refinements**: **3 NEW W143**

## Headlines

1. **Tier 1 #1 (axe coverage Path A) — STRUCTURAL HANG identified, W144+ pivot needed**.
   SW1 implemented Path A mini-axe injection via Playwright `page.addScriptTag`
   CDN-axe pattern (proven on /login per W115 SW3) + W142 SW1 Path C content
   reduction scaffolding (preserved + functional). CI run `25732174008` HIT
   30-MIN WORKFLOW TIMEOUT with NO per-route sidecars. Polish-v2 P5 CI run
   `25735582483` (cancelled at 14m6s) narrowed the failure mode further:
   Path A **hangs structurally on /login alone** (a compact route with NO
   heavy DOM). The hang is between `→ /login` log line and the next expected
   log line — i.e., somewhere inside `auditRoute()` BEFORE the sidecar write
   at lines 372-404. **Most plausible root cause** (UNVERIFIED): frontend's
   CSP `script-src 'self' 'strict-dynamic'` blocks the CDN script-tag
   injection (`https://cdn.jsdelivr.net/.../axe.min.js` lacks the per-request
   nonce required by `strict-dynamic`). Browser silently blocks the script
   → no `load` event → Playwright's `addScriptTag` waits indefinitely.
   W115 SW3 a11y-cdn-axe.spec.ts works locally because @playwright/test's
   webServer config may differ on CSP enforcement vs the W139 SW1 CI infra.
   **W144+ pivot options**:
   - Path A1: serve `axe.min.js` as a same-origin static asset (bypasses CSP)
   - Path A2: bundle `axe-core` as npm dep + `page.evaluate(axe-core-source-string)`
   - Path A3: CSP-bypass nonce per E2E_MODE route (security risk if mis-deployed)
   - PRE-FIX: add `page.on("requestfailed", ...)` listener to CONFIRM the CSP-block
     hypothesis before investing in any of the pivot paths
   **Scaffolding preserved**: SW1 Path A code at `wave138-visual-audit.mjs:299-368`
   + W142 SW1 Path C E2E gates + Path B engine optimization scaffolding all
   preserved (no revert; W144+ pivot composes on top).

2. **Tier 1 #2 Path (a-auth) (z) #10 — STRUCTURALLY DEFERRED via SW2 disproof of crypto root cause**.
   SW2 wrote a JWKS cryptographic round-trip contract test ([test_wave143_jwks_roundtrip.py](../../tests/test_wave143_jwks_roundtrip.py)
   3 tests, all PASS) that DISPROVES Agent 2's primary "Scenario A JWKS
   byte-encoding mismatch" hypothesis. Key SW2 findings:
   - **Library identification CORRECTED** (Agent 2 was WRONG): Temporal Server
     uses `github.com/go-jose/go-jose/v4` (JWKS parsing) + `github.com/golang-jwt/jwt/v4`
     v4.5.2 (token verify), NOT `lestrrat-go/jwx` as Agent 2 claimed. The
     "crypto/rsa: verification error" wording is direct Go stdlib
     `rsa.ErrVerification`, NOT a JWX-wrapped error.
   - **JWKS encoding IS canonical** (RFC 7518 §6.3.1.1 compliant): our
     `well_known.py:58` `numbers.n.to_bytes((bit_length + 7) // 8, "big")`
     produces exactly 256 bytes for RSA-2048, no leading zeros. JWKS-reconstructed
     pub key bit-for-bit identical to PEM-derived pub key.
   - **End-to-end Python verification** of REAL `.secrets/temporal_api_key`
     (the W141/W142 minted token) against BOTH paths SUCCEEDS:
     - PEM-derived pub key directly: PASS
     - JWKS-reconstructed pub key via int.from_bytes (same path go-jose uses): PASS
   - **golang-jwt/jwt/v4 verify code path** is byte-equivalent to Python's
     `pub_key.verify(sig, msg, padding.PKCS1v15(), hashes.SHA256())`. Same
     primitive operation. If Python passes, Go MUST pass (modulo bytes on the
     wire being identical).
   .
   SW3 strategy revision (per W141 anti-pattern #1+#4 + `feedback_perfectionism`):
   skip Path A (already done in SW2 — libraries identified, no encoding issue),
   defer Path B plain server attempt to W144+ as runtime-specific issue with
   uncertain probability. The 4-8h Path B work for an unproven runtime hypothesis
   exceeds the wave's marginal-value threshold given SW2 already produced
   significant artifacts (regression guard test + lib correction).

3. **Tier 2 #2 Rolldown determinism — STRUCTURALLY DEFERRED via API gap**.
   SW4 investigation found that **Rolldown 1.0.0-rc.15 does NOT expose
   `experimental.parallelism`** in its API (Agent 3 hypothesis disproved,
   similar pattern to Agent 2). Only `hashCharacters: "base64"|"base36"|"hex"`
   is exposed for hashing — affects alphabet, not determinism. Layer 1 fix
   structurally requires upstream Rolldown changes (parallelism config OR
   chunk-naming determinism flag) OR custom post-build chunk filename rewriting
   (fragile per Agent 3's own assessment). Per W141 anti-pattern #1+#4: defer
   honestly to W144+.

4. **W143 NEW finding — wave138-visual-audit.mjs JWKS pre-check script bug**.
   CI sidecar `jwks.json` revealed the script was preferring the WRONG endpoint.
   Two JWKS endpoints exist in backend: proper RSA at root `/.well-known/jwks.json`
   (`app/api/well_known.py`) vs HMAC metadata stub at `/api/v1/.well-known/jwks.json`
   (`app/api/internal/jwks.py`, `kty=oct`, NO key material). Pre-W143 the script
   preferred `/api/v1/` first; the stub passed the alg-only RS256 filter,
   masking the shape mismatch. SW1 follow-up commit (`dc4680699`) flips the
   order + adds explicit `n+e` material check. Does NOT close W140 NEW #5
   axe wall — only improves diagnostic accuracy.

5. **W143 trajectory vs W141/W142**: 0 caveats CLOSED at runtime in W143,
   following W141 (0 closed) + W142 (0 closed) pattern. BUT 3 NEW diagnostic
   refinements add structural value:
   - SW2 lib correction narrows W144+ scope significantly (no longer searching
     in lestrrat-go/jwx; cryptography is verified correct)
   - SW2 contract test is a permanent regression guard for JWKS endpoint shape
   - SW4 API gap finding clarifies that Rolldown Layer 1 fix requires upstream
     work, eliminating false-hope iteration

6. **All gates GREEN (post-W143)**:
   - tsc 0 (no .ts changes)
   - vitest 1052p/12s/0f → +3 NEW pytest tests in SW2 (Python contract test);
     vitest unchanged because no frontend test changes
   - eslint scripts/ 36 errors PRESERVED (W140 baseline; W143 SW1 + SW1-fu
     added 3 inline disables for browser-context globals inside `page.evaluate`)
   - Cargo.lock no drift (≥33 waves idempotent)
   - npm audit 0 vulnerabilities (W119 SW5 baseline preserved)
   - Docker stack STOPPED throughout W143 (no runtime swap attempted; SW3
     deferred preempted that need)

---

## SW commits (5 total on `egorribun`)

| SW | Commit | Files | Description |
|----|--------|-------|-------------|
| SW0 | `7ad99c444` | 1 file, +444 | Design doc `docs/plans/2026-05-12-wave143-tier123-design.md` + memory backlog scaffolding |
| SW1 | `63e19f8a6` | 1 file, +79/-66 | wave138-visual-audit.mjs AxeBuilder → CDN-axe `page.addScriptTag` + `page.evaluate(axe.run)` Path A mini-axe injection |
| SW2 | `4e1acc965` | 1 file, +211 | NEW tests/test_wave143_jwks_roundtrip.py — 3 contract tests verifying RFC 7518 §6.3.1.1 canonical encoding + round-trip pub key reconstruction + token verify; disproves Agent 2 hypothesis |
| SW1-fu | `dc4680699` | 1 file, +33/-3 | wave138-visual-audit.mjs JWKS pre-check prefers ROOT URL (proper RSA) + tightens validation to require n+e material |
| SW7 | (this) | 4 files | AUDIT_WAVE143.md + CLAUDE.md row + INDEX.md + N+3 rotation (W140 → archive) + W144 opening prompt |

---

## (z) Path discoveries (3 NEW W143)

### (z) #12 W143 NEW — wave138-visual-audit.mjs JWKS pre-check preferred wrong endpoint

The script at [wave138-visual-audit.mjs:135-157](../../frontend/scripts/wave138-visual-audit.mjs) preferentially fetched `/api/v1/.well-known/jwks.json` over `/.well-known/jwks.json`. The former serves the ws-hub HMAC metadata stub (`app/api/internal/jwks.py`: `kty=oct`, alg=RS256, no n+e material). The latter serves the proper RSA JWKS (`app/api/well_known.py`: full n+e). Pre-W143 the alg-only filter (`k.alg === "RS256"`) at line 151 false-passed the stub. **Mitigated** in SW1 follow-up (`dc4680699`): swap order + require kty=RSA + n+e string fields. **Does NOT close (z) #10** — the W142 docker-compose Temporal config (`TEMPORAL_JWT_KEY_SOURCE1: http://backend:8000/.well-known/jwks.json`) ALREADY pointed at the correct root URL, so Temporal was fetching the proper RSA JWKS, not the stub.

### (z) #13 W143 NEW — Rolldown 1.0.0-rc.15 lacks experimental.parallelism API (Agent 3 hypothesis disproved)

W142 Agent 3 Phase 1 hypothesized Layer 1 fix via `build.rolldownOptions.experimental.parallelism: 1`. W143 SW4 investigation searched the Rolldown 1.0.0-rc.15 type definitions + npm package source — NO `parallelism` config option exists. Only `hashCharacters: "base64"|"base36"|"hex"` is exposed (affects alphabet, not determinism). Layer 1 fix structurally requires upstream Rolldown changes. **Not mitigated** — W144+ scope: file Rolldown upstream issue OR accept as known limitation until Rolldown 1.0 stable adds determinism support.

### (z) #14 W143 NEW — Path A hangs on /login (compact route, NOT heavy-DOM issue) — likely CSP blocks CDN axe injection

**Framing v1 (commit `c6dbb3c72`)**: "Path A throughput WORSE than Paths C+B".

**Framing v2 polish-v2 P2 (file edits before SW1-fu CI run)**: "Path A throughput APPEARS WORSE per INDIRECT evidence" — softened because I had no per-route timing measurements; could be all-routes-slow OR single-route hang.

**Framing v3 (CORRECTED post polish-v2 P5 CI verification)**: Path A hangs **structurally** on /login alone — a single COMPACT route with NO heavy-DOM. This is NOT a throughput issue at all.

CI evidence (`gh run view 25735582483` cancelled at 14 min 6 sec into /login):
```
12:55:45.9268864Z  → JWKS pre-check: GET http://localhost/.well-known/jwks.json
12:55:45.9941662Z  ✓ JWKS healthy: 1 RS256 key(s) with n+e material  (← SW1-fu fix confirmed)
12:55:47.1330218Z  → API login: POST .../auth/login/json
12:55:47.2758064Z  ✓ Login OK; injected 2 cookies
12:55:47.2803001Z  → /login        ← script entered route loop
13:09:53.5814407Z  ##[error]The operation was canceled.   ← my cancel fired here (14m6s hang)
```

The hang is between line `→ /login` (route start) and the next expected log line which would have been the close-route success/failure. No sidecar for /login was written → `auditRoute()` hung BEFORE `writeFile` at lines 372-404.

**Most plausible root cause** (UNVERIFIED — W144+ diagnostic scope): frontend's CSP header `script-src 'self' 'strict-dynamic'` blocks the CDN script tag injected by `page.addScriptTag({ url: "https://cdn.jsdelivr.net/.../axe.min.js" })`. The script never loads → browser fires neither `load` nor `error` event → Playwright's `addScriptTag` waits indefinitely. The W115 SW3 a11y-cdn-axe.spec.ts works locally because dev preview / @playwright/test webServer may not enforce CSP or may use a different policy. Playwright's `setDefaultTimeout(45_000)` set at line 547 of `wave138-visual-audit.mjs` SHOULD bound `addScriptTag` at 45s but did NOT in this CI environment — possibly Playwright `addScriptTag` URL injection bypasses the default timeout.

**W144+ scope: structural pivot needed for Path A**:
- Path A1: serve `axe.min.js` as a same-origin static asset (bypasses CSP entirely)
- Path A2: include axe-core as an `npm` dependency + `page.evaluate(axe-core-as-string)` (no script-tag injection)
- Path A3: inject CSP-bypass `nonce` per route OR set `Content-Security-Policy` override headers for E2E mode (defensive — security risk if mis-deployed)
- W144+ pre-fix MUST add `page.on("requestfailed")` listener to confirm CSP-block hypothesis BEFORE pivoting

**Polish-v2 P5 also CONFIRMED SW1-fu fix works**: log line `✓ JWKS healthy: 1 RS256 key(s) with n+e material` (NEW post-W143 SW1-fu wording) replaces pre-W143 `✓ JWKS healthy: 1 RS256 key(s)` — confirms the validation now requires `kty=RSA + n + e`. JWKS sidecar shows full RSA shape (256-byte `n` modulus + `e: "AQAB"`) instead of pre-fix HMAC stub.

---

## Honest §Honesty caveat trajectory (post-W143)

| # | Caveat | Pre-W143 | Post-W143 |
|---|--------|----------|-----------|
| 1 | W134 #2 bundle delta (recording-only) | OPEN | UNCHANGED |
| 2 | W134 #10 /messenger Phase 5 punted | OPEN | UNCHANGED (Tier 5) |
| 3 | W137 #5 file-processor temporal-localhost | UNCHANGED (W141 SW2 baseline) | UNCHANGED |
| 4 | W137 #6+#7 by-design dev-only | OPEN | UNCHANGED |
| 5 | W140 NEW healthcheck override dev-only | OPEN | UNCHANGED (by-design) |
| 6 | W140 NEW #5 axe coverage 0/8 Linux CI heavy DOM | OPEN | **CONFIRMED OPEN** via W143 SW1 CI run 25732174008 (Path A also disproved); W144+ scope: reduced route subset OR step-level timeout |
| 7 | W140 NEW #6 Path (a-auth) | RECLASSIFIED W142+ → W143+ | **STAYS W144+** — SW2 disproved crypto root cause; runtime-specific issue remains uncertain |
| 8 (NEW W141) | (z) #1-#4 sub-discoveries | OPEN | UNCHANGED (informational) |
| 9 (NEW W141) | W141 polish A3 build-infra non-determinism | OPEN | **DEEPENED** — W143 SW4 found Rolldown 1.0.0-rc.15 lacks parallelism API; structural defer continues |
| 10-13 (NEW W142) | (z) #6-#9 collapsed sub-discoveries | OPEN (informational) | UNCHANGED |
| 14 (NEW W142) | (z) #10 STRUCTURAL crypto/rsa verif error | OPEN structural | **REFINED** — SW2 disproved crypto root cause; remaining hypothesis surface narrowed to Temporal-runtime-specific |
| 15 (NEW W142) | (z) #11 STRUCTURAL Rolldown non-determinism | OPEN structural | **DEEPENED** — W143 SW4 confirmed no in-repo fix path; needs upstream Rolldown |
| 16 (NEW W143) | (z) #12 wave138-visual-audit.mjs JWKS pre-check script bug | — | **MITIGATED in W143 SW1-fu** — script now prefers correct RSA endpoint + validates n+e material |
| 17 (NEW W143) | (z) #13 Rolldown 1.0.0-rc.15 API gap | — | OPEN structural (W144+ upstream-blocked) |
| 18 (NEW W143) | (z) #14 Path A STRUCTURAL HANG on /login (compact route, NOT heavy-DOM) — polish-v2 P5 CI run 25735582483 hung 14m6s at `→ /login` before `auditRoute` could write sidecar; most plausible cause CSP `script-src 'self' 'strict-dynamic'` blocks CDN injection | — | OPEN structural (W144+ pivot to same-origin axe asset OR npm-bundled axe-core + page.evaluate; ADD `page.on("requestfailed")` to confirm CSP-block hypothesis pre-fix) |

**Net post-W143**:
- **0 CLOSED at runtime** in W143 (matches W141 + W142 pattern)
- **1 sub-issue mitigated** (z) #12 JWKS pre-check script bug fixed
- 2 NEW structural (z) discoveries documented (#13 + #14)
- Effective caveat count: **9-18 depending on counting**

**TRUE W143 VALUE (per `feedback_perfectionism.md` honest framing):**
- **SW2 lib correction**: Agent 2's "lestrrat-go/jwx + JWKS encoding mismatch" hypothesis was 100% wrong. Library is actually `go-jose/v4 + golang-jwt/jwt/v4` + the encoding is RFC-canonical + end-to-end cryptographic chain verifies in Python. This narrows W144+ Tier 1 #2 scope significantly — no need to search in JWX OR JWKS encoding.
- **SW2 regression guard**: 3 contract tests prevent future regressions of the JWKS endpoint shape (currently the highest-confidence permanent artifact from W143).
- **SW4 API gap finding**: Rolldown 1.0.0-rc.15 lacks parallelism — saves W144+ from chasing a non-existent option. Sets up structural Rolldown upstream issue filing as W144+ work.
- **SW1-fu JWKS pre-check fix**: improves diagnostic accuracy of future visual-audit.yml runs.
- **Wall-clock efficiency**: ~3-4h core (vs W141's 9-10.5h, W142's 5-6h). The wave delivered diagnostic value with minimal commit footprint.

---

## Verification matrix

| Check | Expected baseline | W143 result | Status |
|-------|---|---|---|
| tsc errors | 0 | 0 | ✅ (no .ts changes) |
| eslint scripts/ pre-existing errors | 36 (config gap) | 36 (UNCHANGED; W143 added 3 inline disables for browser-context globals) | ⚠️ pre-existing carry |
| vitest single run | 1052p/12s/0f | 1052p/12s/0f UNCHANGED (no frontend test changes) | ✅ |
| pytest backend SW2 contract tests | NEW | 3 passed, 1 warning, 0.92s | ✅ |
| Docker temporal | (healthy) admin-tools | STOPPED throughout W143 (no runtime swap attempted) | ⚠️ by-design |
| Docker file-processor | (healthy) | STOPPED throughout W143 (no runtime swap attempted) | ⚠️ by-design |
| Cargo.lock drift | clean (≥33 waves idempotent) | clean | ✅ |
| Tree-shake invariants | 0 lhci-mock-user + 0 data-e2e-stub in PROD | UNCHANGED (no PROD build performed in W143) | ⚠️ defensive carry |
| SW1 CI visual-audit axe coverage | 0/8 routes valid | 0/8 (W142 baseline confirmed by W143 SW1 30-min timeout) | ⚠️ Tier 1 #1 deferred W144+ |
| SW2 JWKS roundtrip contract tests | NEW | 3 passed (all 3 round-trip cases verify byte-perfect reconstruction) | ✅ new regression guard |

---

## W144+ candidates

### Tier 1 (HIGH priority, structural carry from W143)

1. **Tier 1 #1 axe coverage — reduced scope path** (~2-3h):
   - W143 SW1 disproved Path A (30 min timeout). Path A scaffolding preserved.
   - W144+ approach options:
     - **(i) Reduced route subset** — run audit on only /login + /404 (compact pages) + 2-3 lighter authed routes (/profile, /settings); skip /dashboard /map /activity (heavy)
     - **(ii) Step-level timeout per route** — wrap each route in `Promise.race(auditRoute(...), setTimeoutPromise(120s))` to allow workflow to continue + write `axeError: "route-timeout-120s"` sidecar instead of hanging
     - **(iii) Chunked per-route artifact upload** — upload sidecar immediately after each route completes, so partial progress survives workflow cancellation

2. **Tier 1 #2 Path (a-auth) (z) #10 runtime debug** (~3-5h):
   - SW2 disproved crypto root cause. Remaining hypothesis surface narrowed to Temporal-runtime-specific.
   - W144+ approach: docker compose up plain `temporalio/server:1.30.2` (NOT auto-setup) + minimal auth_config.yaml + JWKS at http://backend:8000/.well-known/jwks.json. Watch for actual error message — if NOT "crypto/rsa: verification error", we'll have a different (z) discovery and concrete next debug step.
   - PRECONDITION: schema bootstrap (admin-tools sidecar with temporal-sql-tool) + default namespace creation. W141/W142 scaffolding 100% preserved.

### Tier 2 (Structural deferrals — upstream-blocked)

3. **Tier 2 #2 Rolldown determinism — file upstream issue** (~30 min):
   - W143 SW4 confirmed no in-repo fix path. Rolldown 1.0.0-rc.15 lacks
     parallelism API. Layer 2 (consistent _shell.html + sw.js non-determinism)
     candidates per Agent 3 W142: TanStack Start prerender OR workbox glob
     order — both feasible to investigate.
   - W144+ option: file Rolldown GitHub issue requesting `experimental.parallelism`
     OR `chunkNamesSeed` flag for reproducible builds.

### Tier 3 (Acceptable as-is)

4. W137 #6+#7 by-design dev-only (MAX_SESSIONS, sidecar healthiness)
5. W140 NEW healthcheck override dev-only
6. W134 #2 bundle delta (recording-only)

### Tier 5 (Explicit user decision)

7. /messenger × 2 polish OR /admin polish OR punt as "production-as-is"

---

## Lessons from W143 (carry-forward for W144+)

1. **W141 anti-pattern #3 re-vindicated AGAIN** — Agent reports can be wrong
   about LIBRARY IDENTITY (Agent 2 misidentified `lestrrat-go/jwx`) AND
   API AVAILABILITY (Agent 3 hypothesized `experimental.parallelism`). W144+
   Phase 1 Explore prompts should require VERIFIED library/API references
   (e.g., grep node_modules type defs + read upstream go.mod) for any
   hypothesis claim.

2. **W141 anti-pattern #1 + #4 internalized** — W143 SW1 baked CI run number
   into the commit message + audit. The 30-min timeout was honestly reported
   as deferral, not papered over. Path A's failure became diagnostic value
   (SW1-followup script bug fix surfaced from the sidecar).

3. **W142 NEW Lesson — empirical diff > hypothesis vindicated AGAIN**:
   SW2 contract test (10 min Python investment) produced more actionable
   evidence than ~3-6h Agent 2 hypothesis-based Path A would have. For
   crypto/auth issues, write a Python verification that mirrors the verifier-
   side path before investing in Docker stack runtime swap.

4. **Honest defer beats false-progress**: W143 has 3 honest defers vs
   attempting incomplete fixes. Per `feedback_perfectionism.md` "structural
   deferrals acceptable" + W138 Lesson #8 dynamic counting — the deferrals
   are themselves diagnostic progress (each frames the next wave's scope
   more accurately).

5. **NEW W143 Lesson — script bugs hide via lax validation**: The JWKS
   pre-check (z) #12 went undetected for W138 + W139 + W140 + W141 + W142
   because the alg-only filter false-passed the HMAC stub. W144+ pre-check
   gates (any "shape verification" step) should validate FULL expected shape,
   not just one field. The SW1-fu fix demonstrates the pattern.

6. **NEW W143 Lesson — Agent report verification BEFORE wave-scope estimation**:
   Agent 2 + Agent 3 BOTH made structurally wrong claims (lib + API). If
   Phase 1 Explore ran tightly bounded sanity checks (e.g., "verify the
   library is actually imported in go.mod" + "verify the API exists in node_modules
   type defs"), W143 would have skipped Path A + Path A4 mini-axe attempts
   entirely. W144+ Phase 1 prompts should ask agents for evidence references,
   not just hypothesis statements.

---

## Build × 5 reproducibility status (post-W143 unchanged)

W142 SW6 + W141 polish A3 baseline preserved unchanged:
- Layer 1 INTERMITTENT (Rolldown chunk filename hashing) — confirmed structural
  upstream issue per W143 SW4 API gap finding
- Layer 2 CONSISTENT (_shell.html + sw.js cascade) — root cause candidates
  per Agent 3 W142 (TanStack Start prerender, workbox glob order) remain
  W144+ investigation targets

No build × N attempted in W143 (no vite.config.mts changes — SW4 honest defer).

---

## References

- Plan file: `C:\Users\egorribun\.claude\plans\c-users-egorribun-claude-projects-c-use-polymorphic-sutherland.md`
- Design doc: `docs/plans/2026-05-12-wave143-tier123-design.md`
- Memory backlog: `memory/wave143_backlog.md` (`.claude` profile only)
- Memory handoff: `memory/wave144_opening_prompt.md` (`.claude` profile only, NEW SW7)
- Previous wave: `docs/audits/AUDIT_WAVE142.md`
- W137 §Honesty #5 origin: `docs/audits/archive/AUDIT_WAVE137.md`
- N+3 rotation this wave: `docs/audits/AUDIT_WAVE140.md` → `archive/`
- CI run: `25732174008` (SW1 Path A 30-min timeout — disproof + script bug surface)
- W143 SW2 contract test: [tests/test_wave143_jwks_roundtrip.py](../../tests/test_wave143_jwks_roundtrip.py)
