# Contributing guide

## Frontend translation tests

- Run `pnpm --dir root/frontend test` before opening a PR to execute the Vitest
  suite that now covers translation toggles across dashboard, news, auth, admin,
  and notifications experiences.
- Translation coverage lives in `src/tests/pageTranslations.test.tsx`; add a
  scenario whenever a new page or component surfaces localized copy.
- The shared `renderWithProviders` helper accepts `initialLanguage` (`"en"` or
  `"ru"`) so please exercise both language directions when you extend tests or
  introduce new localized screens.
- Snapshot updates should reflect the finalized English strings; re-run Vitest
  with `--update` if assertions flag stale output.
- Run `npm run manifests:check` from `root/frontend` to confirm generated PWA
  manifests are clean before you push. If it reports drift, regenerate them with
  `npm run generate:manifests` and include the updated files in your commit.

## Backend test coverage

- Keep backend coverage at or above **72%**, matching the current baseline. The
  CI pipeline enforces this with `pytest --cov-fail-under=72`, so changes that
  slip below the threshold will fail the build.
- Before pushing, run `pytest --cov=app --cov-report=term-missing --cov-fail-under=72`
  from the `root/` directory to verify your branch still meets the target and to
  review any uncovered lines.
