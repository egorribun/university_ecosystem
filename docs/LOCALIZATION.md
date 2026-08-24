# Localization guidelines

## Static shell strings

The static HTML shell (meta tags, offline page, and manifest fallbacks) reuses
content from the main application locales to keep copy consistent.

- Meta descriptions reference the `navigation.brandDescription` string in both
  Russian and English.
- Offline fallback text matches the messaging used for staying in sync with the
  schedule, news, and campus map inside the app.
- Manifest names, descriptions, and shortcut captions mirror the wording of the
  primary navigation sections (Schedule, News, Campus map). Edit
  `frontend/public/manifest.source.json` to update these strings so the
  generator can rebuild `manifest*.webmanifest` consistently.

When shell copy changes, update `frontend/public/static-shell-i18n.js` for both
`ru` and `en` bundles and adjust the default Russian HTML in `frontend/index.html`
and `frontend/public/offline.html` to match. Document the source of the new text
in this file so future updates can trace back to the in-app locale keys.

## Dashboard stories

The dashboard "stories" carousel now exposes additional localized strings in
`dashboard.json`:

- `stories.subheading` — short tagline under the block heading.
- `stories.emptyDescription` — supporting text for the empty state.
- `stories.viewer.hints.auto` / `keyboard` / `swipe` / `tap` — navigation tips
  shown inside the viewer dialog.
- `stories.viewer.aria.instructions` — screen reader summary announced when the
  viewer opens.

Whenever you adjust these phrases, update both `en` and `ru` locales so the
dashboard and accessibility hints stay in sync across languages.

## Dashboard weather

The dashboard weather chip uses new entries under `dashboard.weather` for both
languages:

- `label` — short name for the widget, reused in aria-labels.
- `tooltip` — compact summary shown on hover/focus (`Weather · Clear sky · +21°`).
- `conditions.*` — human-friendly descriptions for each weather code.
- `aria.status` and `aria.statusNoTemp` — announcements for screen readers.

Ensure any changes land in both locale files so the tooltip and aria-labels do
not fall back to raw translation keys.

## Campus map fallback

Privacy settings, reduced-motion preferences, or offline conditions can disable
the MapLibre/OpenFreeMap map on the campus page. The replacement component relies on
new strings in `system.json`:

- `map.fallback.title` and `description.*` describe why the static view is
  shown (load error vs. privacy preference).
- `map.fallback.instructions`, `offlineNotice`, and `listLabel` provide the
  keyboard/ARIA copy for the structured campus list.
- `map.fallback.retry` labels the retry button, while `tags.*` and
  `points.*.(title|description|address)` localize the individual campus tiles.

Update both locales when these values change so the fallback remains accessible
and consistent with the interactive map. The MapLibre/OpenFreeMap chunks are
lazy and intentionally network-only rather than install-time precached; a cold
offline navigation therefore has only the generic shell fallback, while the
map fallback remains usable offline once the map route has already loaded.

## Documentation localization workflow

- Keep the Russian and English deployment guides (`docs/DEPLOY.md` and
  `docs/DEPLOY.en.md`) in sync.
- When updating one language, replicate the change in the other file within the
  same pull request and adjust the cross-links at the top if new sections are
  introduced.
- If a future contribution can only supply one language, clearly mark the
  missing translation in both files and open a follow-up issue to track the
  remaining work.
