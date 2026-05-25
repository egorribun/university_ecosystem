# AUDIT_WAVE153.md — /login wedge investigation (SW1+SW2 ship, SW3 mandatory defer)

**Date**: 2026-05-14
**Branch**: `egorribun`
**Author**: W153 SW4 audit
**Wave duration**: ~4-5h core wall-clock + Docker rebuild cycles (~30-60 min) — within plan estimate (2-4h core + 30-60 min polish)

---

## Headline

W153 set out to identify the W150-polish-followup-v2 + W152 unresolved user-facing /login blank screen via Tier 1(c) NODE_ENV=development Docker patch (SW1, infrastructure) followed by Tier 1(a) WebSocketProvider-first component-strip (SW2 component-strip, STRICT 3-iter cap). The wave delivered **two real fixes** + **9 commits on `egorribun`** but **did NOT resolve the user-facing wedge** — the underlying V8 wedge persists after 3 component-strip iterations ruled out 6 providers.

**Outcomes by commit**:
1. `568c51258` SW1 initial NODE_ENV=dev plumbing → empirically broke SSR with `TypeError: jsxDEV is not a function` at `RootShell` (mode=development emitted dev JSX runtime calls into a server bundle loaded by production react-dom)
2. `e563e992d` SW1 fixup → kept `mode=production` while still disabling minify + enabling source maps via NEW `FRONTEND_BUILD_UNMINIFIED` env flag. /login HTTP 200 restored; bundle unminified at 341 KB / 10,910 lines + linked `.map` sidecar at 648 KB; user real-Chrome test confirmed DevTools opens + React error #418 (hydration mismatch) visible in console.
3. `d931492e3` SW2 React #418 fix → `router.ts:78 defaultPendingComponent` SSR-aware via `import.meta.env.SSR` literal. Server emits empty `<div id="root"><!--$-->…<!--/$--></div>` instead of the W152 Phase 1.5 `<div role="status">Loading…</div>` fallback. main.tsx's `hasRealSsrContent` ELEMENT_NODE detection correctly takes `createRoot()` SPA path instead of `hydrateRoot()`. **REAL bug fix**; server-side empirically verified via curl + grep (Loading… absent from HTML).
4. `6b3737da7` SW3 iter 1 — WebSocketProvider stub strip → user real-Chrome: /login STILL blank, **wedge NOT in WebSocketProvider**.
5. `25aefefc3` SW3 iter 2 — AuthProvider stub overlaid → user real-Chrome: /login STILL blank, **wedge NOT in AuthProvider**.
6. `d04d96b33` SW3 iter 3 (LAST allowed per STRICT 3-iter cap) — max-strip ProvidersInner middle layer (LiveRegionProvider + AppShellProvider + MessengerProvider + GlobalHapticsListener) → user real-Chrome: /login STILL blank, **wedge upstream of ProvidersInner**.
7. `05ce98220` SW3 revert → restored AppProviders.tsx + useChatWebSocket.ts to clean SW2 state. All 3 wip iter commits stay in history as diagnostic documentation.

**SW1 + SW1 fixup + SW2 ship as merge-candidate W153 deliverables**. SW3 iter commits stay on `egorribun` as documentation (per plan commit discipline: diagnostic strips never merge to main; this branch reverts to clean state).

**Per W141 anti-pattern #1 STRICT 3-iter cap (NONUPLE-vindicated W138+W141+W143+W144+W145+W147+W148+W149+W152 — W153 = 10th vindication)**: MANDATORY honest defer to W154+. No iter 4.

---

## Scope (user-approved Q1+Q2+Q3, opening prompt structure)

- **Q0** (real-Chrome state): "Still blank — Chrome + Incognito" — W152 baseline reproduces.
- **Q0.5** (alternative browser test): "All blank / haven't tested yet" — no narrowing available; SW1 becomes more important as it makes Chrome itself debuggable.
- **Q1** (primary tier): "Tier 1(c) NODE_ENV=dev patch FIRST + Tier 1(a) strip SW2 (Recommended)" — opening prompt's recommended path.
- **Q2** (first strip target): "WebSocketProvider (Recommended)" — sync-init-most-likely candidate per Phase 1 Agent 2 verified analysis.
- **Q3** (iter ceiling): "STRICT 3-iter cap on SW1 (Recommended)" — corrects W152's iter-5 anti-pattern violation.

---

## SW1 — NODE_ENV=development infrastructure (initial + fixup)

### SW1 initial (`568c51258`, 4 files +43/-7)

Goal: produce unminified bundle + linked source maps so React errors become debuggable in real Chrome DevTools.

Mechanism (per Phase 1 Agent 1 verified findings):
- `frontend/vite.config.mts:447`: `minify: true` → `minify: mode === "production"` (mode-conditional)
- `frontend/scripts/build-orchestrated.mjs:148-165` + 338-357: env propagation: `--mode development` arg to vite subprocess + `NODE_ENV=development` env + mode-gated esbuild sw.ts block (minify off + sourcemap inline + import.meta.env.{DEV,PROD,MODE} flipped)
- `frontend.Dockerfile:33-38`: NEW `ARG FRONTEND_BUILD_MODE="" + ENV propagation`
- `docker-compose.full.yml:131-135`: NEW `FRONTEND_BUILD_MODE: "development"` dev build arg

