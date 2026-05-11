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
   **Rolldown/Vite chunk filename hashing is NON-DETERMINISTIC**. Two clean
   `npm run build` runs produce `dist/client/assets/index-DqqHVXgy.js`
   (build1) vs `dist/client/assets/index-CQ-5oXj0.js` (build2) — same SIZE
   (139,808 bytes) but DIFFERENT FILENAME HASH AND DIFFERENT CONTENT. Cascades
   through `_shell.html`'s `<script src="/assets/index-*.js">` ref (36 byte
   diff offset 1583), `sw.js` precache manifest revision hash (302 byte diff
   offset 31480), and `server.js` TanStack Start manifest ref (16 byte diff
   offset 8155). Adding post-process manifest sort would NOT fix this. SW6
   ships a diagnostic comment block in `build-orchestrated.mjs` documenting
   the finding. W143+ structural fix scope ~5-9h.

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

### (z) #11 W142 NEW — Rolldown chunk filename hash non-determinism (DEEPER than Agent 3 hypothesis)

Empirical `npm run build` × 2 produces:
- `dist/client/assets/index-DqqHVXgy.js` (build1, 139,808 bytes)
- `dist/client/assets/index-CQ-5oXj0.js` (build2, 139,808 bytes)

Same SIZE, DIFFERENT FILENAME HASH AND DIFFERENT CONTENT (sha256 mismatch).
Other route chunks (Dashboard-*, dashboard-*) similarly differ. Cascade
through references:
- `_shell.html` main JS script src ref (36 byte diff offset 1583)
- `sw.js` precache manifest revision for `_shell.html` (302 byte diff offset
  31480) — because _shell.html content changed upstream
- `server.js` TanStack Start manifest ref (16 byte diff offset 8155)

Agent 3 Phase 1 hypothesis was workbox-build manifest order; W142 SW6 diff
DISPROVED this. Real source is in Rolldown's chunking layer:
- Parallel module processing order (Rolldown uses Rust threading)
- Module dependency graph traversal order (filesystem-dependent)
- Intermediate hash inputs (timestamps, mtimes, parallel ID assignment)

**NOT mitigated** — `build-orchestrated.mjs` ships a diagnostic comment
block documenting the finding + W143+ scope (~2-4h diagnosis + ~3-5h fix).
This IS honest progress vs W141 polish A3 ("source not yet identified" →
now "Rolldown chunk filename hash non-determinism, propagates via _shell.html
main-JS ref + sw.js precache revision + server.js manifest ref").

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

**Updated baseline (W142)**:
```
dist/client/assets/index-DqqHVXgy.js   139,808 bytes (build1)  sha256 differs
dist/client/assets/index-CQ-5oXj0.js   139,808 bytes (build2)  per build
dist/client/_shell.html                 65,864 bytes  sha256 differs (36 byte cascade)
dist/client/sw.js                       53,115 bytes  sha256 differs (302 byte cascade)
dist/server/server.js                   39,373 bytes  sha256 differs (16 byte cascade)
```

W143+ Tier 2 #2 candidate fixes this structurally.

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
