import { describe, expect, it, vi } from "vitest"

import {
  buildVCardString,
  calculateAvatarSize,
  calculateHeroLayout,
  calculateStatusIndicator,
  formatDuration,
  parseAchievements,
} from "@/components/profile/profileUtils"

describe("profileUtils closure paths", () => {
  it("parses null, empty, and delimited achievement records", () => {
    expect(parseAchievements(null)).toEqual([])
    expect(parseAchievements("  , ;\n  ")).toEqual([])
    expect(parseAchievements("Dean's list | GUU | 2026 | https://example.test\nMentor")).toEqual([
      {
        key: "Dean's list | GUU | 2026 | https://example.test-0",
        name: "Dean's list",
        issuer: "GUU",
        date: "2026",
        url: "https://example.test",
      },
      { key: "Mentor-1", name: "Mentor", issuer: undefined, date: undefined, url: undefined },
    ])
  })

  it("builds vCards with optional contact fields", () => {
    const full = buildVCardString({
      full_name: "Ada Lovelace",
      email: "ada@example.test",
      institute: "GUU",
      department: "Computer Science",
      position: "Researcher",
      status: "Student",
    })
    expect(full).toContain("FN:Ada Lovelace")
    expect(full).toContain("EMAIL:ada@example.test")
    expect(full).toContain("ORG:GUU")
    expect(full).toContain("TITLE:Researcher")
    expect(full).toContain(`URL:${window.location.href}`)
    expect(full).toMatch(/^BEGIN:VCARD\r\nVERSION:4\.0/)
    expect(full.endsWith("END:VCARD")).toBe(true)

    expect(buildVCardString({ full_name: null, email: null })).toBe(
      `BEGIN:VCARD\r\nVERSION:4.0\r\nFN:\r\nURL:${window.location.href}\r\nEND:VCARD`
    )
  })

  it("uses department/status fallbacks and supports server-side vCards", () => {
    const partial = buildVCardString({
      full_name: "Server User",
      institute: "",
      department: "Mathematics",
      position: "",
      status: "Student",
    })
    expect(partial).toContain("ORG:Mathematics")
    expect(partial).toContain("TITLE:Student")

    vi.stubGlobal("window", undefined)
    try {
      expect(buildVCardString({ full_name: "SSR User" })).toBe(
        "BEGIN:VCARD\r\nVERSION:4.0\r\nFN:SSR User\r\nEND:VCARD"
      )
    } finally {
      vi.unstubAllGlobals()
    }
  })

  it("formats duration and layout values at lower and responsive bounds", () => {
    expect(formatDuration(null)).toBe("0:00")
    expect(formatDuration(-1)).toBe("0:00")
    expect(formatDuration(61_000)).toBe("1:01")
    expect(formatDuration(3_661_000)).toBe("61:01")

    expect(calculateAvatarSize(true, true)).toBe(120)
    expect(calculateAvatarSize(false, true)).toBe(188)
    expect(calculateAvatarSize(false, false)).toBe(168)

    expect(calculateHeroLayout(120, true)).toEqual({
      avatarFloat: 66,
      heroPaddingBottom: "54px",
      heroTextPaddingTop: "172px",
    })
    expect(calculateHeroLayout(40, false)).toEqual({
      avatarFloat: 22,
      heroPaddingBottom: "28px",
      heroTextPaddingTop: "104px",
    })
    expect(calculateStatusIndicator(40)).toEqual({ size: 12, offset: 6 })
    expect(calculateStatusIndicator(200)).toEqual({ size: 32, offset: 16 })
  })
})
