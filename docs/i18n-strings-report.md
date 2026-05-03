# i18n strings report

Generated as part of routine maintenance backlog G3. Read-only — do
not act on findings here without re-validating; this is a snapshot
intended to surface candidates for the primary-device wave queue.

**Last refresh: 2026-05-03** (replaces the 2026-05-03 05:14 first
pass — counts shifted after the G1 batches landed and the second
sweep surfaced a 47-instance 2-arg `t()` pattern that the first
pass missed).

## Scope

Scan results across `frontend/src/` looking for non-localised text
that may reach the user without going through `t()`:

1. **`defaultValue:` fallbacks in `t()` calls** — anti-pattern when
   the underlying key already exists in both `en/` and `ru/`
   locale JSON files. Hides drift from CI's `i18n:check` gate and
   lets stale strings linger if a translator edits the JSON
   without dropping the legacy fallback.
2. **2-argument `t("ns:key", "Fallback")` form** — same semantics
   as `defaultValue:` but written as a positional second argument.
   Easy to miss with a `defaultValue:`-only regex. **Far more
   common than category 1, and far more likely to mask a missing
   translation.**
3. **Hardcoded Russian / English strings inside JSX** — strings
   that reach the user without going through `t()` at all.
   Includes JSX text nodes, `aria-label`, `placeholder`, `title`,
   `alt` and snackbar/alert messages.

## Methodology

- Cyrillic scan: Python `re.compile(r'[Ѐ-ӿ]')` (full Cyrillic
  block + supplement). Walked `frontend/src/**/*.{ts,tsx}`
  excluding `__tests__/`, `*.test.*`, `*.stories.*`,
  `i18n/locales/`.
- `defaultValue:` scan: line-anchored regex `defaultValue\s*:`
  over the same path set.
- 2-argument `t()` scan: regex
  `(?:^|[^a-zA-Z0-9_\.])t\(\s*"([^"]+)"\s*,\s*"([^"]+)"\s*\)`,
  cross-referenced against EN+RU JSON. The regex is anchored on
  a non-identifier prefix character to avoid false positives like
  `url.searchParams.set("foo", "bar")` which Python's plain `t(`
  match would otherwise pick up.
- Hardcoded JSX attribute strings: regex on `aria-label`,
  `placeholder`, `title`, `alt`, `aria-roledescription` matching
  multi-word values starting with an uppercase letter.

The numbers below are absolute counts at scan time. The primary
device should re-run the methodology before triaging — files move
and counts shift between waves.

## Category 1: `defaultValue:` fallbacks

**Total occurrences: 56** across **24 files**
(down from 98 / 49 files at first scan — 35 removals landed under
commits `f3b3d49d0` + `99640089e`, scoped strictly to keys
already present in EN+RU).

**Top 10 by remaining count:**

| Count | File                                                         |
| ----: | ------------------------------------------------------------ |
|    12 | `frontend/src/components/auth/LoginHero.tsx`                 |
|     7 | `frontend/src/pages/Register.tsx`                            |
|     4 | `frontend/src/components/auth/MfaChallengeView.tsx`          |
|     3 | `frontend/src/components/schedule/ScheduleListView.tsx`      |
|     3 | `frontend/src/components/schedule/ScheduleMiniCalendar.tsx`  |
|     3 | `frontend/src/components/ui/WeatherWidget.tsx`               |
|     3 | `frontend/src/hooks/useScheduleTime.ts`                      |
|     2 | `frontend/src/components/feedback/SyncStatus.tsx`            |
|     2 | `frontend/src/components/schedule/ScheduleDesktopTable.tsx`  |
|     2 | `frontend/src/components/schedule/ScheduleSettingsPanel.tsx` |

The residual 56 are roughly:

- **Locale gap** (most common). The English string is rendered for
  RU users today because the key is missing in `ru/` (sometimes
  also missing in `en/`). Examples: most of `LoginHero.tsx`, all
  of `Register.tsx` (password-strength scale + namePlaceholder +
  inviteOptional), `MfaChallengeView.tsx`'s `mfa.or` and
  `actions.trustDevice`, all six `common:prev/today/next/clear/
sync.online/time.minuteShort`, `schedule:toolbar.today` /
  `select.prompt` / `time.{hours,minutes}Short` /
  `parity.label` / `toolbar.weekNavLabel` / `table.empty{,Cell}`.
- **Dynamic `defaultValue:`** (legitimate). The key resolves at
  runtime (e.g. weather code → translation key) and the
  `defaultValue` is a sensible derived label. Examples:
  `WeatherWidget.tsx:40,56,63`. Keep these.
- **Intentional override** (rare). The literal differs from the
  underlying key value — removing the fallback would change the
  rendered text. Single case so far:
  `NewsDetailHeader.tsx:138` aria-label says `"Bookmark"` but
  `news:actions.bookmark` resolves to `"Save"`. Decide which is
  canonical.

