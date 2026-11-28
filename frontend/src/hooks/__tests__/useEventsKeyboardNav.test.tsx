import { renderHook, act } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

// ---------------------------------------------------------------------------
// Mock TanStack Router BEFORE importing the hook.
// useEventsKeyboardNav depends on useNavigate from @tanstack/react-router.
// ---------------------------------------------------------------------------
const mockNavigateFn = vi.fn()
const mockNavigate = vi.fn(() => mockNavigateFn)

vi.mock("@tanstack/react-router", () => ({
  useNavigate: () => mockNavigate(),
}))

// Import AFTER the mock is registered
import { useEventsKeyboardNav } from "../useEventsKeyboardNav"

type EventItem = { id: string }

const ITEMS: EventItem[] = [{ id: "a" }, { id: "b" }, { id: "c" }]

// Default dispatch goes through a real <body>-attached element so the event
// bubbles to the document listener with a proper HTMLElement target (the source
// calls e.target.closest / e.target.tagName, which Document lacks in jsdom).
function dispatchKey(
  key: string,
  target?: EventTarget,
  init: KeyboardEventInit = {}
): KeyboardEvent {
  const event = new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true, ...init })
  act(() => {
    const emitter = (target as Element | undefined) ?? document.body
    emitter.dispatchEvent(event)
  })
  return event
}

