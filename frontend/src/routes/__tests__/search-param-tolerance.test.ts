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

  it("drops unsupported event choices while preserving free-text filters", () => {
    expect(
      validatorOf(EventsRoute)({
        tab: "upcoming",
        q: 12,
        dr: "2026-07-13",
        loc: false,
        sort: "date",
        cat: "study",
      })
    ).toEqual({
      tab: undefined,
      q: "12",
      dr: undefined,
      loc: "false",
      sort: undefined,
      cat: undefined,
    })
  })

  it("drops non-string event choices without throwing", () => {
    expect(
      validatorOf(EventsRoute)({ tab: 3, dr: null, sort: ["newest"], cat: { id: "lecture" } })
    ).toEqual({ tab: undefined, dr: undefined, sort: undefined, cat: undefined })
  })

  it("uses blank event choices as defaults while preserving blank free text", () => {
    expect(
      validatorOf(EventsRoute)({ tab: "", q: "", dr: "", loc: "", sort: "", cat: "" })
    ).toEqual({
      tab: undefined,
      q: "",
      dr: "",
      loc: "",
      sort: undefined,
      cat: undefined,
    })
  })

  it.each([
    { tab: "active", dr: "", sort: "newest", cat: "all" },
    { tab: "archive", dr: "today", sort: "popular", cat: "lecture" },
    { tab: "my", dr: "week", sort: "upcoming", cat: "sport" },
    { dr: "month", cat: "other" },
    { cat: "seminar" },
    { cat: "conference" },
    { cat: "workshop" },
    { cat: "social" },
  ])("preserves supported event choices in shared links: %j", (search) => {
    expect(validatorOf(EventsRoute)(search)).toEqual(search)
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
