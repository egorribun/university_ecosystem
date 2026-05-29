# AUDIT — Wave 195 (Storybook story-coverage campaign, Batch 1 — LEAF-first)

**Date**: 2026-05-29
**Branch**: `egorribun` (PR [#1126](https://github.com/egorribun/university_ecosystem/pull/1126))
**Scope**: User Q0 = **B + F** — "cover absolutely everything left for Storybook stories" + Chromatic review. Phase 1 Explore revealed the true delta (~163 uncovered), so via AskUserQuestion the user chose **phased, LEAF-first** (Q1): W195 ships the largest clean batch of trivial LEAF stories; "everything" becomes a tracked W195→W2xx campaign.
**Wave streak**: 55th consecutive wave with brainstorming + Phase 1 Explore + Phase 3 Review + W141 anti-pattern discipline.

---

## Headline

- **30 NEW LEAF `.stories.tsx`** across 6 family-grouped SWs (Events detail ×5, Events controls ×3, News detail ×6, Navbar ×5, Profile/Activity ×5, UI/Media ×6).
- Story files **78 → 108** (107 discoverable; `find` includes the 1 glob-excluded `routes/_admin/admin.stories.tsx`). Storybook index **374 → 497 entries** (392 stories + **105 autodocs**; the **+30 autodocs** confirm exactly 30 new files).
- **Runtime smoke (real-Chrome Storybook render) surfaced a genuine latent bug** → SW6-fix: `AsyncImage` passed `rootMargin: "12.5rem"` to `IntersectionObserver`, which accepts px/% only → native browsers throw `SyntaxError`. Fixed to `"200px"`. **Zero production-bundle impact** (AsyncImage is unused in prod → tree-shaken; main JS sha byte-identical to W194). 12/12 runtime smoke PASS post-fix.
- **App bundle main JS sha `1bff1fd7…c97` byte-identical × 3 to W194** (≥54-wave LOCAL invariant). server.js → new W195 baseline `f8bd8fab…dbb3` (documented `.stories.tsx` SSR-manifest precedent).
- Vitest **1270 passed / 12 skipped / 0 failed — UNCHANGED** (`.stories.tsx` outside the default vitest project).

---

## Phase 1 Explore (3 agents) — the scope reality

| Metric | Count |
|--------|-------|
| Existing `.stories.tsx` | 77 |
| In-scope components (`src/components/**` + `src/features/**`) | ~238 |
| **Uncovered (delta)** | **~163** |
| ├─ `[LEAF]` story-trivial | ~55 |
| ├─ `[CONTEXT]` needs mocks/providers | ~65 |
| └─ `[SKIP]` orchestrators/providers/route-wrappers | ~17 |

At the established quality bar (~6-10 runtime-verified stories/wave — W194=9, W193=9), "absolutely everything" is a **~6-12 wave campaign, not one wave**. Surfaced to the user; phased LEAF-first chosen.

---

## Per-SW summary (all 1-iter; per-SW substitution rule applied)

| SW | Commit | Stories | Notes |
|----|--------|---------|-------|
| SW1 | `0ad4c0563` | Events detail ×5 | EventCardHero (live/soon/none + no-image) + EventDetail{Hero,Header,Navigation,Skeleton}. `.events-theme` decorator; `pauseAnimationAtEnd` on EventCardHero; EventDetailSkeleton self-contained. |
| SW2 | `890290714` | Events controls ×3 | EventSearchBar + EventQrDialog (open prop) + EventsEmptyState. **Substituted out** `EventFilterPopover` (it's a *hook* `useEventFilterPopover`, not a component) + `EventsShortcutsOverlay`/`OfflineIndicator`/`SyncStatus` (stateful-no-props → render null without a browser event). |
| SW3 | `f61fd7833` | News detail ×6 | NewsCardHero + NewsDetail{Hero,Header,Navigation,Skeleton} + NewsTableOfContents (≥3 `TocEntry`). Mirror of SW1. SW3=6 compensates SW2=3. |
| SW4 | `d758c0bac` | Navbar ×5 | NavbarPill + NavbarLogo + NavbarOverflowMenu + MobileDrawer{Profile,QuickActions}. New `Navbar/` group. **Harness pattern**: a tiny component calls real `useTranslation()` (preview I18nextProvider) to supply the `t: TFunction`/`(key)=>string` prop — no fake-TFunction cast. LazyMotion on m.* components; `User` cast `as unknown as User`. |
| SW5 | `a2bdd64a7` | Profile ×4 + Activity ×1 | ProfileDetails + DetailRow + AchievementsSection + ProfileSkeleton + AnimatedRing (percent/gauge/count, `.activity-theme` + pauseAnimationAtEnd). ProfileSkeleton wraps `<Layout>` (m.*) → LazyMotion; verified context-free. |
| SW6 | `4cd77196e` | UI ×4 + Media ×2 | ContentCard (compound) + SkeletonMorph + StoryCircle + AsyncImage + MediaSlot + SmartImage. SW6=6 → batch total 30. |
| SW6-fix | `ee9ba41e1` | (component) | AsyncImage `rootMargin` `12.5rem`→`200px` (see Headline). |

---

## Verification (wave-close)

- Per-SW: `tsc --noEmit` = 0, `eslint --max-warnings=0` (the 30 files) = 0.
- Full lint gate (`npm run lint`, src + tests) = **0**.
- `vitest run` = **1270 passed / 12 skipped / 0 failed** (unchanged baseline; AsyncImage.test 3/3 after the fix).
- `build-storybook` **SUCCESS** (27s); index 497 entries.
- **Bundle Build × 3**: main JS sha `1bff1fd7403b03e206534340bc89c53a37ce29d1240e923e83b4101c9c813c97` × 3 (size 180,273 b) **= W194 baseline exactly** (filename shifted `B8BD2TjY`→`C6pdnyI2` — Rolldown filename-hash folds in module-graph metadata that unbundled `.stories.tsx` perturb; *content* unchanged per Critical Subtlety #2). server.js 24,024 b sha `f8bd8fab1fbf8494c8c1fea885afcf30d08b7af27af6bdf4e3eeb6190f90dbb3` × 3 (size-identical, content-sha shifted — documented `.stories.tsx` precedent). Re-verified byte-identical AFTER the AsyncImage fix (tree-shaken).
- `npm audit --omit=dev` = **0 vulnerabilities**; i18n parity **18/18** (no new keys); Cargo.lock no drift.
- **Runtime smoke** (`storybook-static` served + real-Chrome over 12 representative stories incl the trickiest — rAF ring, LazyMotion, portal dialog, compound, Layout-wrapping skeleton): **12/12 PASS, 0 real console errors** (image-proxy/picsum network noise filtered).

---

## §Honesty probe

OPEN caveats: **0-2** (unchanged — only the 2 W134 structural-by-design non-goals: W134 §H#2 bundle-delta recording-only + W134 §H#10 /messenger Phase 5 SSR by-design per W161 SW2).

NEW W195 findings (all resolved or honest scope):
1. **AsyncImage `rootMargin: rem` bug** — surfaced + fixed same-wave (SW6-fix). 1 NEW (z). Zero prod impact (tree-shaken). The methodology working as intended.
2. **Story-worthy LEAF set < Agent 1's `[LEAF]` count** — several `[LEAF]`-tagged components are *stateful-no-props* (render `null` without a browser/keyboard event) or *hooks*; substituted out per the per-SW rule. Honest LEAF batch = 30 genuinely prop-driven leaves.
3. **EventQrDialog DarkMode skipped** — portals to `document.body`, outside the decorator's `.dark` scope. Single light variant shipped (correct for a portal modal).
4. **Chromatic (F)** — the post-push CI Chromatic build auto-captures the 30 new baselines (collect-only); the human dashboard spot-check is the user's. No non-deterministic-by-design stories in this batch (animated leaves frozen via `pauseAnimationAtEnd`), unlike W194's MfaChallengeView/ActivityHeatmap.

W141 anti-pattern compliance: #1 (STRICT 1-iter) — every SW landed in 1 iter; SW6's AsyncImage fix is a within-SW6 SAME-mechanism sub-fix (W138 L#1: make the story render), not a pivot. #3 (verify-before-write) — Phase 1 + Phase 3 reads caught hooks-not-components, stateful-no-props leaves, `TocEntry`/`NavigationItem`/`AchievementItem` shapes, `t: TFunction` props, and the `Layout`/`PageFadeIn` context-free check before writing. #4 (closures after evidence) — bundle/render/coverage claims attributed only after Build × 3 + 12/12 smoke + index counts. #15 (ARCHIVED) — all commits fired the husky pre-commit chain cleanly.

---

## Campaign arc — what remains after W195 (tracked)

- **W196 — LEAF batch 2** (~22 remaining clean leaves: schedule DayColumn/ExportDropdown, map MapHeader/MapCategoryFilter/MapWeatherBadge, mfa OtpEntry/TotpQrDisplay, dashboard DateBullet/DashboardSectionSkeleton, activity CardShell/TrendChip/ActivityTimelineItem/ActivityExportButton, ui Spotlight/data-table headers, misc) → completes the LEAF tier.
- **W197–W2xx — CONTEXT tier** (~65), grouped: cards/dialogs (EventCard/NewsCard + edit/create), navbar-actions/mobile-menu, messenger ChatArea/MessengerSidebar/ProfileModal/NewChatModal, **admin ×4** (query-cache-seeded), map panels, schedule dialogs/tables, news comments/detail-body, profile editor/now-playing.
- **SKIP by design (~17)** — orchestrators (`*Feature.tsx`, MapFeature), providers/boundaries, route wrappers.
- **Marginal — decide per-wave**: motion wrappers + tiny composed sub-components (better as variants in parent stories).
- **Honest estimate**: ~6-9 more waves to truly cover everything (CONTEXT slower at ~2-3/SW). Anchors: Schedule 14, Map 23, Events 6, Activity 4, News 6, Dashboard 10.

---

## NEW Gotcha (added to CLAUDE.md)

- **Storybook story-worthiness ≠ "few props"** — the real axis is *renders meaningful UI from args alone*. Components that are *hooks* (`useEventFilterPopover`), *stateful-no-props* (OfflineIndicator/SyncStatus/Shortcut overlays render `null` until a browser/keyboard event), or *portal-to-body* (Dialog dark-mode escapes the decorator `.dark` scope) are NOT clean LEAF material — substitute, don't fight (per-SW rule, W138 L#1). And `IntersectionObserver` `rootMargin` accepts **px/% only, NOT rem** — native browsers throw; jsdom IO mocks are lenient so unit tests miss it; a real-browser Storybook render is the gate that catches it.
