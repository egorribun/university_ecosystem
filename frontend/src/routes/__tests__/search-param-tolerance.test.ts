import { describe, expect, it } from "vitest"

import { Route as EventsRoute } from "../_auth/events.index"
import { Route as NewsRoute } from "../_auth/news.index"
import { Route as SettingsRoute } from "../_auth/settings"
import { Route as LoginRoute } from "../_public/login"

type SearchValidator = (search: Record<string, unknown>) => Record<string, unknown>

function validatorOf(route: { options: { validateSearch?: unknown } }): SearchValidator {
  const validate = route.options.validateSearch as SearchValidator | undefined
  if (!validate) throw new Error("route search validation is not configured")
  return validate
}

// TanStack Router JSON-parses search values: a typed `?q=12` arrives as 12.
describe("route search validation tolerates JSON-parsed URL values", () => {
  it("keeps a numeric news query as text and drops an unknown sort", () => {
    const validate = validatorOf(NewsRoute)
    expect(validate({ q: 12, cat: 7, sort: "bad" })).toEqual({
      q: "12",
      cat: "7",
      sort: undefined,
    })
    expect(validate({ q: "exam", sort: "popular" })).toMatchObject({ q: "exam", sort: "popular" })
  })

  it("keeps numeric event filters as text", () => {
    expect(validatorOf(EventsRoute)({ q: 12, tab: 3, dr: null })).toMatchObject({
      q: "12",
      tab: "3",
      dr: undefined,
    })
  })

  it("keeps the settings tab and tolerates a numeric Spotify marker", () => {
    expect(validatorOf(SettingsRoute)({ tab: 2, spotify: 12 })).toEqual({ tab: 2, spotify: "12" })
  })

  it("never rejects the login page for a numeric redirect", () => {
    const validate = validatorOf(LoginRoute)
    expect(() => validate({ redirect: 2147483648 })).not.toThrow()
    expect(validate({ redirect: 2147483648 })).toEqual({ redirect: "2147483648" })
    expect(validate({ redirect: "/news" })).toEqual({ redirect: "/news" })
    expect(validate({ redirect: { to: "/x" } })).toEqual({ redirect: undefined })
  })
})
