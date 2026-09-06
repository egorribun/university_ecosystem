import { describe, expect, it } from "vitest"
import {
  createMobileNavItems,
  isNavSectionActive,
  MOBILE_NAV_TRANSLATION_NAMESPACE,
  mobileNavAriaCurrent,
  mobileNavAriaHidden,
  navScrollBehavior,
  normalizeNavPath,
  sameNavPath,
  shouldHideForVirtualKeyboard,
} from "../MobileBottomNav"

describe("MobileBottomNav pure navigation contracts", () => {
  it.each([
    ["/dashboard", "/dashboard"],
    ["/dashboard/", "/dashboard"],
    ["/dashboard////", "/dashboard"],
    ["/", "/"],
    ["////", "/"],
  ])("normalizes %j to %j", (input, expected) => {
    expect(normalizeNavPath(input)).toBe(expected)
  })

  it("compares paths without allowing section prefix collisions", () => {
    expect(sameNavPath("/news////", "/news")).toBe(true)
    expect(sameNavPath("/newsroom", "/news")).toBe(false)
    expect(isNavSectionActive("/news/story", "/news")).toBe(true)
    expect(isNavSectionActive("/newsroom", "/news")).toBe(false)
    expect(isNavSectionActive("/", "/")).toBe(true)
    expect(isNavSectionActive("/anything", "/")).toBe(false)
    expect(isNavSectionActive("//anything", "/")).toBe(false)
  })

  it("creates the complete translated navigation contract", () => {
    const translate = (key: string) => `translated:${key}`
    const items = createMobileNavItems(translate)

    expect(items).toHaveLength(5)
    expect(items.map(({ to, label }) => ({ to, label }))).toEqual([
      { to: "/dashboard", label: "translated:navigation:menu.dashboard" },
      { to: "/news", label: "translated:navigation:menu.news" },
      { to: "/events", label: "translated:navigation:menu.events" },
      { to: "/schedule", label: "translated:navigation:menu.schedule" },
      { to: "/profile", label: "translated:navigation:menu.profile" },
    ])
    expect(items.every(({ icon }) => icon != null)).toBe(true)
    expect(MOBILE_NAV_TRANSLATION_NAMESPACE).toBe("navigation")
    expect(mobileNavAriaCurrent(true)).toBe("page")
    expect(mobileNavAriaCurrent(false)).toBeUndefined()
    expect(mobileNavAriaHidden(true)).toBe(true)
    expect(mobileNavAriaHidden(false)).toBeUndefined()
  })

  it("selects a deterministic scroll behavior", () => {
    expect(navScrollBehavior(false)).toBe("smooth")
    expect(navScrollBehavior(true)).toBe("auto")
  })

  it("detects keyboard occlusion only for editable default-scale focus", () => {
    const input = document.createElement("input")
    const textarea = document.createElement("textarea")
    const editor = document.createElement("div")
    Object.defineProperty(editor, "isContentEditable", { configurable: true, value: true })
    const button = document.createElement("button")

    expect(shouldHideForVirtualKeyboard(input, 800, 649)).toBe(true)
    expect(shouldHideForVirtualKeyboard(textarea, 800, 649, undefined)).toBe(true)
    expect(shouldHideForVirtualKeyboard(editor, 800, 649, 1)).toBe(true)
    expect(shouldHideForVirtualKeyboard(button, 800, 649, 1)).toBe(false)
    expect(shouldHideForVirtualKeyboard(input, 800, 650, 1)).toBe(false)
    expect(shouldHideForVirtualKeyboard(input, 800, 649, 0.99)).toBe(false)
    expect(shouldHideForVirtualKeyboard(input, 800, 500, 2)).toBe(false)

    const absSpy = vi.spyOn(Math, "abs").mockReturnValue(0.01)
    try {
      expect(shouldHideForVirtualKeyboard(input, 800, 649, 1.02)).toBe(false)
    } finally {
      absSpy.mockRestore()
    }
  })
})
