# Localization guidelines

## Static shell strings

The static HTML shell (meta tags, offline page, and manifest fallbacks) reuses
content from the main application locales to keep copy consistent.

- Meta descriptions reference the `navigation.brandDescription` string in both
  Russian and English.
- Offline fallback text matches the messaging used for staying in sync with the
  schedule, news, and campus map inside the app.
- Manifest names, descriptions, and shortcut captions mirror the wording of the
  primary navigation sections (Schedule, News, Campus map).

When shell copy changes, update `public/static-shell-i18n.js` for both `ru` and
`en` bundles and adjust the default Russian HTML in `index.html` and
`public/offline.html` to match. Document the source of the new text in this file
so future updates can trace back to the in-app locale keys.
