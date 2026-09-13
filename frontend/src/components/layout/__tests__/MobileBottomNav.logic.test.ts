import { describe, expect, it, vi } from "vitest"
import {
  createMobileKeyboardStore,
  createMobileNavItems,
  isNavSectionActive,
  MOBILE_NAV_TRANSLATION_NAMESPACE,
  mobileNavAriaCurrent,
  mobileNavAriaHidden,
  navScrollBehavior,
  removeMobileKeyboardListeners,
  normalizeNavPath,
  sameNavPath,
  shouldHideForVirtualKeyboard,
} from "../MobileBottomNav"

describe("MobileBottomNav pure navigation contracts", () => {
  it("detaches both viewport listeners and tolerates an absent viewport", () => {
    const removeEventListener = vi.fn()
    const listener = vi.fn()

    removeMobileKeyboardListeners({ removeEventListener }, listener)
    expect(removeEventListener).toHaveBeenNthCalledWith(1, "resize", listener)
    expect(removeEventListener).toHaveBeenNthCalledWith(2, "scroll", listener)
    expect(() => removeMobileKeyboardListeners(null, listener)).not.toThrow()
  })

  it("shares viewport resources until final unsubscribe and ignores a stale callback", () => {
    const originalViewport = Object.getOwnPropertyDescriptor(window, "visualViewport")
    const listeners = new Map<string, EventListener>()
    const visualViewport = {
      height: window.innerHeight,
      scale: 1,
      addEventListener: vi.fn((type: string, listener: EventListener) => {
        listeners.set(type, listener)
      }),
      removeEventListener: vi.fn(),
    }
    Object.defineProperty(window, "visualViewport", {
      configurable: true,
      value: visualViewport,
    })

    try {
      const store = createMobileKeyboardStore()
      const listener = vi.fn()
      const unsubscribeFirst = store.subscribe(listener)
      const unsubscribeSecond = store.subscribe(vi.fn())

      expect(store.getServerSnapshot()).toBe(false)
      expect(visualViewport.addEventListener).toHaveBeenCalledTimes(2)

      listeners.get("resize")?.(new Event("resize"))
      expect(listener).not.toHaveBeenCalled()

      unsubscribeFirst()
      expect(visualViewport.removeEventListener).not.toHaveBeenCalled()

      const staleResize = listeners.get("resize")
      unsubscribeSecond()
      expect(visualViewport.removeEventListener).toHaveBeenCalledTimes(2)
      expect(store.getSnapshot()).toBe(false)
      expect(() => staleResize?.(new Event("resize"))).not.toThrow()
      expect(store.getSnapshot()).toBe(false)
      expect(() => unsubscribeSecond()).not.toThrow()

      const unsubscribeRestarted = store.subscribe(vi.fn())
      expect(visualViewport.addEventListener).toHaveBeenCalledTimes(4)
      unsubscribeRestarted()
      expect(visualViewport.removeEventListener).toHaveBeenCalledTimes(4)
    } finally {
      if (originalViewport) {
        Object.defineProperty(window, "visualViewport", originalViewport)
      } else {
        Reflect.deleteProperty(window, "visualViewport")
      }
    }
  })

  it("keeps a server-safe snapshot when Visual Viewport is unavailable", () => {
    const originalViewport = Object.getOwnPropertyDescriptor(window, "visualViewport")
    Reflect.deleteProperty(window, "visualViewport")

    try {
      const store = createMobileKeyboardStore()
      const unsubscribe = store.subscribe(vi.fn())

      expect(store.getSnapshot()).toBe(false)
      expect(store.getServerSnapshot()).toBe(false)
      unsubscribe()
    } finally {
      if (originalViewport) {
        Object.defineProperty(window, "visualViewport", originalViewport)
      }
    }
  })

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
