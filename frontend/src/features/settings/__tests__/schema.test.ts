import { describe, expect, it } from "vitest"
import * as v from "valibot"

import { SETTINGS_TAB, settingsSearchSchema, type SettingsSearch } from "../schema"

/**
 * Wave 134 SW2 — settingsSearchSchema unit tests.
 *
 * Mirrors the W120 SW5 mapSearchSchema test pattern: number-or-numeric-string
 * coercion, range validation, fallback for invalid values. The tab field
 * must be deep-link-friendly (?tab=2 → Security tab) AND robust against
 * malformed URLs (?tab=999 → fall through to General).
 *
 * Coverage:
 *  - Bare-number (?tab=2) parses to number
 *  - Numeric-string (?tab="2" — TanStack default stringify) parses to number
 *  - Invalid values (NaN, out-of-range, negative) fall back to 0
 *  - SETTINGS_TAB constants are stable and match expected indices
 *  - spotify pass-through preserved (Spotify OAuth callback)
 */

const parse = (input: Record<string, unknown>): SettingsSearch =>
  v.parse(settingsSearchSchema, input)

describe("settingsSearchSchema — tab field", () => {
  it("parses bare number tab=0 (General)", () => {
    expect(parse({ tab: 0 }).tab).toBe(0)
  })

  it("parses bare number tab=2 (Security)", () => {
    expect(parse({ tab: 2 }).tab).toBe(2)
  })

  it("parses numeric-string '2' (TanStack default stringify path)", () => {
    expect(parse({ tab: "2" }).tab).toBe(2)
  })

  it("parses numeric-string '0'", () => {
    expect(parse({ tab: "0" }).tab).toBe(0)
  })

  it("returns 0 (fallback) when tab key is missing entirely", () => {
    // valibot's v.fallback path triggers when the wrapped optional+pipe
    // fails to produce a value for the key. With no `tab` key in input,
    // fallback to 0 fires. Combined with Settings.tsx's `?? 0` default,
    // missing tab consistently lands on General.
    expect(parse({}).tab).toBe(0)
  })

  it("preserves undefined when tab is explicitly undefined (consumer applies '?? 0')", () => {
    // Subtle but documented: when the key is PRESENT with value
    // undefined (e.g. setSearch removes the key by setting it to
    // undefined first), valibot's v.optional accepts undefined directly
    // without invoking the fallback. Settings.tsx applies `search.tab
    // ?? 0` at line 25 so the consumer-side default catches both paths.
    expect(parse({ tab: undefined }).tab).toBeUndefined()
  })

  it("returns 0 (fallback) when tab is non-numeric string", () => {
    // "abc" → parseInt → NaN → check fails → fallback to 0
    expect(parse({ tab: "abc" }).tab).toBe(0)
  })

  it("returns 0 (fallback) when tab is negative", () => {
    expect(parse({ tab: -1 }).tab).toBe(0)
  })

  it("returns 0 (fallback) when tab is out of range (>3)", () => {
    expect(parse({ tab: 4 }).tab).toBe(0)
    expect(parse({ tab: 999 }).tab).toBe(0)
  })

  it("accepts all valid tab indices (0-3)", () => {
    expect(parse({ tab: 0 }).tab).toBe(0)
    expect(parse({ tab: 1 }).tab).toBe(1)
    expect(parse({ tab: 2 }).tab).toBe(2)
    expect(parse({ tab: 3 }).tab).toBe(3)
  })

  it("accepts numeric-string for all valid indices", () => {
    expect(parse({ tab: "0" }).tab).toBe(0)
    expect(parse({ tab: "1" }).tab).toBe(1)
    expect(parse({ tab: "2" }).tab).toBe(2)
    expect(parse({ tab: "3" }).tab).toBe(3)
  })
})

describe("settingsSearchSchema — spotify field", () => {
  it("preserves spotify=connected (Spotify OAuth callback success)", () => {
    expect(parse({ spotify: "connected" }).spotify).toBe("connected")
  })

  it("preserves spotify=error (Spotify OAuth callback failure)", () => {
    expect(parse({ spotify: "error" }).spotify).toBe("error")
  })

  it("returns undefined when spotify is missing", () => {
    expect(parse({}).spotify).toBeUndefined()
  })

  it("does not interact with tab field (orthogonal params)", () => {
    const result = parse({ tab: 2, spotify: "connected" })
    expect(result.tab).toBe(2)
    expect(result.spotify).toBe("connected")
  })
})

describe("SETTINGS_TAB constants", () => {
  it("GENERAL is index 0 (matches Settings.tsx tab=0 mount)", () => {
    expect(SETTINGS_TAB.GENERAL).toBe(0)
  })

  it("ACCOUNT is index 1 (matches Settings.tsx tab=1 mount)", () => {
    expect(SETTINGS_TAB.ACCOUNT).toBe(1)
  })

  it("SECURITY is index 2 — used by routes/_auth/settings.tsx loader for sessions prefetch gate", () => {
    expect(SETTINGS_TAB.SECURITY).toBe(2)
  })

  it("INTEGRATIONS is index 3 (matches Settings.tsx tab=3 mount)", () => {
    expect(SETTINGS_TAB.INTEGRATIONS).toBe(3)
  })

  it("constants are unique (no aliasing)", () => {
    const values = Object.values(SETTINGS_TAB)
    expect(new Set(values).size).toBe(values.length)
  })
})
