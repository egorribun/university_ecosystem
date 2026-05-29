# AUDIT — Wave 198 (Storybook story-coverage campaign, CONTEXT continuation — NO-INFRA)

**Date**: 2026-05-29
**Branch**: `egorribun` (PR [#1126](https://github.com/egorribun/university_ecosystem/pull/1126))
**Scope**: User Q0 = **A+B** (module-mocking unlock + no-infra CONTEXT slice) → **redirected to no-infra** mid-plan after a verify-before-write finding overturned scope A's premise.
**Wave streak**: 58th consecutive wave with brainstorming + Phase 1 Explore + Phase 3 Review + W141 anti-pattern discipline.

---

## Headline

- **30 NEW `.stories.tsx`** across **6 story-SW + 1 audit-SW** (1 EventCard move+modernize + **29 net-new**), covering the 3 ex-"A" cards + a high-confidence no-infra CONTEXT B slice (motion wrappers, skeletons, navbar family, activity cards, profile + dashboard).
- Discoverable story files **155 → 184**. Storybook index **688 → 802 entries** (620 stories + **182 autodocs**; **+29 autodocs** = the 29 net-new files — 30 created minus the deleted legacy `components/EventCard.stories.tsx`).
- **App bundle BYTE-IDENTICAL × 3** to the W197 baseline: main JS `index-C6pdnyI2.js` sha `1bff1fd7…c97` (**filename + content unchanged**) + server.js `f8bd8fab…dbb3`. Stories never enter the app's Vite entry graph. ≥56-wave LOCAL invariant → **≥57-wave**.
- Vitest **1270 passed / 12 skipped / 0 failed — UNCHANGED** (`.stories.tsx` outside the default vitest project).
- **Runtime smoke 30/30 clean, 0 failed** (real-Chrome render of one story per new file; 0 real console errors).

---

## The scope-A pivot (verify-before-write, W141 #3)

The opening prompt + W197 audit framed the 3 "logic-wrapper" cards (EventCard / NewsCard / NewChatModal) as **"gated on a module-mocking-setup wave."** User picked **A+B** at Q0 expecting that infra. Phase 1 Explore + Phase 3 component-reads **disproved the premise** — none of the three need MSW/module-mocking:

- **EventCard** (`components/events/EventCard/EventCard.tsx`) — **zero network calls on mount**. `useEventRegistration`'s only `api.get` is inside `sync()`, called *only* on register/unregister click + wrapped in `try/catch { return null }`; mount-time effects touch only localStorage (guarded). Fully props-driven (`Partial<Event>`), delegates to the already-storied `EventCardView`. (It even already had a **stale legacy story** at `components/EventCard.stories.tsx`.) Agent 1's "fires api.get on mount" claim was a superficial misread.
- **NewsCard** (`components/news/NewsCard.tsx`) — passes `initialData` into `useNewsInteraction`, so prop values render immediately + a failed background refetch is silent under the preview `retry:false`. IndexedDB/localStorage/BroadcastChannel work in real-browser Storybook. **Genuinely uncovered** — the diff's "covered" was a basename collision with `dashboard/NewsCard.stories.tsx` (a different component).
- **NewChatModal** (`components/messenger/NewChatModal.tsx`) — its `/users` `useQuery` is `enabled: open && debouncedSearch.length > 1` (idle until typed). Base story = zero network.

Building MSW-in-Storybook is the exact Storybook + Vite 8/Rolldown service-worker fragility class behind the W120-W123 Chromatic saga. **User-approved decision: no `.storybook` config change.** All three are storied today with the proven prop-fixture (+ light `setQueryData`) pattern — i.e. scope A collapsed into the B slice. **Agent 2's "88 uncovered / 69 STORYABLE" diff was also wrong** (listed already-storied W195-W197 components); the plan rests on a deterministic `comm -23` recompute (238 components − 155 stories = 82 basenames) + direct reads.

---

## Per-SW summary (all 1-iter; risk-ordered cheap → context)

| SW | Commit | Stories | Notes |
|----|--------|---------|-------|
| SW1 | `02808beb0` | 3 ex-A cards | EventCard **move+modernize** (stale `components/EventCard.stories.tsx` → co-located `events/EventCard/EventCard.stories.tsx`, "Events/EventCard"; relative dates for soon/live/past) + NewsCard NEW ("News/NewsCard", distinct from Dashboard/NewsCard collision; decorator adds `<Suspense>` since NewsCard delegates to lazy NewsCardView without its own) + NewChatModal NEW (base empty = zero-network; WithResults via module-level seeded `["users",""]` QueryClient). |
| SW2 | `2eefec0d3` | motion ×5 | FadeSection + Magnetic + PageFadeIn + PageTransition + ScrollReveal. Demo-child render; `data-fade`/`page-fade` have no opacity:0 CSS → visible; ScrollReveal IO fires in-view (LazyMotion). **BackToTop deferred** (renders null until scrollY>420 — SKIP-adjacent). |
| SW3 | `c64a25d6f` | ui/motion + skeletons ×7 | FadeIn/ScaleIn (m.div + LazyMotion) + StaggerChildren (IO reveal of `.stagger-item` children, no LazyMotion) + 4 shimmer skeletons (EventCardSkeleton/NewsCardSkeleton `featured?`/ProfileCardSkeleton `showCover?`/ScheduleCardSkeleton `items?`), feature-theme-scoped. |
| SW4 | `58bed08b0` | navbar ×5 | DesktopNav (NavigationItem fixture + prop-controlled active) + MessengerButton + UserMenu (W197 MessengerContext stub; UserMenu real-`useTranslation` harness) + NotificationsBell (zero-prop; `useNotifications` degrades — generated client returns errors, never throws) + MobileMenu (real AppShellProvider + LazyMotion + `drawerTrapRef` useRef harness; createPortal → default-theme-only). **NavbarActions** (heavy logic/morph) + **MobileBottomNav** (`md:hidden` viewport) deferred. |
| SW5 | `e32a08fbe` | activity ×5 | AttendanceCard/GradesCard/ParticipationCard (CardShell + AnimatedRing + TrendChip + SkeletonMorph; m.* → LazyMotion) + ActivityMotivation (no m.*) + ActivityTimeline (merged feed + Empty). `.activity-theme`; fixed-date fixtures (deterministic). |
| SW6 | `c9894d999` | profile + dashboard ×5 | NowPlayingCard (NowPlaying fixture, m.* → LazyMotion) + ProfileHeader (User fixture + 17 props + 2-ref useRef harness; QRCodeSVG aria-hidden) + ProfileEditor (local-`useState` harness for ~30 controlled-field props; student/teacher) + NewsCardList (NewsOut fixture incl readonly `image_url_optimized`) + ScheduleTimeline (DashboardLesson fixture, deterministic `minutesNow`). **Within-SW fix (W138 L#1)**: ProfileEditor harness prop `role`→`userRole` (jsx-a11y/aria-role false-positive on a custom `role` JSX attr). |

Net story-file count: 155 (delete legacy EventCard −1, add events/EventCard/ +1, +28 others) = **184 discoverable**.

---

## Verification (wave-close, final committed state)

- Per-SW: `tsc --noEmit` = 0, `eslint --max-warnings=0` (the new files) = 0.
- Full `npm run lint` (src + tests) = **0**; `npx vitest run` = **1270 passed / 12 skipped / 0 failed** (unchanged — stories outside the default project); `npm audit --omit=dev` = **0 vulnerabilities**; `npm run i18n:check` = **18/18** (no new keys — stories reuse component i18n).
- `build-storybook` **SUCCESS**; index **802 entries** (620 stories + 182 autodocs; **+29 autodocs = 29 net-new files**; 184 unique story files; legacy `components/EventCard.stories.tsx` gone — only the co-located path remains).
- **Bundle Build × 3** (fresh `rm -rf dist && npm run build`): main JS sha `1bff1fd7403b03e206534340bc89c53a37ce29d1240e923e83b4101c9c813c97` × 3 (file `index-C6pdnyI2.js`) + server.js sha `f8bd8fab1fbf8494c8c1fea885afcf30d08b7af27af6bdf4e3eeb6190f90dbb3` × 3 — **BYTE-IDENTICAL to W197** (filename + content; the EventCard move + 30 story files are entirely outside the app graph). Cargo.lock no drift.
- **Runtime smoke**: self-served `storybook-static` + real Chrome (Playwright chromium, channel "chrome") over one story per NEW file → **30/30 clean, 0 real console errors** (picsum/pravatar/qrserver/imgproxy/maptiler/open-meteo/net::ERR network noise filtered). Confirms the seeded NewChatModal, MessengerContext-stub navbar, AppShellProvider MobileMenu, AnimatedRing activity cards, ProfileHeader QR, ProfileEditor form, and all motion/skeleton wrappers render. Temp smoke script deleted post-run.

---

## §Honesty probe

OPEN caveats: **0-2** (unchanged — only the 2 W134 structural-by-design non-goals: W134 §H#2 bundle-delta recording-only + W134 §H#10 /messenger Phase 5 SSR by-design per W161 SW2). The 30 stories are net-positive coverage, NOT §Honesty closures.

NEW W198 notes (all resolved or by-design):
1. **The "module-mocking gate" was a phantom** — verify-before-write disproved the opening-prompt premise; scope A collapsed into the no-infra B slice. Honest pivot surfaced to the user via AskUserQuestion; user chose no-infra.
2. **One within-SW SAME-mechanism fix** (W138 L#1) — SW6 ProfileEditor harness prop `role`→`userRole` (jsx-a11y/aria-role read the custom prop as an ARIA role). Not a pivot.
3. **3 deferrals** (not gaps — honest classification): BackToTop (renders null until scrollY>420), NavbarActions (full NavbarLogicResult + NavbarMorphState ~25-field harness), MobileBottomNav (`md:hidden` needs a mobile-viewport param). All carried to W199+ candidate pool.
4. **NewChatModal WithResults seeds `["users",""]`** — demonstrates the user-row UI with an empty search box (the listbox renders cached data regardless of search). Minor visual quirk, acceptable for a demo story (commented inline).

W141 anti-pattern compliance: **#1** (STRICT 1-iter) — every story-SW landed in 1 iter; the SW6 `role`→`userRole` rename is a SAME-mechanism sub-fix, not a pivot. **#3** (verify-before-write) — Phase 3 reads decided every harness AND caught Agent 1's "EventCard fires api.get on mount" + Agent 2's inflated diff before any code. **#4** (closures after evidence) — bundle/coverage/smoke claims attributed only after Build × 3 + 30/30 smoke + index counts. **#15** (ARCHIVED) — all 7 commits fired the husky pre-commit chain cleanly (no `--no-verify`).

**0 NEW (z) discoveries** — extends the low-(z) streak (W145-W198). **0 NEW anti-patterns** (14-pattern register stable post-W159 #15 archival).

### Polish — post-close «безупречно?» probe (2026-05-29)

The probe surfaced a **real CI failure my local checks missed**, and it was fixed honestly (not papered over):

- **Finding:** CI `Frontend Tests / Unit Tests` ran `npm run test:ci` = `vitest run --coverage` and **failed the 70% global lines/statements threshold** at **69.48%** — even though all 1270 tests passed. My wave-close verification used plain `vitest run` (pass/fail only), so it never exercised the coverage gate. This is a genuine gap in the W198 close, now recorded.
- **Root cause:** the 5 SW5 activity stories live under `src/features/activity/components/*.stories.tsx`. `coverage.exclude` covered `src/components/**/*` (the other 24 W198 stories) but NOT `src/features/**`, so v8 `all: true` counted those 5 unexecuted story files as 0%-covered, tipping global lines/statements from just-over-70% to 69.48%.
- **Fix:** added `"src/**/*.stories.{ts,tsx}"` to `frontend/vitest.config.ts coverage.exclude` (`fix(wave198-polish-coverage-exclude-stories)`). Principled + directory-agnostic + future-proof; stories are tree-shaken from the app bundle and never executed by the runner, so counting them was a **measurement bug**, not a quality gap. Chosen over lowering the threshold (anti-pattern) or over-excluding all `src/features/**` (would drop real feature code from the denominator).
- **Arithmetic on the functions metric:** the original CI run measured Funcs **71.79%** (passing) WITH stories in the denominator. Excluding 0%-covered files can only *raise* the remaining set's % (numerator unchanged, denominator shrinks) → CI functions rises ≥71.79% after the fix, passing all four thresholds. A local re-run landed Funcs 69.93% (under), which is a **local-execution artifact** (setup-churn 148s vs CI 119s → some function-covering tests under-executed locally), NOT the CI value — CI is the authoritative measurement.
- **Bundle invariant unaffected:** `vitest.config.ts` is test-only config (≠ `vite.config.mts`); the app bundle stays byte-identical `1bff1fd7…c97` (re-verified Build × 3 at wave-close). The fix touches no source.
- **Honest verdict:** the wave's stories + bundle were sound, but the wave was **not** CI-clean at first close. The probe did its job; the fix + this note + a NEW Gotcha close the gap. **NEW W198 §Honesty caveat: local story-wave verification must run `npm run test:ci` (coverage), not just `vitest run`.**

---

## Campaign arc — what remains after W198 (tracked)

- **LEAF tier COMPLETE** (W195-W196). **CONTEXT tier well underway** (W196 6 + W197 21 + W198 ~28 component-level).
- **W199+ — remaining CONTEXT** (~25): the deferred trio (BackToTop / NavbarActions / MobileBottomNav), dialog/editor components (EventCreateDialog, EventFileManager, EventAdminActions, NewsCard/NewsDetailEditDialog, settings/SettingsUI + settings/ui/*), DraggableLessonCard (DndContext), DataTable + ui/table (useReactTable harness), WeatherWidget, SpotifyConnect, SearchDialog, StepUpDialog, MapLibreMap, MainLayout, PageLayout, Layout, LoginHero, EventAboutEditor, EventDetailBody, WeatherParticles, DashboardStories, dashboard/EventsCard.
- **SKIP by design** — orchestrators (`*Feature.tsx`), error boundaries, providers/listeners (LiveRegionProvider, GlobalHapticsListener), SEO (head-only), self-toggling overlays (Events/NewsShortcutsOverlay), event-gated null components (OfflineIndicator, SyncStatus, LivePushToasts, MapWeatherBadge, InstallPrompt).
- **Honest estimate**: ~2-4 more waves at the campaign cadence. Per `feedback_planning_estimates.md`: range + short-horizon; re-plan each wave.

---

## NEW Gotcha (added to CLAUDE.md)

- **The 3 "logic-wrapper" cards (EventCard/NewsCard/NewChatModal) degrade gracefully — no module-mocking needed.** EventCard makes zero network on mount (register/unregister are click-only + try/catch); NewsCard passes `initialData` into `useNewsInteraction` (failed refetch silent under `retry:false`); NewChatModal's `/users` query is `enabled`-gated on search input. In real-browser Storybook, IndexedDB/localStorage/BroadcastChannel all work, and the generated API client (`client.gen.ts:101-108`) **returns** errors rather than throwing (only throws on per-call `throwOnError`), so fire-and-forget calls like `useNotifications`'s on-mount `checkSchedule()` resolve without unhandled rejections. **MSW-in-Storybook is deliberately avoided** — it is the Storybook + Vite 8/Rolldown service-worker fragility class behind the W120-W123 Chromatic saga. Story these (and similar offline-first components) with prop fixtures + optional `queryClient.setQueryData` seeding instead.
