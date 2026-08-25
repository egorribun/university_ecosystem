import * as v from "valibot"

/**
 * Settings route search-param schema — Wave 134 SW2 URL-sync.
 *
 * Two URL params are recognised:
 *
 *   tab — active tab index (0 = General, 1 = Profile, 2 = Security,
 *         3 = Notifications, 4 = Sessions, 5 = Integrations). Pre-W134 tab
 *         state was useState-only; SW2 elevates it to a deep-linkable URL param so notification emails
 *         (e.g. "MFA enrolment expiring → /settings?tab=2") can land on
 *         the correct tab. Absent or invalid values fall back to 0.
 *   spotify — Spotify OAuth callback status ("connected" | "error").
 *         Pre-existing param consumed by Settings.tsx:50-75 to surface a
 *         snackbar after the OAuth redirect-back; documented here so
 *         validateSearch doesn't strip it.
 *
 * `v.fallback(..., 0)` for tab silently coerces invalid values (out of
 * range, malformed) to the General tab so a bad URL doesn't crash the
 * route. Mirrors the W120 SW5 mapSearchSchema fallback pattern.
 *
 * Number coercion: TanStack Router's default `stringifySearch` JSON-
 * quotes string values that LOOK like numbers (`?tab="2"` URL-encodes
 * to `?tab=%222%22`); we serialise tab as an actual number so URLs stay
 * clean (`?tab=2`). The schema's union accepts BOTH bare-number (from
 * setSearch with a number) AND numeric-string (from manual URL or
 * legacy stringifier path).
 */

const tabField = v.fallback(
  v.optional(
    v.pipe(
      v.union([
        v.number(),
        v.pipe(
          v.string(),
          v.transform((s) => Number.parseInt(s, 10))
        ),
      ]),
      v.number(),
      // Reject NaN (parseInt returns NaN for non-numeric strings).
      v.check((n) => Number.isFinite(n), "tab must be finite"),
      v.minValue(0),
      v.maxValue(5)
    )
  ),
  // Fallback for invalid input → General tab (index 0).
  0
)

export const settingsSearchSchema = v.object({
  tab: tabField,
  spotify: v.optional(v.string()),
})

export type SettingsSearch = v.InferOutput<typeof settingsSearchSchema>

/**
 * Stable mapping of tab index → semantic name. Used by tests and the
 * route loader to make conditional prefetch decisions readable.
 */
export const SETTINGS_TAB = {
  GENERAL: 0,
  ACCOUNT: 1,
  SECURITY: 2,
  NOTIFICATIONS: 3,
  SESSIONS: 4,
  INTEGRATIONS: 5,
} as const

export type SettingsTabIndex = (typeof SETTINGS_TAB)[keyof typeof SETTINGS_TAB]