Local gates: tsc 0, eslint 0, prettier clean (post --write of build-orchestrated.mjs to fix wrapped line — W150 polish-v1 anti-pattern #15 caught locally).

Verification post-deployment:
- Bundle: `index-mYw5SnpE.js` **405,375 bytes** (vs W152 baseline 176,670 = 2.3× larger, confirming unminified)
- `.map` sidecar: 733,142 bytes ✓
- `//# sourceMappingURL=index-mYw5SnpE.js.map` trailer present ✓
- 12,380 lines of readable JS with `__vite__mapDeps`/`setupServiceWorker`/`//#endregion` preserved ✓
- Container healthy in 9s ✓

**BUT**: user real-Chrome test surfaced HTTP 500 on /login. Frontend Node SSR logs:

```
TypeError: jsxDEV is not a function
    at RootShell (file:///app/dist/server/assets/router-DamhYhDU.js:7189:68)
    at renderWithHooks (/app/node_modules/react-dom/cjs/react-dom-server.node.production.js:4647:18)
    ...
```

**Diagnosis**: setting `mode: development` + `NODE_ENV: development` at build time caused the JSX transform (via @vitejs/plugin-react oxc plugin) to emit `jsxDEV()` calls in BOTH client AND server bundles. At runtime, Node loads `react-dom-server.node.production.js` (because Dockerfile:155 bakes `ENV NODE_ENV=production` in the runtime stage — INDEPENDENT of build-time NODE_ENV). Production react-dom-server doesn't export `jsxDEV` (dev-only API). → TypeError → HTTP 500 → /login unreachable.

This was exactly the W152 Lesson #3 dev/prod divergence playing out at the JSX transform layer. SW1 plan's R5 ("§Honesty trajectory worsens if SW1 reveals stacked issues") + R10 ("Diff 2 vite subprocess --mode development interaction with BUILD_SKIP_PWA") undersold this — the actual interaction was JSX transform vs runtime react-dom resolution.

### SW1 fixup (`e563e992d`, 4 files +68/-39)

Goal: preserve SW1's debuggable-bundle goal while eliminating the SSR breakage.

Mechanism: keep `mode: production` for the build (so JSX transform stays at production runtime, emitting `jsx()` calls that the production react-dom-server CAN load); narrow the env var semantic to `FRONTEND_BUILD_UNMINIFIED=true` controlling ONLY `build.minify` + `build.sourcemap` via a separate flag (NOT via mode).

- `frontend/vite.config.mts`: NEW `const isUnminified = env.FRONTEND_BUILD_UNMINIFIED === "true" || process.env.FRONTEND_BUILD_UNMINIFIED === "true"` near other config-locals (line ~217). `build.minify: isUnminified ? false : mode === "production"` + `build.sourcemap: isUnminified ? true : (mode === "production" ? "hidden" : true)`. mode-conditional gates preserved for CI / prod compose unchanged.
- `frontend/scripts/build-orchestrated.mjs`: removed `--mode development` arg + `NODE_ENV: development` env propagation. NEW `const isUnminified = process.env.FRONTEND_BUILD_UNMINIFIED === "true"` propagates via env to vite subprocess. esbuild sw.ts block: `minify: !swIsUnminified + sourcemap: swIsUnminified ? "inline" : false` + import.meta.env.* defines KEPT at production values (sw.ts production-mode runtime is fine even when unminified).
- `frontend.Dockerfile`: renamed `ARG FRONTEND_BUILD_MODE` → `FRONTEND_BUILD_UNMINIFIED` with expanded comment block documenting initial-SW1 jsxDEV failure mode.
- `docker-compose.full.yml`: renamed build arg to `FRONTEND_BUILD_UNMINIFIED: "true"`.

Tradeoff acknowledged in commit: lose React DEV runtime warnings (errors stay as `Minified React error #X` codes, lookup-able via reactjs.org/docs/error-decoder). Retain unminified bundle (readable JS variable names + comment regions preserved) + linked source maps (stack traces resolve to real `frontend/src/...tsx:line:col`).

Verification post-fixup deployment:
- /login HTTP **200** / 11,189 bytes (matches pre-W153 production exactly — byte-for-byte content delivery preserved while build is now unminified)
- Bundle: `index-C-be2fJW.js` 341,887 bytes / 10,910 lines (down from SW1-initial 405 KB / 12,380 lines because production runtime is smaller than dev runtime + console.log strip via oxc.define still active at mode=production)
- `.map` sidecar: 648,245 bytes ✓
- `//# sourceMappingURL` trailer present ✓
- **Server bundle: 0 `jsxDEV` references** (verified via `grep -c "jsxDEV" /app/dist/server/assets/*.js` = all 0) — SSR transform correctly emits `jsx()` only
- Container healthy in 15s ✓

User real-Chrome test on /login: **DevTools opens** (first time since W152). Console shows:
- `[GlobalErrors] Unhandled error event Error: Minified React error #418`
- `Uncaught Error: Minified React error #418 at throwOnHydrationMismatch (react-dom-client.production.js:2736:15)`
- workbox SW logs ("Router is responding to: /favicon.ico" etc.)
- `GET http://localhost:8081/api/v1/users/me 500` (routing artifact — user was on :8081 which bypasses Caddy /api proxy; this 500 is NOT a backend bug)
- `Failed to fetch current user`

React error #418: hydration mismatch. Reference: https://react.dev/errors/418

**This was the load-bearing outcome of SW1**: from "DevTools won't open + W152 §Honesty #19 V8-wedge UNIDENTIFIED" to "DevTools opens + named React error visible". The diagnostic infrastructure SW1 ships **permanently improves debuggability** for any future wedge investigation.

---

## SW2 — React #418 fix via SSR-null defaultPendingComponent (`d931492e3`, 1 file +40/-29)

### Root cause analysis (named with file:line citations)

Investigated server response body via `curl /login | grep -aoE 'id="root"[^<]*<[^>]*(<[^>]*>){0,8}'`:

```html
<div id="root"><!--$--><div style="min-height:100dvh;display:flex;align-items:center;justify-content:center;background:var(--bg-page, var(--initial-bg, #060b14));color:var(--text-primary, #f8fafc);font-family:system-ui, -apple-system, sans-serif;font-size:0.9rem;opacity:0.7" role="status" aria-live="polite"><span>Loading…</span></div>...
```

**Chain**:
1. `router.ts:78-97` (W152 Phase 1.5): `defaultPendingComponent` creates a `<div role="status">Loading…</div>` for ANY suspending route.
2. With `__root.tsx:148 ssr: false` (W150-polish-followup state), the server still runs the React SSR pipeline; route loaders are deferred but the Suspense boundary itself renders the fallback.
3. Server emits `<div id="root"><!--$--><div ...>Loading…</div><!--/$-->` — Suspense markers PLUS the visible fallback as an ELEMENT_NODE.
4. `main.tsx:121-127` `hasRealSsrContent` detection scans for ELEMENT_NODE children of `#root`. It finds the Loading… `<div>` and takes the `hydrateRoot()` branch (designed for ssr:true cases).
5. Client renders the actual `<App />` tree (which is the Login form, not Loading…). React tries to match client tree against server tree → mismatch on first element → React #418.

Pre-W152 Phase 1.5, the fallback was implicitly `null` → server emitted only `<!--$--><!--/$-->` markers → main.tsx took createRoot path. W152 Phase 1.5 added the visible UI to fight indefinite-suspension blank screens (defense-in-depth) — good intent, but inadvertently broke the W128/W149 hydration-detection heuristic for ssr:false routes.

W152 §Honesty #24 had captured this risk: "Phase 1.5 `defaultPendingComponent` fallback never observed... wedge-before-React-render vs wedge-with-no-paint, indistinguishable without working DevTools." With W153 SW1's debuggable build, the fallback DOES render server-side, and that SSR'd DOM IS what trips the hydration mismatch.

### Fix

Make `defaultPendingComponent` SSR-aware via `import.meta.env.SSR` (Vite literal substitution: `true` in server bundle, `false` in client bundle):

```ts
defaultPendingComponent: () =>
  import.meta.env.SSR
    ? null
    : createElement("div", {style:..., role:"status", "aria-live":"polite"},
                    createElement("span", null, "Loading…"))
```

DCE in production:
- Server bundle: `true ? null : createElement(...)` → eliminated to just `null` → Suspense fallback returns null → server emits only `<!--$--><!--/$-->` markers in `<div id="root">`
- Client bundle: `false ? null : createElement(...)` → eliminated to `createElement(...)` → user gets visible Loading… UX for in-flight route transitions post-hydration

### Verification (server-side)

| Check | Pre-SW2 | Post-SW2 ✅ |
|---|---|---|
| /login HTTP | 200 / 11,189 b | **200 / 10,874 b** (-315 b = removed Loading… DOM) |
| `#root` contents | `<!--$--><div role="status">Loading……` | **`<!--$--`** (only Suspense markers) |
| `Loading…` in HTML | present | **absent** ✓ |
| Server logs | clean | **clean (no jsxDEV, no errors)** ✓ |

315-byte shell delta exactly matches the removed `<div style="..." role="status" aria-live="polite"><span>Loading…</span></div>` DOM (confirms `import.meta.env.SSR` literal substitution worked: server bundle takes the `null` branch).

User real-Chrome test post-SW2: /login STILL blank + DevTools won't open (regression to W152 baseline behavior). **SW2 closed a real bug** (React #418 hydration mismatch was being thrown) but the user-facing blank-screen persists.

### Diagnostic interpretation (post-SW2 surprise)

The W152 hypothesis was: "V8 wedge so severe it prevents DevTools attach." SW1 fixup with unminified bundle proved DevTools CAN open. Then SW2 closed React #418, expecting /login to render. Instead: /login still blank AND DevTools won't open again.

Interpretation: **React #418 was an EFFECT, not the cause**. The React error was throwing late in the render cycle, which interrupted the underlying sync wedge and gave DevTools a window to attach. With SW2's fix removing the error, the underlying wedge runs to completion uninterrupted → DevTools can't attach again. This matches W152 §Honesty #19 "V8-wedge cause UNIDENTIFIED" framing — fixing the SYMPTOM doesn't fix the underlying wedge.

**Cheap diagnostic before SW3**: user tested Incognito (`Ctrl+Shift+N`). Result: /login also blank + DevTools won't open in Incognito too. Confirms:
- Service Worker caching is NOT the cause (Incognito has fresh SW state)
- React #418 was an artifact/effect, not root cause
- W152 §Honesty #19 V8-wedge persists post-SW2

### W153 SW2 deliverables (real merge-candidate value)

Despite not fixing the user-facing wedge, SW2 is a real bug fix:
- React #418 hydration mismatch on ssr:false routes is genuinely closed
- W128/W149 SSR architecture's `hasRealSsrContent` detection now works correctly with W152 Phase 1.5's visible fallback (SSR-suppressed; client-only feedback retained)
- Pattern recipe documented in CLAUDE.md (W153 SW2 closes a real bug on the SSR-empty-shell route variant)

---

## SW3 — Component-strip cascade (STRICT 3-iter cap, all 3 FAILED)

Original W153 plan said SW2 = component-strip; W153 renumbered to SW3 because SW2 became the React #418 targeted fix (per outcome of SW1 plan branch (a) "DevTools opens + visible React/JS error → Skip SW2 strip; create W153 SW3 targeted fix"). The original SW2 plan's strip strategy was preserved as SW3.

### SW3 iter 1 — WebSocketProvider stub strip (`6b3737da7`, 2 files +33/-4, wip prefix)

Diff:
- `frontend/src/hooks/useChatWebSocket.ts:91`: added `export` to `class WebSocketStore` (1-char prereq for stub instantiation)
- `frontend/src/AppProviders.tsx`: dropped `WebSocketProvider` import + added `WebSocketStoreContext, WebSocketStore`; module-level singleton `W153_NO_OP_WS_STORE = new WebSocketStore()` (matches real `useMemo(() => new WebSocketStore(), [])` stable-identity contract); replaced `<WebSocketProvider>` JSX with `<WebSocketStoreContext.Provider value={W153_NO_OP_WS_STORE}>` stub.

Phase 1 Agent 2 had verified: stub preserves `useContext(WebSocketStoreContext)` shape so `MessengerContext.tsx:31` `useChatWebSocket({enabled: isAuth})` doesn't throw "must be used within WebSocketProvider". WebSocketStore's constructor + getSnapshot have no observable side effects on /login.

Hypothesis: opening prompt's W153 plan placed WebSocketProvider as most likely sync-side-effect candidate — `useMemo(new WebSocketStore())` + `useSyncExternalStore` subscription during render.

**User test result**: /login STILL BLANK. Wedge is NOT in WebSocketProvider.

### SW3 iter 2 — AuthProvider stub overlay (`25aefefc3`, 1 file +34/-3, wip prefix)

Overlay on top of iter 1 stub. Both strips simultaneously active.

Diff:
- `frontend/src/AppProviders.tsx`: dropped `AuthProvider` import + added `AuthContext` + `resetEtagCache` from `@/api/client`; module-level `W153_NO_OP_AUTH` value mirrors the existing default at AuthContext.tsx:33-43 (no-op login/logout/setUser/refresh/etc. + `authOperation: false` + `resetEtagCache`); replaced `<AuthProvider>` JSX with `<AuthContext.Provider value={W153_NO_OP_AUTH}>`.

Hypothesis: opening prompt's W153 plan placed AuthProvider 2nd — `useProfileSync` auto-fetch + `queryClient.fetchQuery` (W134 SW1 Bridge) + localStorage cache hydration. Any of these could trigger sync wedge during mount.

Cheap diagnostic before iter 2: `curl /api/v1/users/me` via Caddy returned clean 401 (correct unauth behavior). Backend healthy. The earlier /users/me 500 in the SW1 fixup screenshot was a routing artifact (user tested :8081 direct, no /api proxy). The /users/me wasn't the wedge cause.

**User test result**: /login STILL BLANK. Wedge is NOT in AuthProvider.

### SW3 iter 3 — Max-strip ProvidersInner (LAST allowed iter, `d04d96b33`, 1 file +36/-27, wip prefix)

Adapted from original plan iter 3 ("MainLayout strip via __root.tsx:321") because /login is `_public` routed and doesn't load MainLayout (per Phase 1 Agent 2 finding: messenger tree never loaded, MainLayout never mounted on /login).

Max-strip target list:
- `LiveRegionProvider` (a11y announcer) — STRIPPED
- `AppShellProvider` (theme/layout context) — STRIPPED
- `MessengerProvider` (messenger context) — STRIPPED
- `GlobalHapticsListener` (touch haptics) — STRIPPED

Preserved (load-bearing for Login's render):
- Outer `LanguageProvider` (Login uses `useTranslation`)
- Outer `LazyMotion` + `MotionConfig` (Login uses framer-motion `<m.X>`)
- `AuthContext.Provider` stub + `W153_NO_OP_AUTH` (preserves `useAuth` shape)
- `WebSocketStoreContext.Provider` stub + `W153_NO_OP_WS_STORE` (preserves `useChatWebSocket` context shape)
- `ErrorBoundary` (safety net for any throw downstream)
- `__root.tsx`-level wrappers untouched (PersistQueryClientProvider, ThemeProvider — outside AppProviders scope)

ProvidersInner after iter 3:
```tsx
return (
  <AuthContext.Provider value={W153_NO_OP_AUTH}>
    <WebSocketStoreContext.Provider value={W153_NO_OP_WS_STORE}>
      <ErrorBoundary>{children}</ErrorBoundary>
    </WebSocketStoreContext.Provider>
  </AuthContext.Provider>
)
```

**User test result**: /login STILL BLANK. Wedge is upstream of ProvidersInner.

### SW3 cumulative result (6 providers ruled out)

| Provider | Iter | Result |
|---|---|---|
| WebSocketProvider | 1 | Not the wedge |
| AuthProvider / useProfileSync | 2 | Not the wedge |
| LiveRegionProvider | 3 | Not the wedge |
| AppShellProvider | 3 | Not the wedge |
| MessengerProvider | 3 | Not the wedge |
| GlobalHapticsListener | 3 | Not the wedge |

**Remaining suspects** (W154+ scope):
- LanguageProvider (i18n init via react-i18next: `useState(getInitialLanguage())` localStorage read, `useEffect(i18n.changeLanguage)`, context provision)
- LazyMotion / MotionConfig (framer-motion: animation provider; `strict` mode with `domAnimation` feature set)
- `__root.tsx`-level providers:
  - PersistQueryClientProvider (W152 Phase 1.8 IDB-strip was NEGATIVE result — already disproved; W153 SW3 didn't re-test per opening prompt anti-redo discipline)
  - ThemeProvider (reads localStorage for theme preference, sets `.dark` class on `<html>`)
- App.tsx `<StartClient />` (tanstackStart `hydrateStart()` internals → `<Await>` → `<RouterProvider>`)
- main.tsx `createRoot()` / `hydrateRoot()` detection logic + bootstrap path
- Module-init JS (W125 Phase 2 tanstackStart() plugin runtime, `queryClient` instantiation at @/app/queryClient, `idbPersister` setup, MEM/window init)

### SW3 revert (`05ce98220`, 2 files +22/-91)

Per plan SW2 commit discipline ("SW2 iter commits stay on `egorribun` and are NEVER merged to main"), AND `feedback_perfectionism.md` "honest framing":

- `git checkout d931492e3 -- frontend/src/AppProviders.tsx frontend/src/hooks/useChatWebSocket.ts` restores both files to clean post-SW2 state.
- All 3 wip iter commits (`6b3737da7`, `25aefefc3`, `d04d96b33`) stay in git history as diagnostic documentation. Their effects are undone by the revert commit.
- Bundle hash `index-C-be2fJW.js` post-revert build IDENTICAL to SW2's `index-C-be2fJW.js` (content-addressed hashing — same source produces same bundle).

---

## STRICT 3-iter cap discipline + mandatory defer

Per W141 anti-pattern #1 + opening prompt's STRICT 3-iter cap declaration:
- iter 1 (SW1 NODE_ENV diagnostic + fixup): infrastructure, broke SSR but fixup restored. 1 effective mechanism iter.
- iter 2 (SW2 React #418 fix): targeted fix based on SW1 evidence. Closed real bug, didn't fix user-facing.
- iter 3 (SW3 component-strip cascade, 3 sub-iters): 3 strip iterations under the cap, all failed.
- **MANDATORY DEFER at iter 4+**: no more component-strip attempts.

W141 anti-pattern #1 NONUPLE-vindicated W138+W141+W143+W144+W145+W147+W148+W149+W152 → **W153 = 10th vindication**.

Available W154+ diagnostic paths:
- **Tier 1(b) git bisect** (W125 Phase 2 tanstackStart adoption → HEAD, ~30+ candidate commits, ~6-8 bisect steps × ~10 min/step ≈ ~1h with Docker rebuild + manual /login check per step)
- **Tier 1(d) Linux cross-OS test** (rule out Windows + WSL2 + Docker Desktop virtualized FS layer; if Linux renders /login fine, wedge is platform-specific OS/runtime issue like the W132 vite-plugin-pwa Windows hang)
- **(Cheap pre-W154 diagnostic, ~30 seconds)**: user tests /404 or / on the current SW2-state build. If /404 renders, wedge is /login-specific (narrows W154+ heavily). If /404 also blanks, app-wide module-init wedge → git bisect is the answer. Filed as W154+ first step.

---

## Verification matrix

| SW | Component | Build hash | Verify command | Result |
|---|---|---|---|---|
| SW1 initial | NODE_ENV=dev | `index-mYw5SnpE.js` 405,375 b | `head -c 400 dist/client/assets/index-*.js` + sourceMappingURL trailer | ✅ unminified + .map (but ❌ SSR 500) |
| SW1 fixup | mode=production + unminify | `index-C-be2fJW.js` 341,887 b | curl /login=200/11,189b + `grep -c "jsxDEV" dist/server/assets/*.js = 0` | ✅ SSR restored + unminified + .map |
| SW2 | React #418 SSR-null | `index-C-be2fJW.js` (same content hash because runtime fix only) | curl /login=200/10,874b + `grep -aq "Loading…" /tmp/login.html` → absent | ✅ React #418 server-side cause removed |
| SW3 iter 1 | WebSocketProvider stub | `index-P851VZRR.js` 405 KB | user real-Chrome /login | ❌ still blank |
| SW3 iter 2 | + AuthProvider stub | `index-DimMwhUh.js` | user real-Chrome /login | ❌ still blank |
| SW3 iter 3 | + max-strip ProvidersInner | `index-BEoKGexe.js` | user real-Chrome /login | ❌ still blank |
| SW3 revert | clean SW2 | `index-C-be2fJW.js` | curl + bundle hash | ✅ clean (content-hash identical to SW2) |

All local gates green throughout: tsc 0, eslint 0 (max-warnings=0), prettier clean. routeTree.gen.ts no drift (no route definition changes). Container `(healthy)` in 8-15s on every redeploy.

---

## §Honesty probe (post-W153 caveats trajectory)

### Pre-W153 baseline (W152 close): 21-25 OPEN

Per W152 opening prompt §Honesty caveats inherited:
- 6 pre-W150 carry-forward
- 15 W150 polish-followup-v2 carry-forward (incl. #14 SSR root cause unidentified, #19 V8-wedge cause unidentified, #16 SW NetworkFirst /users/me framing refined, #20 user-side verification incomplete)
- 4 NEW W152-introduced (#22 dev-only Phase 0 finding, #23 diagnostic tooling failure, #24 Phase 1.5 fallback observability, #25 Phase 1.8 IDB-strip NEGATIVE result)

### W153 closures (real)

**Closed via SW1 + SW1 fixup**:
- **#23 (diagnostic tooling failure)** — CLOSED via SW1 fixup. `FRONTEND_BUILD_UNMINIFIED=true` ships permanent diagnostic infrastructure. Real Chrome DevTools opens on the unminified bundle (verified by user). Source maps resolve stack traces to `frontend/src/...tsx:line:col`.

**Closed via SW2**:
- **#24 (Phase 1.5 fallback observability)** — CLOSED. SW2 root-caused the W152 Phase 1.5 `defaultPendingComponent` interaction with `hasRealSsrContent` detection in main.tsx. The fallback DOES render server-side; the SSR'd Loading… `<div>` was tripping the hydration path. Now SSR-suppressed via `import.meta.env.SSR` literal.

**Partial closure / honest framing**:
- **#22 (dev-only Phase 0 finding promoted to prod)** — W152 Phase 0 npm run dev surfaced a hydration mismatch in dev mode that didn't reproduce in production. SW1 fixup unblocked user real-Chrome DevTools → confirmed React #418 hydration mismatch DOES happen in production too (post-W150-polish-followup ssr:false config). SW2 closed the production-mode #418. So Phase 0 finding WAS productive — it pointed at hydration mismatch as a real class of bugs, and W153 SW2 closed the specific instance. **Closeable in framing**, but the original W152 Phase 0 narrative was specifically about a different code path (npm run dev SSR via tanstackStart's dev mode). Documentation update warranted.

**NOT closed (user-facing scope persists)**:
- **#14 (SSR root cause for /login blank)** — STAYS OPEN. SW3 iter 1+2+3 ruled out 6 providers but didn't identify the wedge. User-facing /login still blank.
- **#19 (V8-wedge cause UNIDENTIFIED)** — STAYS OPEN. React #418 was an artifact/effect, not the underlying V8 wedge. Iter 1+2+3 ruled out 6 providers as the wedge source. Wedge is upstream of ProvidersInner.
- **#20 (user-side verification incomplete with rendered /login)** — STAYS OPEN. User real-Chrome continues to show blank /login.

### NEW W153 honest caveats

1. **W153 §Honesty NEW #1**: SW1 initial commit (`568c51258`) introduced an SSR regression via `mode: development` propagation. The regression was caught at SW1 verification step and immediately addressed by SW1 fixup (`e563e992d`), but the initial commit stays in git history. Honest framing per `feedback_perfectionism.md`.
2. **W153 §Honesty NEW #2**: SW2's React #418 fix closes a real bug but is NOT the user-facing blank-screen blocker. Per W141 anti-pattern #4 ("don't claim closure pre-implementation") + opening prompt's "NEVER commit 'Closes §Honesty #X' before user real-Chrome + Incognito confirms /login renders": SW2's commit message does NOT claim user-facing closure.
3. **W153 §Honesty NEW #3**: SW3 STRICT 3-iter cap reached without isolating the wedge. Wedge is upstream of ProvidersInner. W154+ requires git bisect or Linux cross-OS test.
4. **W153 §Honesty NEW #4**: 6 providers ruled out via SW3 iter 1+2+3 strips. The remaining suspect surface (LanguageProvider / LazyMotion / MotionConfig / __root.tsx-level / App.tsx StartClient / main.tsx createRoot / module-init) is significantly narrower than the W152 entry-point suspect list — diagnostic narrowing achieved without root-cause closure.

### Realistic post-W153 §Honesty estimate

Pre-W153: 21-25 OPEN. Post-W153:
- Closures: #23 + #24 + partial #22 = 2-3 closed
- New: NEW #1+#2+#3+#4 = 4 new caveats
- Net: **22-26 OPEN post-W153**

Trajectory direction: **net slightly UP** (more new caveats than closures). The plan's "worst case (SW1 outcome (b) + SW2 all 3 iter fail) → §Honesty 21-25 unchanged" projection was approximately right — slightly worse because the iter cascade surfaced 4 new caveats (W153-specific documentation), but with concrete diagnostic infrastructure win (SW1 + SW2) that's real value.

Per `feedback_perfectionism.md`: HONEST framing over false closure. W153 delivered concrete value (SW1 infrastructure + SW2 #418 fix + scope narrowing) without claiming user-facing closure. The §Honesty count increase reflects honest documentation, NOT regression — W138 Lesson #8 dynamic counting allows trajectory growth before shrinkage when work surfaces real findings.

---

## (z) Path discoveries (W141 anti-pattern #3 vindication)

Per the W139-W145 (z) tracking convention:

- **(z) #1**: SW1 initial mode=development propagation caused JSX transform to emit `jsxDEV()` calls in server bundle. Combined with production-NODE_ENV runtime react-dom resolution → `TypeError: jsxDEV is not a function`. NOT in original SW1 plan's R5 framing (which talked about generic "stacked issues"). The specific JSX transform / react-dom runtime resolution interaction was the actual mechanism. Mitigated by SW1 fixup. Documented in CLAUDE.md gotcha (if not already covered by existing react-dom-server entries).
- **(z) #2**: SW2 fix closes React #418 but underlying V8 wedge persists. The hypothesis that "fixing the named error closes the user-facing issue" was incorrect. The named error was an EFFECT of the wedge, not its cause. Documented in §Honesty NEW #2.
- **(z) #3**: SW3 iter 1+2+3 strip cascade ruled out 6 providers but didn't isolate. Opening prompt's hypothesis ordering (WebSocketProvider FIRST per Q2 recommendation) was structurally invalidated — wedge is upstream of all stripped providers. Documented as W154+ scope refinement.
- **(z) #4**: post-revert bundle hash MATCHES SW2 build (`index-C-be2fJW.js` identical content hash). Vite's content-addressed hashing is deterministic — same source produces same bundle. Useful for verifying clean revert state. NOT a bug, but a useful diagnostic.

**4 NEW (z) discoveries**. Lower than W139's 9, W140's 8 — consistent with W141 anti-pattern #3 working as designed when plan grounding is firm (Phase 1 Explore Agent file:line citations + Phase 3 Review my-own-eyes verification). The strip cascade's failure was honest discovery, not a result of vague hypothesis.

---

## W154+ candidate prioritization

### Tier 1(b) git bisect (~1-2h structural, RECOMMENDED first)

**Approach**: bisect between W125 Phase 2 tanstackStart adoption (the SSR migration kickoff) and HEAD. ~30-40 candidate commits in chronological order:
- W125 Phase 2 tanstackStart adoption
- W126 Phase 3 auth-at-edge
- W127 SW1 provider hoist to __root.tsx (HIGH SUSPICION: hoisted ThemeProvider + AppProviders to __root.tsx RootComponent)
- W128 SW3 per-request QueryClient via SsrRoot subcomponent (HIGH SUSPICION: createRoot-vs-hydrateRoot interaction)
- W134 SW1 useProfileSync Bridge mechanism
- W149 SW2 hydrateRoot adoption (`eae778f9b`)
- W150 polish-followup-v2 ssr:false flip (`a26d1e7da` + `cffc41d6f`)
- W152 Phase 1.5/1.6/1.7/1.8 commits

Process:
```bash
git bisect start
git bisect bad HEAD
git bisect good <pre-W125-commit>  # need to identify a known-working baseline
# bisect runs ~5-7 steps
```

Each step: `git checkout <bisect-sha>` + Docker rebuild + user /login test. ~10 min/step × ~7 steps ≈ ~70 min wall-clock.

Risk: pre-W125 architecture is significantly different (no tanstackStart, simpler routing). The pre-W125 baseline may have other bugs that mask the current bug. Careful baseline identification needed.

### Tier 1(d) Linux cross-OS test (~1-2h infrastructure)

**Approach**: stand up the same Docker stack on Linux. Two outcomes:
- **Linux renders /login fine** → Windows + WSL2 + Docker Desktop platform-specific issue. Similar root-cause class to W132 vite-plugin-pwa Windows hang. Fix is environment-specific.
- **Linux ALSO blanks** → code-level cross-platform wedge confirmed. Tier 1(b) git bisect remains the path.

Setup options:
- Use existing `.github/workflows/visual-audit.yml` (W139 SW1) as starting point — run on Linux CI runner
- OR rent a Linux VM (cheap cloud instance, ~30 min setup)
- OR connect to existing Linux box via SSH

### Tier 1(e) Cheap pre-W154 diagnostic (~30 seconds, RECOMMENDED first action)

User tests /404 or `/` (root) on the current clean SW2-state build:
- /404 renders → wedge is /login-route-specific (narrows W154+ heavily; could be Login.tsx itself or _public.tsx route config)
- /404 also blanks → app-wide module-init wedge → Tier 1(b) git bisect is the answer

This is a 30-second test that significantly informs W154+ direction.

### Tier 2 — Husky pre-commit prettier (~30-60 min, housekeeping)

Per W150 polish-v1 + W153 SW1 + W153 SW1 fixup: prettier drift on build-orchestrated.mjs + vite.config.mts was caught LOCALLY both times (W150 polish-v1 anti-pattern #15 has hit 3+ consecutive waves). Structural fix via husky + lint-staged:

```json
// frontend/package.json
"husky": "^9.x",
"lint-staged": "^15.x",
"lint-staged": {
  "src/**/*.{ts,tsx,js,jsx,json,css,scss,md}": ["prettier --write"],
  "tests/**/*.{ts,tsx,js,jsx}": ["prettier --write"],
  "scripts/**/*.mjs": ["prettier --write"],
  "*.{mts,ts}": ["prettier --write"]
}
```

```bash
# .husky/pre-commit
npx lint-staged
```

Closes:
- W150 §Honesty #13 polish-v1 prettier gap (recurring)
- W153 anti-pattern #15 carry-forward
- routeTree.gen.ts prettier drift (W153 didn't hit but recurring W147+W148+W149)

---

## Closing summary + commit graph

W153 commits on `egorribun` (in chronological order):

1. `568c51258` feat(wave153-sw1): NODE_ENV=development opt-in for /login wedge diagnosis [INITIAL — broke SSR]
2. `e563e992d` fix(wave153-sw1-fixup): keep mode=production to preserve SSR JSX transform [FIXUP — /login 200 restored]
3. `d931492e3` fix(wave153-sw2-react-418): defaultPendingComponent SSR-null to fix hydration mismatch [REAL BUG FIX]
4. `6b3737da7` wip(wave153-sw3-iter1): WebSocketProvider stub strip for /login wedge diagnostic [FAILED]
5. `25aefefc3` wip(wave153-sw3-iter2): AuthProvider stub strip (overlays iter 1) for /login wedge bisection [FAILED]
6. `d04d96b33` wip(wave153-sw3-iter3): max-strip ProvidersInner middle layer (LAST allowed iter) [FAILED]
7. `05ce98220` revert(wave153-sw3-iters): restore AppProviders + useChatWebSocket to SW2 state (mandatory defer) [REVERT]

**Main-merge candidates**: `568c51258` + `e563e992d` + `d931492e3` (SW1 + SW1 fixup + SW2 real bug fix).
**Diagnostic-only (kept in history)**: `6b3737da7` + `25aefefc3` + `d04d96b33` (SW3 wip iter commits; effects undone by `05ce98220` revert).

Final deployed state matches clean SW2: bundle `index-C-be2fJW.js` 341,887 b unminified + .map sidecar 648,245 b + /login 200/10,874b shell + 0 jsxDEV in server bundle + 0 Loading… in HTML. Container healthy. User-facing /login still blank (W152 §Honesty #14+#19+#20 persist — W154+ scope).

W153 SHIPPED concrete value:
- **SW1 infrastructure**: permanent diagnostic toolchain for any future /login wedge OR similar V8-wedge investigation. `FRONTEND_BUILD_UNMINIFIED=true` is a dev-compose-only flag, prod-safe by default.
- **SW2 React #418 fix**: real hydration mismatch bug closed. defaultPendingComponent SSR-aware via `import.meta.env.SSR` literal. Pattern recipe for future Suspense fallbacks that need to be SSR-suppressed.
- **SW3 6-provider exclusion**: narrows W154+ suspect surface significantly. Wedge is upstream of ProvidersInner (LanguageProvider / LazyMotion / __root.tsx-level / App.tsx StartClient / main.tsx createRoot / module-init).

**§Honesty trajectory**: 21-25 → 22-26 OPEN. Net slightly UP (4 new caveats from honest documentation of SW3 strip cascade outcome vs 2-3 closures). Per `feedback_perfectionism.md` honest framing; per W138 Lesson #8 dynamic counting (additive when surfacing real findings).

---

## N+3 rotation (W153 SW4 housekeeping)

Active waves pre-W153: W149/W150/W152.
Active waves post-W153: **W150/W152/W153**.
Rotation: `git mv docs/audits/AUDIT_WAVE149.md docs/audits/archive/AUDIT_WAVE149.md`.

INDEX.md updated to reflect:
- W153 added to "Active audits" with headline
- W149 demoted to "Archived audits" section under Frontend audit era

---

## NOT IN W153 (W154+ candidates)

- /404 + / cheap diagnostic (30-second user test before committing to W154+ Tier 1(b)/(d))
- Tier 1(b) git bisect
- Tier 1(d) Linux cross-OS test
- Husky pre-commit prettier (Tier 2 housekeeping)
- /messenger Phase 5 punted (W150 §Honesty #10 carry-forward)
- /admin polish arc continuation (W150 → W151+ → ... → W154+ still queued)

Per `feedback_planning_estimates.md`: W154+ wall-clock estimate is **3-7h core** depending on outcome:
- /404 diagnostic = 30 seconds
- If /404 renders → /login-specific scope, deep Login.tsx investigation ~1-2h
- If /404 blanks → Tier 1(b) git bisect ~1-2h OR Tier 1(d) Linux ~1-2h
- Plus wave-close overhead ~30-60 min polish

Historical anchoring: W150-W152 each spent 3-5h on /login-related work. W153 was 4-5h. W154+ should aim for resolution OR honest framework defer if Tier 1(b)/(d) require more than 1 wave's budget.