**Fix path** for the locale-gap class: add the missing key to
BOTH `en/` and `ru/` in the same commit, then drop the
`defaultValue`. Best done in a single commit per namespace so the
locale diff is reviewable.

## Category 2: 2-argument `t("ns:key", "Fallback")` form

**Total occurrences: 47** across 17 files.
**26 of those calls reference keys that are missing in BOTH `en/`
and `ru/`** — the English fallback is what users see on the
production RU build. This is a real translation gap, not just a
code-quality concern.

### 2a. Keys missing in BOTH locales (RU users see English fallback)

| File:Line                                       | Key                            | English fallback shipping to RU users                    |
| ----------------------------------------------- | ------------------------------ | -------------------------------------------------------- |
| `components/error/PageErrorBoundary.tsx:66`     | `system:pageError.title`       | `"Page Error"`                                           |
| `components/error/PageErrorBoundary.tsx:69`     | `system:pageError.description` | `"Something went wrong loading this page."`              |
| `components/error/PageErrorBoundary.tsx:116`    | `system:pageError.retry`       | `"Try Again"`                                            |
| `components/error/PageErrorBoundary.tsx:123`    | `system:pageError.home`        | `"Go Home"`                                              |
| `components/feedback/NotificationsBell.tsx:175` | `notifications:new`            | `"New"`                                                  |
| `components/messenger/ChatArea.tsx:271`         | `messenger:selectChatDesc`     | `"Connect with anyone across the university ecosystem."` |
| `components/messenger/NewChatModal.tsx:101`     | `messenger:noUsersFound`       | `"No users found matching your search"`                  |
| `components/messenger/ProfileModal.tsx:39`      | `messenger:profile`            | `"Profile"`                                              |
| `components/messenger/ProfileModal.tsx:56`      | `messenger:loadingProfile`     | `"Loading profile..."`                                   |
| `components/messenger/ProfileModal.tsx:88`      | `messenger:status`             | `"Status"`                                               |
| `components/messenger/ProfileModal.tsx:94`      | `common:active`                | `"Active"`                                               |
| `components/messenger/ProfileModal.tsx:99`      | `common:inactive`              | `"Inactive"`                                             |
| `components/messenger/ProfileModal.tsx:112`     | `messenger:avatar`             | `"Avatar"`                                               |
| `components/messenger/ProfileModal.tsx:115`     | `messenger:viewAvatar`         | `"Open full size"`                                       |
| `hooks/features/useMessengerController.ts:309`  | `messenger:clearChatTitle`     | `"Clear Chat"`                                           |
| `hooks/features/useMessengerController.ts:310`  | `messenger:confirmClear`       | `"Clear chat history for everyone?"`                     |
| `hooks/features/useMessengerController.ts:312`  | `common:clear`                 | `"Clear"`                                                |
| `hooks/features/useMessengerController.ts:313`  | `common:cancel`                | `"Cancel"`                                               |
| `hooks/features/useMessengerController.ts:325`  | `messenger:deleteChatTitle`    | `"Delete Chat"`                                          |
| `hooks/features/useMessengerController.ts:326`  | `messenger:confirmDelete`      | `"Delete this chat for all participants?"`               |
| `hooks/features/useMessengerController.ts:328`  | `common:delete`                | `"Delete"`                                               |
| `hooks/features/useMessengerController.ts:329`  | `common:cancel`                | `"Cancel"`                                               |
| `hooks/features/useMessengerController.ts:347`  | `messenger:profileLoadError`   | `"Unable to load participant profile"`                   |
| `pages/Dashboard.tsx:287`                       | `dashboard:pageTitle`          | `"Dashboard"`                                            |
| `pages/Messenger.tsx:117`                       | `common:confirm`               | `"Confirm"`                                              |
| `pages/Messenger.tsx:118`                       | `common:cancel`                | `"Cancel"`                                               |

> Note on `common:cancel/confirm/clear/delete`: `common.json` has
> these only under `buttons.{cancel,confirm,clear,delete}`; the
> top-level form the messenger code uses doesn't exist. Likely
> simplest fix is to alias them at the top-level OR change the
> call sites to `t("common:buttons.cancel")` etc. Either is a
> single-commit fix.

### 2b. Keys present in both locales — code-quality cleanup only

The remaining 21 calls have the underlying key in EN+RU and the
2-arg fallback is unreachable at runtime. Sample:
`messenger:online`, `messenger:offline`, `messenger:title`,
`messenger:newChat`, `messenger:search`, `messenger:typeMessage`,
`profile:pageTitle`, `featureFlags.*` (admin namespace),
`offlineIndicator.{online,offline}` (system namespace),
`common:noResults`. **Fix path**: drop the 2nd argument; no locale
edit needed.

## Category 3: Hardcoded Russian strings

Cyrillic scan against `**/*.{ts,tsx}` (excluding tests, locale
files, Storybook stories) returned **4 hits in `.tsx`** and ~30 in
`.ts`. After manual classification:

