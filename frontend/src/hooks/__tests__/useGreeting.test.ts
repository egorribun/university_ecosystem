import { renderHook } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

import { getContextualEmoji, getGreetingKey, getSpecialGreeting, useGreeting } from "../useGreeting"

// These pure-helper functions are exported and tested directly —
// no React rendering required (no i18n dependency in the extracted helpers).

describe("getGreetingKey", () => {
  it.each([
    [4, "morning"],
    [7, "morning"],
    [11, "morning"],
    [12, "afternoon"],
    [16, "afternoon"],
    [17, "evening"],
    [23, "evening"],
    [0, "night"],
    [3, "night"],
  ] as const)("returns %s for hour %i", (hour, expected) => {
    expect(getGreetingKey(hour)).toBe(expected)
  })
})

describe("getSpecialGreeting", () => {
  it("returns 'newYear' for January 1st", () => {
    expect(getSpecialGreeting(new Date(2025, 0, 1))).toBe("newYear")
  })

  it("returns 'newYearEve' for December 31st", () => {
    expect(getSpecialGreeting(new Date(2024, 11, 31))).toBe("newYearEve")
  })

  it("returns 'knowledgeDay' for September 1st", () => {
    expect(getSpecialGreeting(new Date(2025, 8, 1))).toBe("knowledgeDay")
  })

  it("returns null for a regular day", () => {
    expect(getSpecialGreeting(new Date(2025, 5, 15))).toBeNull()
  })

  it("returns null for January 2nd (just after New Year)", () => {
    expect(getSpecialGreeting(new Date(2025, 0, 2))).toBeNull()
  })
})

describe("getContextualEmoji", () => {
  // ---------------------------------------------------------------------------
  // Special day overrides time-of-day emoji
  // ---------------------------------------------------------------------------
  it("returns 🎄 on New Year regardless of time and weekday", () => {
    expect(getContextualEmoji("morning", 3, "newYear")).toBe("🎄")
    expect(getContextualEmoji("night", 5, "newYearEve")).toBe("🎄")
  })

  it("returns 🎓 on Knowledge Day", () => {
    expect(getContextualEmoji("morning", 1, "knowledgeDay")).toBe("🎓")
  })

  // ---------------------------------------------------------------------------
  // Time-of-day defaults
  // ---------------------------------------------------------------------------
  it("returns ☀️ for a default morning", () => {
    expect(getContextualEmoji("morning", 2, null)).toBe("☀️")
  })

  it("returns 🌤️ for a default afternoon", () => {
    expect(getContextualEmoji("afternoon", 2, null)).toBe("🌤️")
  })

  it("returns 🌆 for a default evening", () => {
    expect(getContextualEmoji("evening", 2, null)).toBe("🌆")
  })

  it("returns 🌙 for night", () => {
    expect(getContextualEmoji("night", 2, null)).toBe("🌙")
  })

  // ---------------------------------------------------------------------------
  // Friday party override (day 5)
  // ---------------------------------------------------------------------------
  it("returns 🎉 on Friday morning", () => {
    expect(getContextualEmoji("morning", 5, null)).toBe("🎉")
  })

  it("returns 🎉 on Friday afternoon", () => {
    expect(getContextualEmoji("afternoon", 5, null)).toBe("🎉")
  })

  it("returns 🎉 on Friday evening", () => {
    expect(getContextualEmoji("evening", 5, null)).toBe("🎉")
  })

  // ---------------------------------------------------------------------------
  // Monday sleepy emoji
  // ---------------------------------------------------------------------------
  it("returns 😴 on Monday morning", () => {
    expect(getContextualEmoji("morning", 1, null)).toBe("😴")
  })

  it("returns default afternoon emoji on Monday afternoon (no Monday override)", () => {
    expect(getContextualEmoji("afternoon", 1, null)).toBe("🌤️")
  })
})

describe("useGreeting", () => {
  it("uses the special-date translation and keeps a normal date on the time-of-day path", () => {
    const special = renderHook(() => useGreeting(new Date(2025, 0, 1, 9, 0)))
    expect(special.result.current.specialKey).toBe("newYear")
    expect(special.result.current.greeting).toBe("dashboard:greeting.special.newYear")

    const regular = renderHook(() => useGreeting(new Date(2025, 5, 15, 20, 0)))
    expect(regular.result.current.specialKey).toBeNull()
    expect(regular.result.current.greeting).toBe("dashboard:greeting.evening")
  })
})