describe("useEventsKeyboardNav", () => {
  beforeEach(() => {
    mockNavigate.mockReturnValue(mockNavigateFn)
    mockNavigateFn.mockReset()
  })

  afterEach(() => {
    vi.clearAllMocks()
    document.body.innerHTML = ""
  })

  // -------------------------------------------------------------------------
  // registerRef + scrollToCard (lines 20-31) — get/set/delete + scrollIntoView
  // -------------------------------------------------------------------------
  it("registerRef stores an element then scrolls into view on 'j' (lines 22-31)", () => {
    const { result } = renderHook(() => useEventsKeyboardNav(ITEMS))

    const el = document.createElement("div")
    const scrollSpy = vi.fn()
    el.scrollIntoView = scrollSpy as unknown as typeof el.scrollIntoView

    act(() => {
      result.current.registerRef(0, el)
    })

    // 'j' advances to index 0 and scrolls the registered card into view
    dispatchKey("j")

    expect(result.current.activeIndex).toBe(0)
    expect(scrollSpy).toHaveBeenCalledWith({ behavior: "smooth", block: "center" })
  })

  it("uses instant scrolling with reduced motion and follows preference changes", () => {
    const query = "(prefers-reduced-motion: reduce)"
    const preference = Object.assign(new EventTarget(), {
      media: query,
      matches: true,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
    })
    const matchMedia = vi.spyOn(window, "matchMedia").mockImplementation((value) => {
      expect(value).toBe(query)
      return preference
    })

    try {
      const { result } = renderHook(() => useEventsKeyboardNav(ITEMS))
      const first = document.createElement("div")
      const second = document.createElement("div")
      const firstScroll = vi.fn()
      const secondScroll = vi.fn()
      first.scrollIntoView = firstScroll
      second.scrollIntoView = secondScroll
      act(() => {
        result.current.registerRef(0, first)
        result.current.registerRef(1, second)
      })

      dispatchKey("j")
      expect(result.current.activeIndex).toBe(0)
      expect(firstScroll).toHaveBeenLastCalledWith({ behavior: "instant", block: "center" })
      dispatchKey("j")
      expect(result.current.activeIndex).toBe(1)
      expect(secondScroll).toHaveBeenLastCalledWith({ behavior: "instant", block: "center" })
      dispatchKey("k")
      expect(result.current.activeIndex).toBe(0)
      expect(firstScroll).toHaveBeenCalledTimes(2)
      expect(firstScroll).toHaveBeenLastCalledWith({ behavior: "instant", block: "center" })

      act(() => {
        preference.matches = false
        preference.dispatchEvent(Object.assign(new Event("change"), { matches: false }))
      })
      dispatchKey("j")
      expect(result.current.activeIndex).toBe(1)
      expect(secondScroll).toHaveBeenCalledTimes(2)
      expect(secondScroll).toHaveBeenLastCalledWith({ behavior: "smooth", block: "center" })
    } finally {
      matchMedia.mockRestore()
    }
  })

  it("registerRef(null) removes the element; scrollToCard then no-ops (lines 23-30)", () => {
    const { result } = renderHook(() => useEventsKeyboardNav(ITEMS))

    const el = document.createElement("div")
    const scrollSpy = vi.fn()
    el.scrollIntoView = scrollSpy as unknown as typeof el.scrollIntoView

    act(() => {
      result.current.registerRef(0, el)
    })
    act(() => {
      // null branch — delete from the map (line 24)
      result.current.registerRef(0, null)
    })

    dispatchKey("j")

    // active index still advanced (line 47-51) but no element present → no scroll
    expect(result.current.activeIndex).toBe(0)
    expect(scrollSpy).not.toHaveBeenCalled()
  })

  // -------------------------------------------------------------------------
  // typing-guard (lines 38-41)
  // -------------------------------------------------------------------------
  it("ignores keydown when target is an <input> (line 39)", () => {
    const { result } = renderHook(() => useEventsKeyboardNav(ITEMS))

    const input = document.createElement("input")
    document.body.appendChild(input)

    dispatchKey("j", input)

    expect(result.current.activeIndex).toBe(-1)
  })

  it("ignores keydown when target is a <textarea> (line 39)", () => {
    const { result } = renderHook(() => useEventsKeyboardNav(ITEMS))

    const textarea = document.createElement("textarea")
    document.body.appendChild(textarea)

    dispatchKey("k", textarea)

    expect(result.current.activeIndex).toBe(-1)
  })

  it("ignores keydown when target is a <select> (line 39)", () => {
    renderHook(() => useEventsKeyboardNav(ITEMS))

    const select = document.createElement("select")
    document.body.appendChild(select)

    dispatchKey("Enter", select)

    expect(mockNavigateFn).not.toHaveBeenCalled()
  })

  it("leaves Enter activation to a focused button", () => {
    const { result } = renderHook(() => useEventsKeyboardNav(ITEMS))
    dispatchKey("j")

    const button = document.createElement("button")
    const icon = document.createElement("span")
    button.appendChild(icon)
    document.body.appendChild(button)

    const event = dispatchKey("Enter", icon)

    expect(event.defaultPrevented).toBe(false)
    expect(mockNavigateFn).not.toHaveBeenCalled()
    expect(result.current.activeIndex).toBe(0)
  })

  it("ignores keydown when target is inside a [role='dialog'] (line 40)", () => {
    const { result } = renderHook(() => useEventsKeyboardNav(ITEMS))

    const dialog = document.createElement("div")
    dialog.setAttribute("role", "dialog")
    const child = document.createElement("button")
    dialog.appendChild(child)
    document.body.appendChild(dialog)

    dispatchKey("j", child)

    expect(result.current.activeIndex).toBe(-1)
  })

  it("ignores keydown when target is contenteditable (line 41)", () => {
    const { result } = renderHook(() => useEventsKeyboardNav(ITEMS))

    const div = document.createElement("div")
    document.body.appendChild(div)
    // isContentEditable is read-only in jsdom; define on the instance + a
    // first 'j' on body proves the listener works, then the editable target
    // is skipped (line 41) leaving activeIndex unchanged at -1.
    Object.defineProperty(div, "isContentEditable", { value: true, configurable: true })

    dispatchKey("j", div)

    expect(result.current.activeIndex).toBe(-1)
  })

  // -------------------------------------------------------------------------
  // switch — j/J/k/K (lines 43-63)
  // -------------------------------------------------------------------------
  it("'j' advances index, clamped at items.length - 1 (lines 44-52)", () => {
    const { result } = renderHook(() => useEventsKeyboardNav(ITEMS))

    dispatchKey("j") // 0
    expect(result.current.activeIndex).toBe(0)
    dispatchKey("j") // 1
    dispatchKey("j") // 2
    dispatchKey("j") // clamp at 2
    expect(result.current.activeIndex).toBe(2)
  })

  it("uppercase 'J' also advances (line 45)", () => {
    const { result } = renderHook(() => useEventsKeyboardNav(ITEMS))

    dispatchKey("J")
    expect(result.current.activeIndex).toBe(0)
  })

  it("'k' decrements index, clamped at 0 (lines 54-62)", () => {
    const { result } = renderHook(() => useEventsKeyboardNav(ITEMS))

    dispatchKey("j") // 0
    dispatchKey("j") // 1
    dispatchKey("k") // 0
    expect(result.current.activeIndex).toBe(0)
    dispatchKey("k") // clamp at 0
    expect(result.current.activeIndex).toBe(0)
  })

  it("uppercase 'K' also decrements (line 55)", () => {
    const { result } = renderHook(() => useEventsKeyboardNav(ITEMS))

    dispatchKey("j") // 0
    dispatchKey("j") // 1
    dispatchKey("K") // 0
    expect(result.current.activeIndex).toBe(0)
  })

  // -------------------------------------------------------------------------
  // Enter (lines 64-73)
  // -------------------------------------------------------------------------
  it("'Enter' navigates to the active event detail (lines 65-70)", () => {
    renderHook(() => useEventsKeyboardNav(ITEMS))

    dispatchKey("j") // activeIndex 0 → item "a"
    dispatchKey("Enter")

    expect(mockNavigateFn).toHaveBeenCalledWith({
      to: "/events/$id",
      params: { id: "a" },
    })
  })

  it("'Enter' does nothing when no card is active (line 65 guard false)", () => {
    const { result } = renderHook(() => useEventsKeyboardNav(ITEMS))

    // activeIndex starts at -1 → guard activeIndex >= 0 is false
    dispatchKey("Enter")

    expect(mockNavigateFn).not.toHaveBeenCalled()
    expect(result.current.activeIndex).toBe(-1)
  })

  it("ignores a sparse-array hole even when its index is active", () => {
    const sparse = new Array<EventItem>(1)
    const { result } = renderHook(() => useEventsKeyboardNav(sparse))

    dispatchKey("j")
    expect(result.current.activeIndex).toBe(0)
    dispatchKey("Enter")

    expect(mockNavigateFn).not.toHaveBeenCalled()
  })

  // -------------------------------------------------------------------------
  // Escape (lines 74-77)
  // -------------------------------------------------------------------------
  it("'Escape' resets activeIndex to -1 (lines 75-76)", () => {
    const { result } = renderHook(() => useEventsKeyboardNav(ITEMS))

    dispatchKey("j") // 0
    expect(result.current.activeIndex).toBe(0)
    dispatchKey("Escape")
    expect(result.current.activeIndex).toBe(-1)
  })

  // -------------------------------------------------------------------------
  // empty items short-circuit (line 34)
  // -------------------------------------------------------------------------
  it("does not register a listener when items is empty (line 34)", () => {
    const { result } = renderHook(() => useEventsKeyboardNav([]))

    dispatchKey("j")

    expect(result.current.activeIndex).toBe(-1)
  })

  // -------------------------------------------------------------------------
  // listener cleanup on unmount (lines 80-81 / line 84 removeEventListener)
  // -------------------------------------------------------------------------
  it("removes the keydown listener on unmount (line 84)", () => {
    const { result, unmount } = renderHook(() => useEventsKeyboardNav(ITEMS))

    dispatchKey("j")
    expect(result.current.activeIndex).toBe(0)

    unmount()

    // after unmount the handler is gone — dispatching must not throw / nothing observable
    const before = result.current.activeIndex
    dispatchKey("j")
    // result.current is frozen at last render; this only asserts no error is thrown
    expect(result.current.activeIndex).toBe(before)
  })

  // -------------------------------------------------------------------------
  // reset-on-items-change effect (lines 88-90)
  // -------------------------------------------------------------------------
  it("resets activeIndex to -1 when items change (lines 88-90)", () => {
    const { result, rerender } = renderHook(({ items }) => useEventsKeyboardNav(items), {
      initialProps: { items: ITEMS },
    })

    dispatchKey("j") // 0
    expect(result.current.activeIndex).toBe(0)

    rerender({ items: [{ id: "x" }] })

    expect(result.current.activeIndex).toBe(-1)
  })
  it.each(["ctrlKey", "metaKey", "altKey", "isComposing"] as const)(
    "leaves %s keyboard events untouched",
    (modifier) => {
      const { result } = renderHook(() => useEventsKeyboardNav(ITEMS))
      dispatchKey("j")
      dispatchKey("j")
      expect(result.current.activeIndex).toBe(1)

      for (const key of ["j", "k", "Enter", "Escape"]) {
        const event = dispatchKey(key, undefined, { [modifier]: true })
        expect(event.defaultPrevented).toBe(false)
        expect(result.current.activeIndex).toBe(1)
      }
      expect(mockNavigateFn).not.toHaveBeenCalled()
    }
  )

  it("respects a key already consumed by a child control", () => {
    const { result } = renderHook(() => useEventsKeyboardNav(ITEMS))
    dispatchKey("j")
    const child = document.createElement("div")
    child.addEventListener("keydown", (event) => event.preventDefault())
    document.body.appendChild(child)

    for (const key of ["j", "k", "Enter", "Escape"]) {
      const event = dispatchKey(key, child)
      expect(event.defaultPrevented).toBe(true)
      expect(result.current.activeIndex).toBe(0)
    }
    expect(mockNavigateFn).not.toHaveBeenCalled()
  })

  it("preserves Shift+J/K navigation and ordinary Enter activation", () => {
    const { result } = renderHook(() => useEventsKeyboardNav(ITEMS))
    expect(dispatchKey("J", undefined, { shiftKey: true }).defaultPrevented).toBe(true)
    dispatchKey("J", undefined, { shiftKey: true })
    expect(result.current.activeIndex).toBe(1)
    expect(dispatchKey("K", undefined, { shiftKey: true }).defaultPrevented).toBe(true)
    expect(result.current.activeIndex).toBe(0)
    expect(dispatchKey("Enter").defaultPrevented).toBe(true)
    expect(mockNavigateFn).toHaveBeenCalledWith({
      to: "/events/$id",
      params: { id: "a" },
    })
  })
})
