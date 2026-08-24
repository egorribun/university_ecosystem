import { describe, expect, it, vi, beforeEach, afterEach } from "vitest"
import {
  announce,
  FocusTrap,
  prefersReducedMotion,
  onReducedMotionChange,
  generateId,
  skipToMainContent,
} from "@/utils/a11y"

beforeEach(() => {
  // Clean up any leftover announcer elements
  document.getElementById("sr-announcer-polite")?.remove()
  document.getElementById("sr-announcer-assertive")?.remove()
})

afterEach(() => {
  vi.restoreAllMocks()
  document.getElementById("sr-announcer-polite")?.remove()
  document.getElementById("sr-announcer-assertive")?.remove()
})

describe("a11y utilities", () => {
  describe("announce", () => {
    it("creates a polite live region and sets message", () => {
      announce("Item added to cart")

      const container = document.getElementById("sr-announcer-polite")
      expect(container).not.toBeNull()
      expect(container?.getAttribute("aria-live")).toBe("polite")
      expect(container?.getAttribute("role")).toBe("status")
      expect(container?.getAttribute("aria-atomic")).toBe("true")
      expect(container?.textContent).toBe("Item added to cart")
    })

    it("creates an assertive live region when priority is assertive", () => {
      announce("Error occurred!", "assertive")

      const container = document.getElementById("sr-announcer-assertive")
      expect(container).not.toBeNull()
      expect(container?.getAttribute("aria-live")).toBe("assertive")
      expect(container?.textContent).toBe("Error occurred!")
    })

    it("reuses existing announcer element", () => {
      announce("First message")
      announce("Second message")

      const containers = document.querySelectorAll("#sr-announcer-polite")
      expect(containers.length).toBe(1)
      expect(containers[0]?.textContent).toBe("Second message")
    })

    it("applies visually-hidden styles to announcer", () => {
      announce("Hidden message")

      const container = document.getElementById("sr-announcer-polite")
      expect(container?.style.position).toBe("absolute")
      expect(container?.style.overflow).toBe("hidden")
    })
  })

  describe("FocusTrap", () => {
    it("activates and focuses first focusable element", () => {
      const container = document.createElement("div")
      const button1 = document.createElement("button")
      button1.textContent = "First"
      const button2 = document.createElement("button")
      button2.textContent = "Second"
      container.appendChild(button1)
      container.appendChild(button2)
      document.body.appendChild(container)

      // Make elements visible for offsetParent check
      Object.defineProperty(button1, "offsetParent", { value: document.body, configurable: true })
      Object.defineProperty(button2, "offsetParent", { value: document.body, configurable: true })

      const focusSpy = vi.spyOn(button1, "focus")
      const trap = new FocusTrap(container)
      trap.activate()

      expect(focusSpy).toHaveBeenCalled()

      trap.deactivate()
      document.body.removeChild(container)
    })

    it("deactivate returns focus to previously focused element", () => {
      const container = document.createElement("div")
      const button = document.createElement("button")
      container.appendChild(button)
      document.body.appendChild(container)

      Object.defineProperty(button, "offsetParent", { value: document.body, configurable: true })

      const outsideButton = document.createElement("button")
      outsideButton.textContent = "Outside"
      document.body.appendChild(outsideButton)
      outsideButton.focus()

      const returnFocusSpy = vi.spyOn(outsideButton, "focus")

      const trap = new FocusTrap(container)
      trap.activate()
      trap.deactivate()

      expect(returnFocusSpy).toHaveBeenCalled()

      document.body.removeChild(container)
      document.body.removeChild(outsideButton)
    })

    it("does not try to restore focus to a non-HTML active element", () => {
      const container = document.createElement("div")
      const button = document.createElement("button")
      container.appendChild(button)
      document.body.appendChild(container)
      Object.defineProperty(button, "offsetParent", { value: document.body, configurable: true })

      const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg")
      svg.setAttribute("tabindex", "0")
      document.body.appendChild(svg)
      svg.focus()
      expect(document.activeElement).toBe(svg)

      const trap = new FocusTrap(container)
      trap.activate()
      expect(() => trap.deactivate()).not.toThrow()

      container.remove()
      svg.remove()
    })

    it("traps Tab key at last element → wraps to first", () => {
      const container = document.createElement("div")
      const button1 = document.createElement("button")
      const button2 = document.createElement("button")
      container.appendChild(button1)
      container.appendChild(button2)
      document.body.appendChild(container)

      Object.defineProperty(button1, "offsetParent", { value: document.body, configurable: true })
      Object.defineProperty(button2, "offsetParent", { value: document.body, configurable: true })

      const trap = new FocusTrap(container)
      trap.activate()

      // Simulate focus on last element
      button2.focus()

      const focusSpy = vi.spyOn(button1, "focus")
      const event = new KeyboardEvent("keydown", { key: "Tab", bubbles: true })
      const preventDefaultSpy = vi.spyOn(event, "preventDefault")
      document.dispatchEvent(event)

      expect(preventDefaultSpy).toHaveBeenCalled()
      expect(focusSpy).toHaveBeenCalled()

      trap.deactivate()
      document.body.removeChild(container)
    })

    it("traps Shift+Tab at first element → wraps to last", () => {
      const container = document.createElement("div")
      const button1 = document.createElement("button")
      const button2 = document.createElement("button")
      container.appendChild(button1)
      container.appendChild(button2)
      document.body.appendChild(container)

      Object.defineProperty(button1, "offsetParent", { value: document.body, configurable: true })
      Object.defineProperty(button2, "offsetParent", { value: document.body, configurable: true })

      const trap = new FocusTrap(container)
      trap.activate()

      // Focus is on first element
      button1.focus()

      const focusSpy = vi.spyOn(button2, "focus")
      const event = new KeyboardEvent("keydown", { key: "Tab", shiftKey: true, bubbles: true })
      const preventDefaultSpy = vi.spyOn(event, "preventDefault")
      document.dispatchEvent(event)

      expect(preventDefaultSpy).toHaveBeenCalled()
      expect(focusSpy).toHaveBeenCalled()

      trap.deactivate()
      document.body.removeChild(container)
    })

    it("allows Tab in either direction when focus is not at an edge", () => {
      const container = document.createElement("div")
      const first = document.createElement("button")
      const middle = document.createElement("button")
      const last = document.createElement("button")
      container.append(first, middle, last)
      document.body.appendChild(container)
      for (const element of [first, middle, last]) {
        Object.defineProperty(element, "offsetParent", {
          value: document.body,
          configurable: true,
        })
      }

      const trap = new FocusTrap(container)
      trap.activate()
      middle.focus()

      const backward = new KeyboardEvent("keydown", {
        key: "Tab",
        shiftKey: true,
        bubbles: true,
      })
      const forward = new KeyboardEvent("keydown", { key: "Tab", bubbles: true })
      const backwardPrevent = vi.spyOn(backward, "preventDefault")
      const forwardPrevent = vi.spyOn(forward, "preventDefault")
      document.dispatchEvent(backward)
      document.dispatchEvent(forward)

      expect(backwardPrevent).not.toHaveBeenCalled()
      expect(forwardPrevent).not.toHaveBeenCalled()

      trap.deactivate()
      container.remove()
    })

    it("ignores non-Tab keys", () => {
      const container = document.createElement("div")
      const button = document.createElement("button")
      container.appendChild(button)
      document.body.appendChild(container)

      Object.defineProperty(button, "offsetParent", { value: document.body, configurable: true })

      const trap = new FocusTrap(container)
      trap.activate()

      const event = new KeyboardEvent("keydown", { key: "Enter", bubbles: true })
      const preventDefaultSpy = vi.spyOn(event, "preventDefault")
      document.dispatchEvent(event)

      expect(preventDefaultSpy).not.toHaveBeenCalled()

      trap.deactivate()
      document.body.removeChild(container)
    })

    it("safely ignores Tab when the dialog has no visible focusable elements", () => {
      const container = document.createElement("div")
      document.body.appendChild(container)

      const trap = new FocusTrap(container)
      trap.activate()

      const event = new KeyboardEvent("keydown", { key: "Tab", bubbles: true })
      expect(() => document.dispatchEvent(event)).not.toThrow()

      trap.deactivate()
      document.body.removeChild(container)
    })
  })

  describe("prefersReducedMotion", () => {
    it("returns true when user prefers reduced motion", () => {
      vi.spyOn(window, "matchMedia").mockReturnValue({
        matches: true,
        media: "(prefers-reduced-motion: reduce)",
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      } as unknown as MediaQueryList)

      expect(prefersReducedMotion()).toBe(true)
    })

    it("returns false when user does not prefer reduced motion", () => {
      vi.spyOn(window, "matchMedia").mockReturnValue({
        matches: false,
        media: "(prefers-reduced-motion: reduce)",
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      } as unknown as MediaQueryList)

      expect(prefersReducedMotion()).toBe(false)
    })
  })

  describe("onReducedMotionChange", () => {
    it("subscribes to media query change events", () => {
      const addEventListenerSpy = vi.fn()
      vi.spyOn(window, "matchMedia").mockReturnValue({
        matches: false,
        media: "(prefers-reduced-motion: reduce)",
        addEventListener: addEventListenerSpy,
        removeEventListener: vi.fn(),
      } as unknown as MediaQueryList)

      const callback = vi.fn()
      onReducedMotionChange(callback)

      expect(addEventListenerSpy).toHaveBeenCalledWith("change", expect.any(Function))
    })

    it("returns unsubscribe function", () => {
      const removeEventListenerSpy = vi.fn()
      vi.spyOn(window, "matchMedia").mockReturnValue({
        matches: false,
        media: "(prefers-reduced-motion: reduce)",
        addEventListener: vi.fn(),
        removeEventListener: removeEventListenerSpy,
      } as unknown as MediaQueryList)

      const unsubscribe = onReducedMotionChange(vi.fn())
      unsubscribe()

      expect(removeEventListenerSpy).toHaveBeenCalledWith("change", expect.any(Function))
    })

    it("forwards changed preference values to the subscriber", () => {
      let listener: ((event: MediaQueryListEvent) => void) | undefined
      vi.spyOn(window, "matchMedia").mockReturnValue({
        matches: false,
        media: "(prefers-reduced-motion: reduce)",
        addEventListener: (_type: string, nextListener: EventListenerOrEventListenerObject) => {
          listener = nextListener as (event: MediaQueryListEvent) => void
        },
        removeEventListener: vi.fn(),
      } as unknown as MediaQueryList)
      const callback = vi.fn()

      onReducedMotionChange(callback)
      listener?.({ matches: true } as MediaQueryListEvent)
      listener?.({ matches: false } as MediaQueryListEvent)

      expect(callback).toHaveBeenNthCalledWith(1, true)
      expect(callback).toHaveBeenNthCalledWith(2, false)
    })
  })

  describe("generateId", () => {
    it("returns string with default prefix", () => {
      const id = generateId()
      expect(id).toMatch(/^a11y-\d+$/)
    })

    it("returns string with custom prefix", () => {
      const id = generateId("modal")
      expect(id).toMatch(/^modal-\d+$/)
    })

    it("generates unique IDs on each call", () => {
      const id1 = generateId()
      const id2 = generateId()
      expect(id1).not.toBe(id2)
    })

    it("increments counter", () => {
      const id1 = generateId()
      const id2 = generateId()
      const num1 = parseInt(id1.split("-")[1]!, 10)
      const num2 = parseInt(id2.split("-")[1]!, 10)
      expect(num2).toBe(num1 + 1)
    })
  })

  describe("skipToMainContent", () => {
    it("focuses main element when it exists", () => {
      const main = document.createElement("main")
      document.body.appendChild(main)

      const focusSpy = vi.spyOn(main, "focus")
      skipToMainContent()

      expect(focusSpy).toHaveBeenCalled()
      expect(main.tabIndex).toBe(-1)

      document.body.removeChild(main)
    })

    it("removes tabindex after focusing", () => {
      const main = document.createElement("main")
      document.body.appendChild(main)

      skipToMainContent()

      // removeAttribute is called after focus, so tabindex should be removed
      expect(main.getAttribute("tabindex")).toBeNull()

      document.body.removeChild(main)
    })

    it("falls back to [role=main] when no <main> tag", () => {
      const div = document.createElement("div")
      div.setAttribute("role", "main")
      document.body.appendChild(div)

      const focusSpy = vi.spyOn(div, "focus")
      skipToMainContent()

      expect(focusSpy).toHaveBeenCalled()

      document.body.removeChild(div)
    })

    it("does nothing when no main element exists", () => {
      // Should not throw
      expect(() => skipToMainContent()).not.toThrow()
    })
  })
})
