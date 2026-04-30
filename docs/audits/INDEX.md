# Audit Trail Index

Reverse-chronological listing of per-wave audit reports. Created in Wave 122 polish-docs-v3 reorganization (commit `8eba94352`); Wave 123 SW5 executed first N+3 rotation (W120 → archive).

## Active audits

Recent audits (last 3 waves) — referenced from `CLAUDE.md ## Audit Trail` and current opening prompts:

| Wave | Date | Audit file | Headline |
|------|------|-----------|----------|
| 123 | 2026-04-30 | [AUDIT_WAVE123.md](AUDIT_WAVE123.md) | Frontend tech-debt + Chromatic UNBLOCKED — `strictExecutionOrder` workaround in `.storybook/main.ts` viteFinal closes W120 SW8 / W121 SW7 / W122 SW5 blocker; ScheduleCard CLS monitor stable at 0.0335; vendor-ui audit NO-OP for bundle |
| 122 | 2026-04-30 | [AUDIT_WAVE122.md](AUDIT_WAVE122.md) | Frontend tech-debt + bundle/image bandwidth — ~875 KB image savings + vendor-pdf truly lazy + DashboardHero CLS root-cause fix |
| 121 | 2026-04-29 | [AUDIT_WAVE121.md](AUDIT_WAVE121.md) | Inherited tech-debt close — /activity + /map LHCI MEASURABLE for first time post-W116 (Lighthouse 13.1.0); 22-key i18n gap closed |

## Archived audits

Older waves (W112-W120 + W21-W32 in `TOTAL_AUDIT_*` legacy format) — moved to `archive/` for repo-root cleanliness. Still tracked in git, still searchable via `grep -r "X" docs/audits/archive/`.

### Frontend audit era (W112-W120)

| Wave | Date | Audit file | Theme |
|------|------|-----------|-------|
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
