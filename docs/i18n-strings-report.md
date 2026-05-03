# i18n strings report

Generated as part of routine maintenance backlog G3. Read-only — do
not act on findings here without re-validating; this is a snapshot
intended to surface candidates for the primary-device wave queue.

## Scope

Scan results across `frontend/src/` looking for two categories of
non-localised text:

1. **`defaultValue:` fallbacks in `t()` calls** — anti-pattern when the
   key already exists in both `en/` and `ru/` JSON locales (per
   CLAUDE.md gotchas across multiple waves). The fallback hides
   missing-key gaps from CI's `i18n:check` gate and lets stale strings
   linger in production.
2. **Hardcoded Russian / English strings inside JSX** — strings that
   reach the user without going through `t()`. Includes JSX text
   nodes, `aria-label="..."` attributes, `placeholder=""`,
   `title=""`, and `alt=""`.

## Methodology

- `grep -rE 'defaultValue\s*:' frontend/src/` for category 1.
- `grep -rE '[А-Я][а-я]{3,}' frontend/src/` for category 2 (Cyrillic).
- Manual sample of high-traffic components for English-string review
  (full grep returns >2000 false positives — names, types, etc).

The numbers below are absolute file counts at scan time; the primary
device should re-run the audit before triaging.

## Category 1: `defaultValue:` fallbacks

**Total occurrences: 98** across **49 files**.

**Top 10 by occurrence count:**

| Count | File |
|------:|------|
| 12 | `frontend/src/components/auth/LoginHero.tsx` |
| 9  | `frontend/src/features/news/components/NewsHeader.tsx` |
| 8  | `frontend/src/pages/Register.tsx` |
| 6  | `frontend/src/components/news/NewsCardContent.tsx` |
| 5  | `frontend/src/components/auth/MfaChallengeView.tsx` |
| 4  | `frontend/src/pages/Schedule.tsx` |
| 4  | `frontend/src/components/ui/WeatherWidget.tsx` |
| 4  | `frontend/src/components/schedule/ScheduleListView.tsx` |
| 4  | `frontend/src/components/schedule/ScheduleDesktopTable.tsx` |
| 4  | `frontend/src/components/news/NewsDetailHeader.tsx` |

(Full list reproducible via `grep -rEc 'defaultValue\\s*:' frontend/src/ | grep -v ':0$' | sort -t: -k2 -n -r`)

### Triage guidance for the primary device

For each occurrence:

1. Check whether the fallback string matches the value of the i18n key
   in `frontend/src/i18n/locales/en/<namespace>.json`.
2. If it matches AND the key exists in `ru/` too — safe to delete the
   fallback. The CI `i18n:check` gate will catch any future divergence.
3. If the fallback differs from the key value — there is a bug
   (either the fallback or the locale file is wrong); fix the
   discrepancy before removing the fallback.
4. If the key is missing in `ru/` — populate the translation first,
   then remove the fallback.

Recommended batch size: ~10 occurrences per commit so each is
trivially reviewable.

## Category 2: Hardcoded Russian strings inside JSX

Sample of confirmed cases (grep matched 5+ char Cyrillic substrings):

- `frontend/src/components/feedback/LoadingState.stories.tsx` — three
  `label: "Загрузка..."` strings inside Storybook stories. **Likely
  acceptable** — Storybook story args are not user-facing in
  production. Verify before removing.
- `frontend/src/components/dashboard/ScheduleCard.tsx` — comment
  string only (not user-facing); skip.
- `frontend/src/components/map/EventMarker.tsx` — a docstring
  example; not runtime-user-facing.

**No production user-facing Russian-text findings in the sample.**

A more exhaustive sweep should run against:

- JSX text children: `<span>...text...</span>`
- `aria-label="..."`, `placeholder="..."`, `title="..."`,
  `alt="..."` attributes
- Toast / snackbar / alert messages

That broader sweep is too noisy to automate cleanly (false positives
from type names, identifiers, etc.) and is best done manually
per-component during regular review.

## Notes

- This report is a one-shot snapshot. **Do not commit fixes from this
  file's recommendations without re-grepping the live tree** — files
  move and counts shift.
- Rapid wave-tracked work on Schedule / News / Events / Activity /
  Map (per `CLAUDE.md` gotchas) means specific files are likely in
  flux. Cross-check `git log -- <file>` before triaging.
- The `i18n:check` CI gate (`vitest run src/tests/translationParity.test.ts`)
  catches missing keys but does NOT catch defaultValue fallbacks — a
  future enhancement could add an ESLint rule (`eslint-plugin-i18next`
  is already in devDependencies) to flag `defaultValue:` arguments and
  promote this report's recommendations to a CI gate.
