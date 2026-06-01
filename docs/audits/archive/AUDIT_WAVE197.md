# AUDIT — Wave 197 (Storybook story-coverage campaign, CONTEXT tier — Broad-doable A+C)

**Date**: 2026-05-29
**Branch**: `egorribun` (PR [#1126](https://github.com/egorribun/university_ecosystem/pull/1126))
**Scope**: User Q0 = **"1 и 3"** (options A + C) → refined via Q1 to **Broad-doable** — cover everything storyable in A+C **without new module-mocking infra**.
**Wave streak**: 57th consecutive wave with brainstorming + Phase 1 Explore + Phase 3 Review + W141 anti-pattern discipline.

---

## Headline

- **21 NEW `.stories.tsx`** across **7 story-SW + 1 audit-SW**, covering the cheap CONTEXT slice (A) + the storyable harder CONTEXT (C) — prop-driven sub-components, dialogs, the two CardViews (Spotlight harness), Schedule tables/dialogs, Map panels, and Messenger composition.
- Discoverable story files **134 → 155** (+21). Storybook index **611 → 688 entries** (535 stories + **153 autodocs**; the **+21 autodocs** confirm exactly 21 new files; +56 story variants).
- **App bundle BYTE-IDENTICAL × 3** to the W196 baseline: main JS `index-C6pdnyI2.js` sha `1bff1fd7…c97` (filename + content unchanged) + server.js `f8bd8fab…dbb3`. The lone source touch (`export MessengerContext`) tree-shakes completely. ≥55-wave LOCAL invariant → **≥56-wave**.
- Vitest **1270 passed / 12 skipped / 0 failed — UNCHANGED** (`.stories.tsx` outside the default vitest project).
- **Runtime smoke 21/21 clean, 0 failed** (real-Chrome render of one story per new file; 0 real console errors).

---

## Phase 1 Explore (3 agents) + Phase 3 verify-before-write

3 parallel Explore agents mapped the module-mocking gate, the cheap-A candidates, and the decorator kit. **Phase 3 source-reads drove every harness decision** (W141 #3):

- **Module-mocking gate (decisive)** — `@storybook/addon-vitest` is installed but Storybook module-mocking is **NOT configured** for story use (`setupTests.ts` `vi.mock`s are vitest-only). Per W196 lesson #12, the logic-wrapper cards (`EventCard`/`NewsCard` → `useEventCardLogic`/`useNewsInteraction`+IndexedDB) + `NewChatModal` (internal `/users` `useQuery`) **defer** to a future infra wave; their prop-driven sub-components were storied instead.
- **`RelatedNews`/`RelatedEvents` take `items[]` directly** (no internal `useQuery`) — the opening-prompt pattern #11 query-seeding decorator was **not needed at all** (verify-before-write win).
- **`useSpotlight()` is a clean exported hook** → `NewsCardView`/`EventCardView` storied via a real-hook harness (no MotionValue mock, no module-mocking).
- **`@/components/ui/Dialog` + `@/components/settings/ui/Dialogs` both `createPortal` to `document.body`** → EventEditDialog / EventDetailEditDialog / Schedule dialogs follow the EventQrDialog default-theme-only pattern.
- **`MapControls` null-guards every `mapRef.current?.` call** → a `useRef<MapRef|null>(null)` harness renders the panel with no live `<Map>` (easier than the W194 markers).
- **`useAppShell()` throws without a provider** → MapSidebar wraps the real, side-effect-free `<AppShellProvider>`; `getCampusBuildings("ru")[0]` drives it (props accept `undefined`).
- **MessengerSidebar does NOT call `useMessenger()`** (only `useMessengerController` as a *type*) → no context stub; only **ChatArea** needed the stub (the one source touch).

---

## Per-SW summary (all 1-iter; risk-ordered cheap → complex → context-family)

| SW | Commit | Stories | Notes |
|----|--------|---------|-------|
| SW1 | `e53195bc6` | News ×4 | NewsComments (t/getMoscowDate-as-prop harness) + NewsDetailBody (content-only, marked + WASM regex fallback + ToC) + NewsCardActions (absolute trigger in relative host) + RelatedNews (items[]). Ambient. |
| SW2 | `50751fa7c` | Events ×4 | EventActions (nested EventQrDialog) + EventEditDialog + EventDetailEditDialog (portal Dialogs → default-theme) + RelatedEvents (items[]). **Within-SW fix (W138 L#1)**: EventOut fixtures need the required readonly `image_url_optimized`. |
| SW3 | `29f22c3bf` | Profile/Map ×3 | ProfileModal (inline `fixed inset-0`, LazyMotion + `.messenger-theme`) + MapSidebar (real AppShellProvider + getCampusBuildings fixture) + MapControls (useRef null harness). **Within-SW fix**: UserOut needs readonly `avatar_url_optimized`/`cover_url_optimized`. |
| SW4 | `4867cfccf` | CardViews ×2 | NewsCardView + EventCardView via real `useSpotlight()` harness (Omit<…Props,"spotlight">) + LazyMotion; lazy admin/edit sub-components via Suspense. The complex tier — typechecked clean first pass. |
| SW5 | `69b16eca7` | Schedule tables ×3 | ScheduleDesktopTable + ScheduleMobileView + ScheduleListView. Pick<ReturnType<useScheduleData>> + display-helper fixtures (Lesson[] + Set<string> conflictedIds + Map notesMap) inside the real, pure `<SchedulePageProvider>`; Zustand stores global. |
| SW6 | `1f970a3ee` | Schedule dialogs ×3 | AddLessonDialog + EditLessonDialog + LessonDetailsDialog. Opened via SchedulePageProvider + a mount-effect `OpenDialogHarness` calling `openDialog(type[, lesson])`. Settings Dialog portals → default theme. |
| SW7 | `b7201d412` | Messenger ×2 | ChatArea (tsc-typed MessengerContext.Provider stub — the one source touch `export MessengerContext`, byte-identical-verified) + MessengerSidebar (no stub; Contact[] fixture). LazyMotion + `.messenger-theme`; ChatArea decorator gives the virtualizer a height. |

Variant totals: SW1 13 + SW2 10 + SW3 9 + SW4 8 + SW5 6 + SW6 4 + SW7 6 = **56** (matches the +56 story delta).

---

## Verification (wave-close)

- Per-SW: `tsc --noEmit` = 0, `eslint --max-warnings=0` (the new files) = 0.
- Full `npm run lint` (src + tests) = **0**; `vitest run` = **1270 passed / 12 skipped / 0 failed** (unchanged); `npm audit --omit=dev` = **0**; i18n parity **18/18** (no new keys — stories reuse component i18n).
- `build-storybook` **SUCCESS**; index **688 entries** (535 stories + 153 autodocs; +21 autodocs = +21 files; 155 unique story files).
- **Bundle Build × 3**: main JS sha `1bff1fd7403b03e206534340bc89c53a37ce29d1240e923e83b4101c9c813c97` × 3 (file `index-C6pdnyI2.js`, 180,273 b) + server.js sha `f8bd8fab1fbf8494c8c1fea885afcf30d08b7af27af6bdf4e3eeb6190f90dbb3` × 3 — **BYTE-IDENTICAL to W196** (content + main-JS filename). The `export MessengerContext` source touch tree-shakes (verified after SW7 + ×3 at close). Cargo.lock no drift.
- **Runtime smoke**: self-served `storybook-static` + real Chrome (Playwright chromium, channel "chrome") over one story per new file → **21/21 clean, 0 real console errors** (network noise — picsum/pravatar/qrserver/imgproxy/maptiler — filtered). Confirms TanStack `<Link>` cards, LazyMotion `m.*` trees, useSpotlight harnesses, portal dialogs, AppShellProvider/SchedulePageProvider/MessengerContext harnesses, and the virtualized ChatArea all render. Temp smoke script deleted post-run.

---

## §Honesty probe

OPEN caveats: **0-2** (unchanged — only the 2 W134 structural-by-design non-goals: W134 §H#2 bundle-delta recording-only + W134 §H#10 /messenger Phase 5 SSR by-design per W161 SW2). The 21 stories are net-positive coverage, NOT §Honesty closures.

NEW W197 notes (all resolved or by-design):
1. **Two within-SW fixture fixes (W138 L#1, SAME mechanism)** — SW2 EventOut + SW3 UserOut each have a required readonly `*_optimized` field a filtered grep hid; tsc caught both, fixed within the SW (not pivots).
2. **`export MessengerContext`** is the wave's only source touch — additive, unused by the app graph, tree-shaken to a byte-identical bundle (verified Build × 3). The NewsCardView `messages` arg cast mirrors the W189 ChatArea.test `as` pattern (Message[] ↔ UiMessage structural identity).
3. **Logic-wrapper cards (EventCard/NewsCard) + NewChatModal DEFERRED** to a future module-mocking-setup wave; admin `*Feature.tsx` + MessengerFeature are SKIP-by-design (orchestrators). Honest scope, not a gap — the storyable A+C was fully covered.

W141 anti-pattern compliance: **#1** (STRICT 1-iter) — every SW landed in 1 iter; the two within-SW fixture fixes are SAME-mechanism sub-fixes (make tsc pass), not pivots. **#3** (verify-before-write) — Phase 3 reads decided every harness (module-mocking gate, items[]-not-useQuery, portal-vs-inline, useAppShell-throws, MessengerSidebar-needs-no-stub) before writing. **#4** (closures after evidence) — bundle/coverage/smoke claims attributed only after Build × 3 + 21/21 smoke + index counts. **#15** (ARCHIVED) — all 8 commits fired the husky pre-commit chain cleanly (no `--no-verify`).

**0 NEW (z) discoveries** — extends the low-(z) streak (W145-W197). **0 NEW anti-patterns** (14-pattern register stable post-W159 #15 archival).

---

## Campaign arc — what remains after W197 (tracked)

- **LEAF tier COMPLETE** (W195 30 + W196 21). **CONTEXT tier well underway** (W196 6 + W197 21).
- **W198+ — remaining CONTEXT** (~38): logic-wrapper cards (EventCard/NewsCard) + NewChatModal — **gated on a module-mocking-setup wave**; remaining map panels (MapMiniOverview, MapWeatherBadge if storyable), profile editor / now-playing, news/event detail bodies + headers not yet covered, any remaining schedule/messenger sub-components. ~2-3 stories/SW.
- **SKIP by design** — orchestrators (`*Feature.tsx`), providers/boundaries, route wrappers, hooks-misfiled-as-components, stateful-no-props overlays.
- **Honest estimate**: ~4-7 more waves; the next natural step is a module-mocking-setup wave to unlock the logic-wrapper cards. Per `feedback_planning_estimates.md`: range + short-horizon; re-plan each wave.

---

## NEW Gotcha (added to CLAUDE.md)

- **Storybook CONTEXT-tier provider-harness selection by export surface** — pick the *real* provider when it is exported + side-effect-free (`SchedulePageProvider` for Schedule tables/dialogs, `AppShellProvider` for MapSidebar); stub the (newly-exported) context when the real provider does impure work (`MessengerContext.Provider` for ChatArea, since `MessengerProvider` runs WebSocket/query). Portal components (`@/components/ui/Dialog`, `@/components/settings/ui/Dialogs` via `createPortal`) escape themed decorators → default-theme-only stories (EventQrDialog pattern: no `themed` wrapper, `layout: "fullscreen"`). `MapControls` reads its map only in imperative handlers → a `useRef<MapRef|null>(null)` renders the full UI with no live `<Map>`. Generated `*Out` fixtures carry required **readonly `*_optimized`** fields (`image_url_optimized`, `avatar_url_optimized`, `cover_url_optimized`) — a `[a-z_]+:`-filtered grep hides them; include them or tsc fails.
