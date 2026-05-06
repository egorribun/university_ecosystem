# Audit Trail Index

Reverse-chronological listing of per-wave audit reports. Created in Wave 122 polish-docs-v3 reorganization (commit `8eba94352`); Wave 123 SW5 executed first N+3 rotation (W120 → archive); Wave 124 SW6 executed second rotation (W121 → archive); Wave 125 SW4 executed third rotation (W122 → archive); Wave 126 SW9 executed fourth rotation (W123 → archive); Wave 127 SW8 executed fifth rotation (W124 → archive); Wave 128 SW7 executed sixth rotation (W125 → archive).

## Active audits

Recent audits (last 3 waves) — referenced from `CLAUDE.md ## Audit Trail` and current opening prompts:

| Wave | Date | Audit file | Headline |
|------|------|-----------|----------|
| 128 | 2026-05-06 | [AUDIT_WAVE128.md](AUDIT_WAVE128.md) | TanStack Start v1 SSR Phase 5 continuation — **first per-route SSR on the W125-W127 foundation**: /dashboard SSRs with full Navbar + Footer + content (75,086 bytes vs W127 10,751 shell = +598%). 6 commits: SW1 AuthProvider Strategy A bridge (readSsrAuthHint plain function — NOT hook — + useProfileSync 5th param + 27 unit tests); SW2 flip `_auth.tsx ssr:true` + 9 sibling explicit `ssr:false` (TanStack Start inheritance contract REVISED post plan-review — child can ONLY make MORE restrictive); SW3 `<SsrRoot />` reads useRouteContext for per-request QueryClient (fixes singleton mismatch — loader.ensureQueryData visible to AuthProvider); MainLayout in both branches (hydration parity); dashboard.tsx ssr:true + loader Promise.all([events, stories]) + useIsomorphicLayoutEffect; SW3-followup Promise.all → Promise.allSettled (best-effort prefetch — backend-down doesn't blank-paint NO_FCP) + vite-plugin-pwa 1.2.0 → 1.3.0; SW4-fix restore `/* LHCI_CSS_PLACEHOLDER */` in __root.tsx INITIAL_PAINT_CSS (W125 Phase 2 dropped it — post-build-shell.mjs substitution silently no-op'd). Bundle: main 137,818 → 138,125 bytes (+307); `_shell.html` 10,659 → 65,602 bytes (+515% — MainLayout SSR'd at build). chrome-devtools-mcp 0 hydration errors on /dashboard + /map + /activity. **LHCI numerical Perf/CLS/LCP DEFERRED W129+** (Lighthouse + headless Chrome + Windows NO_FCP across all routes; structural environment, not W128 regression — chrome-devtools-mcp real Chrome works fine). Gates: tsc 0, lint 0, vitest **931p/12s/0f**, npm audit 0. SW6 vite-plugin-pwa Windows hang investigation: peer-dep bump bonus + Path B (programmatic vite.build) viable but needs vite 8 environments orchestration W129+ |
| 127 | 2026-05-05/06 | [AUDIT_WAVE127.md](AUDIT_WAVE127.md) | TanStack Start v1 SSR migration Phase 5 (provider hoisting + cookie-mirror) — `<AppProviders>` + `<ThemeProvider>` hoisted from `main.tsx`/`App.tsx` chain INTO `__root.tsx` `RootComponent` (both SSR + client share provider tree); SSR branch wraps with vanilla `<QueryClientProvider>` (PersistQueryClientProvider client-only); `useChatWebSocket` `useSyncExternalStore` 3rd arg `() => false` for React 19 SSR; ThemeContext + LanguageContext write `ue-mode` + `ue:language` cookies; `src/server.ts` reads via new `src/ssrTheme.ts` (75 lines + 20 tests) into 2 new `AsyncLocalStorage` instances exposed via `globalThis.__ssrThemeGetter__`/`__ssrLangGetter__`; `RootShell` renders `<html lang={lang} class={isDark ? "dark" : undefined} suppressHydrationWarning>` server-side; /map + /activity `ssr:'data-only'` annotation (silently ignored under `_auth.tsx ssr:false` per inheritance contract); foundation-only wave per user scope (no per-route SSR enablement; W128+ takes LCP wins); cookie permutations 4/4 working via vite preview + curl; LHCI deferred to W128 (W126 polish #3 hang reproduced) |
| 126 | 2026-05-05 | [AUDIT_WAVE126.md](AUDIT_WAVE126.md) | TanStack Start v1 SSR migration Phase 3 (auth-at-edge INFRASTRUCTURE-ONLY) — backend's existing `access_token_v2` HttpOnly cookie reused (no Set-Cookie additions; SW2 dropped after SW1 found backend chokepoint already provides everything); `src/ssrAuth.ts` (cookie parser + jose JWKS-based JWT validation against `/.well-known/jwks.json`) + 19 unit tests; `src/server.ts` `node:async_hooks` AsyncLocalStorage scopes auth per-request via `globalThis.__ssrAuthGetter__`; `src/router.ts` `getRouter()` reads SSR auth state replacing W125 SSR_STUB_AUTH; client bundle byte-identical to W125 baseline (137,813 bytes; jose + node:async_hooks server-only per Vite environments partition); SW5 + SW6 (per-route SSR enablement) DEFERRED to Phase 5 — provider hoisting prerequisite (UNBLOCKED in polish via root ssr:true + _auth/_admin ssr:false; /login SSRs 20,320 bytes form HTML, 0 hydration errors via chrome-devtools-mcp) |

## Archived audits

Older waves (W112-W122 + W21-W32 in `TOTAL_AUDIT_*` legacy format) — moved to `archive/` for repo-root cleanliness. Still tracked in git, still searchable via `grep -r "X" docs/audits/archive/`.

### Frontend audit era (W112-W125)

| Wave | Date | Audit file | Theme |
|------|------|-----------|-------|
| 125 | 2026-05-05 | [archive/AUDIT_WAVE125.md](archive/AUDIT_WAVE125.md) | TanStack Start v1 SSR migration Phase 1 + Phase 2 — `@tanstack/react-start@1.167.62` install; src/server.ts createServerEntry; __root.tsx shellComponent + ssr:false stub; post-build-shell.mjs replaces transformIndexHtml plugins |
| 124 | 2026-05-01 | [archive/AUDIT_WAVE124.md](archive/AUDIT_WAVE124.md) | XL Mobile Perf + LazyMotion Aggressive + Variance + SSR Pre-flight — vendor-ui **−56.6 KB / −34.8%**; CLS 0.033 → 0.017; SSR pre-flight design doc for W125+ |
| 123 | 2026-04-30 | [archive/AUDIT_WAVE123.md](archive/AUDIT_WAVE123.md) | Frontend tech-debt + Chromatic UNBLOCKED — `strictExecutionOrder` workaround in `.storybook/main.ts` viteFinal closes W120 SW8 / W121 SW7 / W122 SW5 blocker |
| 122 | 2026-04-30 | [archive/AUDIT_WAVE122.md](archive/AUDIT_WAVE122.md) | Frontend tech-debt + bundle/image bandwidth — ~875 KB image savings + vendor-pdf truly lazy + DashboardHero CLS root-cause fix |
| 121 | 2026-04-29 | [archive/AUDIT_WAVE121.md](archive/AUDIT_WAVE121.md) | Inherited tech-debt close — /activity + /map LHCI MEASURABLE for first time post-W116 (Lighthouse 13.1.0); 22-key i18n gap closed |
| 120 | 2026-04-28 | [archive/AUDIT_WAVE120.md](archive/AUDIT_WAVE120.md) | Inherited tech-debt close — CLS arc closed at WCAG Good ceiling (warn@0.15 → error@0.10); Schedule a11y 5→0 axe violations + Layout.tsx duplicate `<main>` global fix |
| 119 | 2026-04-28 | [archive/AUDIT_WAVE119.md](archive/AUDIT_WAVE119.md) | CLS push-gate close + LHCI sweep + Renovate semver-major (npm audit 9 → 0) |
| 118 | 2026-04-22 | [archive/AUDIT_WAVE118.md](archive/AUDIT_WAVE118.md) | CLS content-layout fix (XL own-wave) — footer + InstallPrompt + EventsBackdrop + Dashboard residuals |
| 117 | 2026-04-20–21 | [archive/AUDIT_WAVE117.md](archive/AUDIT_WAVE117.md) | Mobile performance pass (XL own-wave) — main chunk 291 KB → 174 KB (-40%) via OTEL chunk split + observability defer |
| 116 | 2026-04-20 | [archive/AUDIT_WAVE116.md](archive/AUDIT_WAVE116.md) | Frontend structural remainders + Storybook unblock |
| 115 | 2026-04-19 | [archive/AUDIT_WAVE115.md](archive/AUDIT_WAVE115.md) | Frontend structural remainders + a11y hit-box + housekeeping (RRD removed; npm audit 20→9) |
| 114 | 2026-04-18–19 | [archive/AUDIT_WAVE114.md](archive/AUDIT_WAVE114.md) | Frontend test infrastructure + a11y polish — `renderWithRouter` helper + 26 ported vitest files; `<MotionConfig reducedMotion="user">` |
| 113 | 2026-04-18 | [archive/AUDIT_WAVE113.md](archive/AUDIT_WAVE113.md) | Frontend runtime verification — multi-browser Playwright + 2 pre-existing WCAG 2.2 AA contrast violations + LHCI mobile baseline |
| 112 | 2026-04-17 | [archive/AUDIT_WAVE112.md](archive/AUDIT_WAVE112.md) | Frontend production audit cross-page (XL) — `noUncheckedIndexedAccess`, multi-browser Playwright, useURLState hook, `features/activity/` migration |

### Pre-W21 era (mixed naming: `AUDIT_YYYY_MM_DD_*`, `WAVE19_FULL_AUDIT`, `TOTAL_AUDIT_2026`)

Earliest audit-trail files. Mixed naming — these predate the `TOTAL_AUDIT_WAVE<N>.md` convention (W21+) and the `AUDIT_WAVE<N>.md` convention (W112+). Two files (`AUDIT_2026_03_06_WAVE3.md` + `AUDIT_2026_03_07_FINAL.md`) remain locally-only via `.gitignore` lines 315-316 — historical decision (likely large content); they exist on this machine in `archive/` but aren't pushed to remote.

| Wave | Date | Audit file | Theme |
|------|------|-----------|-------|
| 19 | 2026-03-24 | [archive/WAVE19_FULL_AUDIT.md](archive/WAVE19_FULL_AUDIT.md) | Wave 19 Total Backend Audit Report |
| FINAL | 2026-03-19 | [archive/AUDIT_2026_03_19_FINAL.md](archive/AUDIT_2026_03_19_FINAL.md) | Тотальный Аудит Архитектуры и Безопасности |
| (cross-wave) | 2026-03-24 | [archive/TOTAL_AUDIT_2026.md](archive/TOTAL_AUDIT_2026.md) | TOTAL AUDIT 2026 — Platform-wide |
| 9 | 2026-03-16 | [archive/AUDIT_2026_03_16_WAVE9.md](archive/AUDIT_2026_03_16_WAVE9.md) | Security & Architecture Audit |
| 8 | 2026-03-15 | [archive/AUDIT_2026_03_15_WAVE8.md](archive/AUDIT_2026_03_15_WAVE8.md) | Security & Architecture Audit |
| 7 | 2026-03-07 | _local-only_ — `archive/AUDIT_2026_03_07_FINAL.md` (gitignored) | Wave 7 final audit |
| 3 | 2026-03-06 | _local-only_ — `archive/AUDIT_2026_03_06_WAVE3.md` (gitignored) | Wave 3 initial audit |

### Legacy backend audit era (W21-W32, `TOTAL_AUDIT_*` naming)

Pre-frontend-audit-era files using `TOTAL_AUDIT_WAVE<N>.md` naming. Backend security/performance audits.

| Wave | Audit file | Theme |
|------|-----------|-------|
| 32 | [archive/TOTAL_AUDIT_WAVE32.md](archive/TOTAL_AUDIT_WAVE32.md) | 7 deferred items closed (ChatService DI, Redis circuit breaker, L1 XFetch jitter, Helm chart, JWKS hot-reload, ADR-012/013) |
| 31 | [archive/TOTAL_AUDIT_WAVE31.md](archive/TOTAL_AUDIT_WAVE31.md) | 13 issues — gateway os.Exit, WS notification, Safari localStorage, AbortSignal, gRPC timeout, pod anti-affinity |
| 30 | [archive/TOTAL_AUDIT_WAVE30.md](archive/TOTAL_AUDIT_WAVE30.md) | 22 issues — free-threading singleton, symlink path traversal, PII regex, ruff pin |
| 28 | [archive/TOTAL_AUDIT_WAVE28.md](archive/TOTAL_AUDIT_WAVE28.md) | Python 2 except syntax fixed (43 violations, 21 files); CSRF timing |
| 27 | [archive/TOTAL_AUDIT_WAVE27.md](archive/TOTAL_AUDIT_WAVE27.md) | 18 issues — ws-hub limits, rate-limit fail-closed, file-processor path traversal |
| 26 | [archive/TOTAL_AUDIT_WAVE26.md](archive/TOTAL_AUDIT_WAVE26.md) | Python 2 except syntax (44 occurrences); Helm secrets; Go input validation |
| 25 | [archive/TOTAL_AUDIT_WAVE25.md](archive/TOTAL_AUDIT_WAVE25.md) | 20 issues — NullSessionBackend fail-closed; persisted query manifest threading |
| 24 | [archive/TOTAL_AUDIT_WAVE24.md](archive/TOTAL_AUDIT_WAVE24.md) | 20 issues — ws-hub Hub.ctx; file-processor GraphQL depth+timeout; React Compiler memo cleanup |
| 23 | [archive/TOTAL_AUDIT_WAVE23.md](archive/TOTAL_AUDIT_WAVE23.md) | 21 issues — OTEL metrics bridge; useSuspenseQuery; asyncio.TaskGroup; adaptive debounce |
| 22 | [archive/TOTAL_AUDIT_WAVE22.md](archive/TOTAL_AUDIT_WAVE22.md) | 21 issues — Renovate Bot crypto manual review; SBOM; concurrency tests |
| 21 | [archive/TOTAL_AUDIT_WAVE21.md](archive/TOTAL_AUDIT_WAVE21.md) | 21 issues — bcrypt removal; Argon2id only; volatile-lru |

## Conventions

- **Naming**: `AUDIT_WAVE<N>.md` for waves 112+; `TOTAL_AUDIT_WAVE<N>.md` for legacy waves 21-32.
- **Structure**: each audit has §Executive summary, §Commits table, §SW1-N narrative, §End-of-wave gates, §Honesty probe, §Wave N+1 hand-off, optionally §Polish pass.
- **Promotion to/from archive**: when a wave closes and N+3 next opens, the oldest of the 3 active audits moves to `archive/`. Maintain "last 3 waves active" invariant.
- **Cross-references**: active audits reference each other via relative `./AUDIT_WAVE<N>.md`. Active → archived: `./archive/AUDIT_WAVE<N>.md`. Archived audits' internal cross-refs point to historical paths (root-level) and were left as-is — they're historical records.

## Git history

All files preserved via `git mv` — `git log --follow docs/audits/AUDIT_WAVE122.md` shows full history including pre-move commits at root.