- `.tsx` — all 4 are inside `// …` or `/* … */` comments. Zero
  user-facing.
- `.ts` —
  - `data/campusBuildings.ts` — building IDs (`ГУК`, `ПА`, `ЛК`,
    `А`, `Б`, `СК`, `О2`, `О6`, `ЦИТ`), structure references
    (`стр. 8`, `стр. 5`), in-comment building names. These are
    domain identifiers, not UI copy; the localised display names
    live in `i18n/locales/{en,ru}/map.json`.
  - `data/campusPOI.ts` — comments with Russian shop-cluster
    names for context.
  - `features/{events,news}/categories.ts` — regex patterns that
    classify event/news titles by language-mixed keyword match.
    Internal classification, not rendered.
  - `hooks/useNextLesson.ts`, `hooks/useScheduleTime.ts` — JSDoc
    examples (e.g. `e.g. "ГУК-305"`, `"7ч 22м"`).
  - `utils/buildingIcons.ts`, `utils/roomStatus.ts`,
    `utils/stripMaplibreMarkerChrome.ts` — JSDoc examples.
  - `tests/mocks/handlers.ts` — MSW mock fixtures, not
    user-facing in production.

**One genuine case** worth flagging:

- `frontend/src/push/notification-helpers.ts:7-8`

  ```
  defaultTitle: "Новое уведомление",
  defaultBody: "У вас есть новое уведомление.",
  ```

  Used as fallback for push payloads that don't supply
  `title`/`body`. Service-worker context — `i18next` is not
  guaranteed to be available there. The current solution is to
  hardcode Russian (the dominant locale). **Fix path** is unclear:
  the SW would need either (a) a locale-aware fallback derived
  from `navigator.language`, (b) a postMessage from the page to
  pre-seed strings, or (c) duplicating both EN+RU into the SW
  bundle. Best left for the primary device to decide.

- `frontend/src/utils/bootstrapFallback.ts:21-26` — bilingual
  `EN / RU` text shown when the React bundle itself fails to load
  (i18n not yet initialised). **Intentionally non-i18n.**

## Category 4: Hardcoded English aria-labels

7 confirmed instances of `aria-label="..."` with a multi-word
English literal where the surrounding component uses `t()` for
visible text:

| File:Line                                     | aria-label            |
| --------------------------------------------- | --------------------- |
| `components/messenger/ChatWindow.tsx:48`      | `"Chat messages"`     |
| `components/messenger/MessageInput.tsx:122`   | `"Remove"`            |
| `components/messenger/MessageInput.tsx:143`   | `"Attachments"`       |
| `components/navbar/NavbarOverflowMenu.tsx:82` | `"More navigation"`   |
| `components/navbar/UserMenu.tsx:55`           | `"Loading user menu"` |
| `components/ui/ProfileCardSkeleton.tsx:22`    | `"Loading profile"`   |
| `components/ui/ScheduleCardSkeleton.tsx:19`   | `"Loading schedule"`  |

The chat / messenger surface and the loading skeletons announce
themselves in English to RU AT users. Not visible UI, but it
violates WCAG 3.1.2 Language of Parts when set on an
`<html lang="ru">` document.

**Fix path:** add `messenger:aria.*`, `navigation:overflowMenu`,
`common:aria.loadingProfile/Schedule/UserMenu` keys; replace the
literals with `t()` calls. Each change is small and atomic.

## Headline summary

- **Real translation gaps shipping today: ~33** — 26 from
  Category 2a + 7 from Category 4. RU users see English text in
  the messenger surface, page-level error boundary, dashboard
  page title, common confirm/cancel dialogs, and AT-only
  loading-state announcements.
- **Code-quality-only items: ~77** — 56 `defaultValue:` residuals
  - 21 reachable 2-arg fallbacks. Removing them tightens CI gates
    but doesn't change user experience.

The Category 2a list is the most actionable: roughly 26 missing
keys, each one trivially translated. Combined with the 7
hardcoded aria-labels, that's ~33 small locale-file additions
that would close the entire visible / AT-facing English-leak
surface uncovered by this scan.

## Notes / caveats

- This report is a one-shot snapshot. Do **not** commit fixes
  without re-running the methodology — files move between waves
  and counts drift.
- Wave-tracked work on Schedule / News / Events / Activity / Map
  (per `CLAUDE.md` gotchas) means specific files in those areas
  are likely in flux. Cross-check `git log -- <file>` before
  triaging anything in those directories.
- The `i18n:check` CI gate
  (`vitest run src/tests/translationParity.test.ts`) catches
  missing keys but does NOT catch `defaultValue:` fallbacks or
  2-arg fallbacks. A future enhancement could add an ESLint rule
  (`eslint-plugin-i18next` is already in `devDependencies`) to
  flag both forms and promote this report's recommendations to
  a CI gate.
- Methodology regenerates totals deterministically; treat the
  numbers as advisory, not authoritative.
