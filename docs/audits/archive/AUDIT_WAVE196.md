# AUDIT — Wave 196 (Storybook story-coverage campaign, Batch 2 — LEAF tier complete + CONTEXT kickoff)

**Date**: 2026-05-29
**Branch**: `egorribun` (PR [#1126](https://github.com/egorribun/university_ecosystem/pull/1126))
**Scope**: User Q0 = **B + C** — *complete the LEAF tier* **and** *kick off the CONTEXT tier* (maximal-coverage reading of the standing "cover absolutely everything left for stories" directive).
**Wave streak**: 56th consecutive wave with brainstorming + Phase 1 Explore + Phase 3 Review + W141 anti-pattern discipline.

---

## Headline

- **27 NEW `.stories.tsx`** = **21 LEAF** (completes the LEAF tier) + **6 CONTEXT-cheap cards** (kickoff), across **4 story-SW + 1 audit-SW**.
- Discoverable story files **107 → 134** (+27). Storybook index **497 → 611 entries** (479 stories + **132 autodocs**; the **+27 autodocs** confirm exactly 27 new files; +87 story variants).
- **App bundle BYTE-IDENTICAL × 3** to the W195 baseline: main JS `index-C6pdnyI2.js` sha `1bff1fd7…c97` (filename + content unchanged) + server.js `f8bd8fab…dbb3` — the 27 stories had ZERO app-bundle impact (story-only; outside the Vite app entry graph). ≥54-wave LOCAL invariant → **≥55-wave**.
- Vitest **1270 passed / 12 skipped / 0 failed — UNCHANGED** (`.stories.tsx` outside the default vitest project).
- **Runtime smoke 27/27 clean, 0 failed** (real-Chrome render of one story per new file; 0 real console errors).

---

## Phase 1 Explore (3 agents) + Phase 3 verify-before-write

3 parallel Explore agents mapped LEAF candidates, CONTEXT-kickoff cards, and the decorator kit. **Phase 3 source-reads corrected 4 Agent over-counts** (W141 #3 vindications):
- **Map/Events/News ShortcutsOverlays** — Agent 1 tagged all three LEAF. Reading the sources: **MapShortcutsOverlay** takes `open`/`onClose` (controlled dialog → LEAF), but **EventsShortcutsOverlay + NewsShortcutsOverlay** are zero-prop, self-toggle `open` via `useState`+`window keydown`, `if(!open) return null` → static story renders nothing → **SKIP** (W195 audit was right).
- **MapWeatherBadge** — zero props, calls `useMapWeather()` internally, `if(!data) return null`; no clean hook-mock seam → **CONTEXT/defer**. But its child **MapWeatherPanel** is controlled (`data`/`open`/`onClose`) → **LEAF** (bonus; Agent mislabeled it CONTEXT).
- **mfa title** — Agent said `Auth/Mfa*`; W194 `MfaChallengeView.stories.tsx` uses `Auth/` → OtpEntry/TotpQrDisplay use `Auth/`.
- **EventInfo** props — Agent said optional; the interface shows `startsAt`/`endsAt`/`location`/`description` REQUIRED.

`preview.tsx` confirmed a strong global decorator set (`QueryClientProvider` + `I18nextProvider` + `LanguageProvider` + `AuthContext`(admin) + TanStack `RouterProvider` + padding wrapper; **NO LazyMotion**), which is why the "CONTEXT" cards render cheaply (the providers they need are ambient). The `<Link to="/events/$id">` cards de-risked by reading W195-storied **NewsDetailNavigation** (same `<Link>` pattern, clean) — the preview root-only router renders the anchor without throwing.

---

## Per-SW summary (all 1-iter; per-SW substitution rule applied)

| SW | Commit | Stories | Notes |
|----|--------|---------|-------|
| SW1 | `a1e168327` | Schedule + Map ×7 | DayColumn (`userRole="student"` → no DndContext) + ExportDropdown + MapHeader + MapCategoryFilter + MapSearchBar + MapShortcutsOverlay + MapWeatherPanel. `.schedule-theme`/`.map-theme` + LazyMotion for `m.*`. |
| SW2 | `1c8b144d4` | MFA + Dashboard + UI ×7 | OtpEntry + TotpQrDisplay (`Auth/`) + DateBullet + DashboardSectionSkeleton + NewsCardBackground (`.dashboard-theme` orb host) + Spotlight (LazyMotion) + SafeHtml. **Within-SW detect-secrets fix** (W138 L#1): the `DEMO_SECRET` keyword tripped the hook → moved `# pragma: allowlist secret` to a trailing comment on the line (CLAUDE.md ## Gotchas pattern); low-entropy demo TOTP seed. |
| SW3 | `6dafda1ce` | Activity + UI data-table ×7 | CardShell + TrendChip + ActivityTimelineItem + ActivityComparativeCard + ActivityExportButton (`.activity-theme`) + DataTableColumnHeader + DataTablePagination (**`useReactTable` harness** mirroring DataTable.tsx — the wave's riskiest piece; typechecked clean). **Completes the LEAF tier (21 leaves).** |
| SW4 | `78449569d` | CONTEXT kickoff ×6 | EventCardContent + EventInfo + NewsCardContent (title-as-`<Link>` via global RouterProvider) + EventQuickView + NewsQuickView (LazyMotion popovers, `position="bottom"`) + EventMedia (SmartImage + live/soon). Cheapest CONTEXT slice. |

---

## Verification (wave-close)

- Per-SW: `tsc --noEmit` = 0, `eslint --max-warnings=0` (the new files) = 0.
- Full `npm run lint` (src + tests) = **0**; `vitest run` = **1270 passed / 12 skipped / 0 failed** (unchanged); `npm audit --omit=dev` = **0**; i18n parity **18/18** (no new keys).
- `build-storybook` **SUCCESS**; index **611 entries** (479 stories + 132 autodocs; +27 autodocs = +27 files; 134 unique story files).
- **Bundle Build × 3**: main JS sha `1bff1fd7403b03e206534340bc89c53a37ce29d1240e923e83b4101c9c813c97` × 3 (file `index-C6pdnyI2.js`) + server.js sha `f8bd8fab1fbf8494c8c1fea885afcf30d08b7af27af6bdf4e3eeb6190f90dbb3` × 3 — **BYTE-IDENTICAL to W195** (content + main-JS filename). Cargo.lock no drift.
- **Runtime smoke**: self-served `storybook-static` + real-Chrome (Playwright chromium, channel "chrome") over one story per new file → **27/27 clean, 0 real console errors** (network noise — picsum/open-meteo/maptiler — filtered). Confirms the TanStack `<Link>` cards, LazyMotion `m.*` leaves, `useReactTable` harnesses, WASM SafeHtml, and lazy QR all render. Temp smoke script deleted post-run.

---

## §Honesty probe

OPEN caveats: **0-2** (unchanged — only the 2 W134 structural-by-design non-goals: W134 §H#2 bundle-delta recording-only + W134 §H#10 /messenger Phase 5 SSR by-design per W161 SW2). The 27 stories are net-positive coverage, NOT §Honesty closures.

NEW W196 notes (all resolved or by-design):
1. **detect-secrets keyword false-positive** (SW2) — `DEMO_SECRET = "…"` tripped the Secret-Keyword detector; resolved within-SW with the trailing `# pragma: allowlist secret` (documented CLAUDE.md pattern). NOT a (z) — known detect-secrets behavior.
2. **MapWeatherBadge + Events/News ShortcutsOverlays SKIPPED** — verified stateful-no-props / hook-internal-null (render nothing statically). Honest classification, not a gap.
3. **EventMedia/QuickView popovers** rely on `position="bottom"` + a sized relative host so the absolute/`bottom-full` popover stays in frame for the snapshot.

W141 anti-pattern compliance: **#1** (STRICT 1-iter) — every SW landed in 1 iter; SW2's detect-secrets fix is a within-SW SAME-mechanism sub-fix (W138 L#1: make the commit pass), not a pivot. **#3** (verify-before-write) — Phase 3 reads corrected 4 Agent classifications (ShortcutsOverlay controlled-vs-self-toggle, MapWeatherBadge/Panel, mfa title, EventInfo required props) + de-risked the `<Link>` cards via NewsDetailNavigation before writing. **#4** (closures after evidence) — bundle/coverage/smoke claims attributed only after Build × 3 + 27/27 smoke + index counts. **#15** (ARCHIVED) — all 4 SW commits + this audit fired the husky pre-commit chain cleanly (no `--no-verify`).

**0 NEW (z) discoveries** — extends the low-(z) streak (W145-W196). **0 NEW anti-patterns** (14-pattern register stable post-W159 #15 archival).

---

## Campaign arc — what remains after W196 (tracked)

- **LEAF tier COMPLETE** (W195 batch 1 = 30 leaves; W196 = 21 leaves → all genuinely prop-driven leaves now storied).
- **W197+ — CONTEXT tier continuation** (~59 remaining): logic-wrapper cards (EventCard/NewsCard via `useEventCardLogic`/`useNewsInteraction`+IndexedDB), edit/create dialogs (`useQueryClient` + mutations), **admin ×4** (query-cache-seeded), messenger ChatArea/MessengerSidebar/ProfileModal/NewChatModal, map panels (MapSidebar/MapControls — MapRef), schedule dialogs/tables, news comments/detail-body, profile editor/now-playing. Heavier mocks (hook-return-as-prop, `queryClient.setQueryData`, MapRef). ~2-3 stories/SW.
- **SKIP by design** — orchestrators (`*Feature.tsx`), providers/boundaries, route wrappers, hooks-misfiled-as-components, stateful-no-props overlays.
- **Honest estimate**: ~5-8 more waves to truly cover everything (CONTEXT slower). Per `feedback_planning_estimates.md`: range + short-horizon; re-plan each wave.

---

## NEW Gotcha (added to CLAUDE.md)

- **Storybook overlay story-worthiness: controlled (`open` prop) = LEAF; self-toggle (`useState`+`window keydown`, no prop) = SKIP** — MapShortcutsOverlay takes `open`/`onClose` (story passes `open: true` → renders the dialog) whereas EventsShortcutsOverlay/NewsShortcutsOverlay own their `open` state + `if(!open) return null`, so a static story renders nothing. And a **TanStack `<Link to="/typed/$id">` renders its anchor in Storybook's root-only preview router without throwing** (proven by NewsDetailNavigation + the W196 EventCardContent/NewsCardContent cards), so "CONTEXT" cards that only use `<Link>`/`useTranslation`/`useAuth`/`useQuery` are storyable via the global decorators alone — the providers they "need" are ambient in `preview.tsx`. For TanStack-table sub-components (`DataTableColumnHeader`/`DataTablePagination`), build a real `useReactTable({data, columns, …rowModels})` harness (mirror `DataTable.tsx`) to supply the `column`/`table` prop.
