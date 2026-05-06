# Audit Trail Index

Reverse-chronological listing of per-wave audit reports. Created in Wave 122 polish-docs-v3 reorganization (commit `8eba94352`); Wave 123 SW5 executed first N+3 rotation (W120 → archive); Wave 124 SW6 executed second rotation (W121 → archive); Wave 125 SW4 executed third rotation (W122 → archive); Wave 126 SW9 executed fourth rotation (W123 → archive); Wave 127 SW8 executed fifth rotation (W124 → archive); Wave 128 SW7 executed sixth rotation (W125 → archive); Wave 129 SW8 executed seventh rotation (W126 → archive); Wave 130 SW5 executed eighth rotation (W127 → archive).

## Active audits

Recent audits (last 3 waves) — referenced from `CLAUDE.md ## Audit Trail` and current opening prompts:

| Wave | Date | Audit file | Headline |
|------|------|-----------|----------|
| 130 | 2026-05-06 | [AUDIT_WAVE130.md](AUDIT_WAVE130.md) | Phase 5 SSR continuation — **/schedule SSR + Weather TanStack Query refactor**. Closes 1 of 5 remaining W128 SW2 ssr:false opt-downs (4 left: messenger × 2, profile, settings). Total SSR routes after W130: **6** (≥6 threshold MET for W125 Phase 4 deploy infra readiness). 5 commits: SW1 (`6efa841df`) NEW `frontend/src/api/hooks/schedule.ts` — pure `scheduleGroupsQueryOptions()` + `pageScheduleQueryOptions(groupId)` factories mirroring W129 events.ts/news.ts placement; useScheduleData refactored to spread the factories (queryKey shape preserved for cache identity); Schedule.cache.test.tsx updated `expect.anything()` for new `{ signal }` arg pattern. SW2 (`94804567a`) `/schedule` SSR enabled — removed `ssr: false` (inherits `_auth.tsx ssr: true` W128 SW2) + `loader: Promise.allSettled([context.queryClient.ensureQueryData(scheduleGroupsQueryOptions())])`. **Partial-SSR strategy**: prefetch only `/groups` (auth-only, no group_id required); lessons fetch client-side post-hydration. Sequential `/users/me + /schedule/{group_id}` SSR DEFERRED to W131+ (cookie forwarding own scope). SW3 (`5faa0ef6a`) Weather full TanStack Query migration — NEW `frontend/src/api/hooks/weather.ts` (`weatherQueryOptions(coordinates, cacheTtlMs)` factory with 4-decimal coordinate precision + sessionStorage placeholderData for cold-mount fast paint). useWeather refactored 175 → 91 lines (-84). Public `UseWeatherResult` shape unchanged. 24 new factory tests in `ssrFactories.test.ts` (16 → 40). SW4 (`1879cc474`) npm audit fix — `ip-address` 10.1.0 → 10.2.0 (XSS in Address6, GHSA-v2v4-37r5-5v8g; recently disclosed CVE; theoretical for this codebase but closing audit-baseline regression). SW5 audit + memory + N+3 rotation. Bundle (PROD × 3 reproducible): main 138,845 → **138,974 bytes** (+129); `_shell.html` 65,778 → 65,872 (+94). VITE_LHCI build 137,769 + 65,954. Curl 11 routes (VITE_LHCI preview): **/schedule 70,847 bytes** (NEW SSR vs ~10,500 shell pre-W130 = +577% SSR content); /dashboard 75,384 (+94); /events 90,059 (+94); /events/$id 71,676 (+40); /news 78,659 (+94); /news/$id 68,445 (+40); /map 42,313 (data-only +94); /activity 65,917 (data-only +94); /404 64,485 (+94 client-only); /login + / 307 → /dashboard. chrome-devtools-mcp visual smoke 4 SSR routes (/dashboard + /schedule + /events + /news): 0 React hydration errors each. Tree-shake invariant: PROD 0 mock-user references, VITE_LHCI 1 (useFocusTrap chunk). Gates: tsc 0, lint 0, vitest **983p/12s/0f** (W129 baseline 959 + 24 new factory tests), npm audit **0 vulnerabilities** post-fix, Cargo.lock no drift (idempotent ≥ 20 waves) |
| 129 | 2026-05-06 | [AUDIT_WAVE129.md](AUDIT_WAVE129.md) | Phase 5 SSR continuation — **/news + /events + /events/$id + /news/$id all SSR-enabled**, closes 4 of 9 W128 SW2 ssr:false opt-downs. 7 commits: SW1 (`d70ac9ce2`) /events index — drop `ssr: false` + add `prefetchEventsListQuery` loader (factory existed since W128, drop-in 15 min) + NEW `src/utils/loaderLang.ts` shared `resolveLoaderLang()` helper (SSR via `globalThis.__ssrLangGetter__` from W127 SW4 cookie chain; client via `localStorage.getItem("ue:language")` mirror); SW2 (`0a25f82f5`) /events/$id — extract `eventDetailQueryOptions` factory + ensureQueryData loader; SW3 (`ade0c4e88`) extract `prefetchNewsListQuery` factory mirroring events.ts:261-272 exactly (reuses pre-existing pure `createNewsListQueryFn`); SW4 (`1312c593c`) /news index loader; SW5 (`8a1e35113`) /news/$id — extract `newsDetailQueryOptions(id, language)` factory + refactor `pages/NewsDetail.tsx` to use it (cache identity preserved); SW6 (`78b1b5f3d`) NEW `.github/workflows/lhci-linux.yml` workflow_dispatch trigger for on-demand Lighthouse on Linux runner — closes W128 LHCI deferral with honest re-framing (existing `frontend-tests.yml lighthouse:` job already runs on every PR since W117+; real W128 blocker was LOCAL Windows measurement). Bundle (PROD × 3 reproducible): main 138,125 → **138,845 bytes** (+720); `_shell.html` 65,602 → 65,778 (+176). VITE_LHCI build 137,640 + 65,860. Curl 9 routes (VITE_LHCI preview): /events 89,965 / /events/$id 71,636 / /news 78,565 / /news/$id 68,405 — all > 30 KB; /dashboard preserved 75,290 (+204 modulepreload graph delta); /map + /activity data-only ~42-66 KB shells preserved. chrome-devtools-mcp /events visual smoke: 0 React hydration errors. Tree-shake invariant: PROD 0 mock-user references, VITE_LHCI 1 (useFocusTrap chunk). Gates: tsc 0, lint 0, vitest **931p/12s/0f** (W128 baseline preserved exactly), npm audit 0, Cargo.lock no drift |
| 128 | 2026-05-06 | [AUDIT_WAVE128.md](AUDIT_WAVE128.md) | TanStack Start v1 SSR Phase 5 continuation — **first per-route SSR on the W125-W127 foundation**: /dashboard SSRs with full Navbar + Footer + content (75,086 bytes vs W127 10,751 shell = +598%). 6 commits: SW1 AuthProvider Strategy A bridge (readSsrAuthHint plain function — NOT hook — + useProfileSync 5th param + 27 unit tests); SW2 flip `_auth.tsx ssr:true` + 9 sibling explicit `ssr:false` (TanStack Start inheritance contract REVISED post plan-review — child can ONLY make MORE restrictive); SW3 `<SsrRoot />` reads useRouteContext for per-request QueryClient (fixes singleton mismatch — loader.ensureQueryData visible to AuthProvider); MainLayout in both branches (hydration parity); dashboard.tsx ssr:true + loader Promise.all([events, stories]) + useIsomorphicLayoutEffect; SW3-followup Promise.all → Promise.allSettled (best-effort prefetch — backend-down doesn't blank-paint NO_FCP) + vite-plugin-pwa 1.2.0 → 1.3.0; SW4-fix restore `/* LHCI_CSS_PLACEHOLDER */` in __root.tsx INITIAL_PAINT_CSS (W125 Phase 2 dropped it — post-build-shell.mjs substitution silently no-op'd). Bundle: main 137,818 → 138,125 bytes (+307); `_shell.html` 10,659 → 65,602 bytes (+515% — MainLayout SSR'd at build). chrome-devtools-mcp 0 hydration errors on /dashboard + /map + /activity. **LHCI numerical Perf/CLS/LCP DEFERRED W129+** (Lighthouse + headless Chrome + Windows NO_FCP across all routes; structural environment, not W128 regression — chrome-devtools-mcp real Chrome works fine). Gates: tsc 0, lint 0, vitest **931p/12s/0f**, npm audit 0. SW6 vite-plugin-pwa Windows hang investigation: peer-dep bump bonus + Path B (programmatic vite.build) viable but needs vite 8 environments orchestration W129+ |

## Archived audits

Older waves (W112-W122 + W21-W32 in `TOTAL_AUDIT_*` legacy format) — moved to `archive/` for repo-root cleanliness. Still tracked in git, still searchable via `grep -r "X" docs/audits/archive/`.

### Frontend audit era (W112-W127)

| Wave | Date | Audit file | Theme |
|------|------|-----------|-------|
| 127 | 2026-05-05/06 | [archive/AUDIT_WAVE127.md](archive/AUDIT_WAVE127.md) | TanStack Start v1 SSR migration Phase 5 (provider hoisting + cookie-mirror) — `<AppProviders>` + `<ThemeProvider>` hoisted into `__root.tsx`; ThemeContext + LanguageContext write `ue-mode` + `ue:language` cookies; `src/ssrTheme.ts` + 2 new AsyncLocalStorage instances (`globalThis.__ssrThemeGetter__`/`__ssrLangGetter__`); RootShell renders `<html lang class>` server-side; foundation-only wave per user scope (no per-route SSR enablement; W128+ takes LCP wins) |
| 126 | 2026-05-05 | [archive/AUDIT_WAVE126.md](archive/AUDIT_WAVE126.md) | TanStack Start v1 SSR migration Phase 3 (auth-at-edge INFRASTRUCTURE-ONLY) — `src/ssrAuth.ts` + jose JWKS-based JWT validation; `node:async_hooks` AsyncLocalStorage scopes auth per-request via `globalThis.__ssrAuthGetter__`; client bundle byte-identical to W125 (jose server-only via Vite environments partition) |
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

Wave 130 SW5 N+3 rotation: `git mv docs/audits/AUDIT_WAVE127.md docs/audits/archive/AUDIT_WAVE127.md` — active waves after rotation: W128, W129, W130.
