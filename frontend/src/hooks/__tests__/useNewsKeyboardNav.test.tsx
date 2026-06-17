import { renderHook, act } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

// ---------------------------------------------------------------------------
// Mock TanStack Router BEFORE importing the hook.
// useNewsKeyboardNav depends on useNavigate from @tanstack/react-router.
// ---------------------------------------------------------------------------
const mockNavigateFn = vi.fn()
const mockNavigate = vi.fn(() => mockNavigateFn)

vi.mock("@tanstack/react-router", () => ({
  useNavigate: () => mockNavigate(),
}))

// Import AFTER the mock is registered
import { useNewsKeyboardNav } from "../useNewsKeyboardNav"

type NewsItem = { id: string }

const ITEMS: NewsItem[] = [{ id: "a" }, { id: "b" }, { id: "c" }]

// Default dispatch goes through a real <body>-attached element so the event
// bubbles to the document listener with a proper HTMLElement target (the source
// calls e.target.closest / e.target.tagName, which Document lacks in jsdom).
function dispatchKey(key: string, target?: EventTarget) {
  act(() => {
    const event = new KeyboardEvent("keydown", { key, bubbles: true })
    const emitter = (target as Element | undefined) ?? document.body
    emitter.dispatchEvent(event)
  })
}

describe("useNewsKeyboardNav", () => {
  beforeEach(() => {
    mockNavigate.mockReturnValue(mockNavigateFn)
    mockNavigateFn.mockReset()
  })

  afterEach(() => {
    vi.clearAllMocks()
    document.body.innerHTML = ""
  })

  // -------------------------------------------------------------------------
  // registerRef + scrollToCard (lines 18-29) — get/set/delete + scrollIntoView
  // -------------------------------------------------------------------------
  it("registerRef stores an element then scrolls into view on 'j' (lines 20-29)", () => {
    const { result } = renderHook(() => useNewsKeyboardNav(ITEMS))

    const el = document.createElement("div")
    const scrollSpy = vi.fn()
    el.scrollIntoView = scrollSpy as unknown as typeof el.scrollIntoView

    act(() => {
      result.current.registerRef(0, el)
    })

    dispatchKey("j")

    expect(result.current.activeIndex).toBe(0)
    expect(scrollSpy).toHaveBeenCalledWith({ behavior: "smooth", block: "center" })
  })

  it("registerRef(null) removes the element; scrollToCard then no-ops (lines 21-28)", () => {
    const { result } = renderHook(() => useNewsKeyboardNav(ITEMS))

    const el = document.createElement("div")
    const scrollSpy = vi.fn()
    el.scrollIntoView = scrollSpy as unknown as typeof el.scrollIntoView

    act(() => {
      result.current.registerRef(0, el)
    })
    act(() => {
      result.current.registerRef(0, null)
    })

    dispatchKey("j")

    expect(result.current.activeIndex).toBe(0)
    expect(scrollSpy).not.toHaveBeenCalled()
  })

  // -------------------------------------------------------------------------
  // typing-guard (lines 36-39)
  // -------------------------------------------------------------------------
  it("ignores keydown when target is an <input> (line 37)", () => {
    const { result } = renderHook(() => useNewsKeyboardNav(ITEMS))

    const input = document.createElement("input")
    document.body.appendChild(input)

    dispatchKey("j", input)

    expect(result.current.activeIndex).toBe(-1)
  })

  it("ignores keydown when target is a <textarea> (line 37)", () => {
    const { result } = renderHook(() => useNewsKeyboardNav(ITEMS))

    const textarea = document.createElement("textarea")
    document.body.appendChild(textarea)

    dispatchKey("k", textarea)

    expect(result.current.activeIndex).toBe(-1)
  })

  it("ignores keydown when target is a <select> (line 37)", () => {
    renderHook(() => useNewsKeyboardNav(ITEMS))

    const select = document.createElement("select")
    document.body.appendChild(select)

    dispatchKey("Enter", select)

    expect(mockNavigateFn).not.toHaveBeenCalled()
  })

  it("ignores keydown when target is inside a [role='dialog'] (line 38)", () => {
    const { result } = renderHook(() => useNewsKeyboardNav(ITEMS))

    const dialog = document.createElement("div")
    dialog.setAttribute("role", "dialog")
    const child = document.createElement("button")
    dialog.appendChild(child)
    document.body.appendChild(dialog)

    dispatchKey("j", child)

    expect(result.current.activeIndex).toBe(-1)
  })

  it("ignores keydown when target is contenteditable (line 39)", () => {
    const { result } = renderHook(() => useNewsKeyboardNav(ITEMS))

    const div = document.createElement("div")
    Object.defineProperty(div, "isContentEditable", { value: true, configurable: true })
    document.body.appendChild(div)

    dispatchKey("j", div)

    expect(result.current.activeIndex).toBe(-1)
  })

  // -------------------------------------------------------------------------
  // switch — j/J/k/K (lines 41-61)
  // -------------------------------------------------------------------------
  it("'j' advances index, clamped at items.length - 1 (lines 42-50)", () => {
    const { result } = renderHook(() => useNewsKeyboardNav(ITEMS))

    dispatchKey("j") // 0
    expect(result.current.activeIndex).toBe(0)
    dispatchKey("j") // 1
    dispatchKey("j") // 2
    dispatchKey("j") // clamp at 2
    expect(result.current.activeIndex).toBe(2)
  })

  it("uppercase 'J' also advances (line 43)", () => {
    const { result } = renderHook(() => useNewsKeyboardNav(ITEMS))

    dispatchKey("J")
    expect(result.current.activeIndex).toBe(0)
  })

  it("'k' decrements index, clamped at 0 (lines 52-60)", () => {
    const { result } = renderHook(() => useNewsKeyboardNav(ITEMS))

    dispatchKey("j") // 0
    dispatchKey("j") // 1
    dispatchKey("k") // 0
    expect(result.current.activeIndex).toBe(0)
    dispatchKey("k") // clamp at 0
    expect(result.current.activeIndex).toBe(0)
  })

  it("uppercase 'K' also decrements (line 53)", () => {
    const { result } = renderHook(() => useNewsKeyboardNav(ITEMS))

    dispatchKey("j") // 0
    dispatchKey("j") // 1
    dispatchKey("K") // 0
    expect(result.current.activeIndex).toBe(0)
  })

  // -------------------------------------------------------------------------
  // Enter (lines 62-71)
  // -------------------------------------------------------------------------
  it("'Enter' navigates to the active article (lines 63-68)", () => {
    renderHook(() => useNewsKeyboardNav(ITEMS))

    dispatchKey("j") // activeIndex 0 → item "a"
    dispatchKey("Enter")

    expect(mockNavigateFn).toHaveBeenCalledWith({
      to: "/news/$id",
      params: { id: "a" },
    })
  })

  it("'Enter' does nothing when no card is active (line 63 guard false)", () => {
    const { result } = renderHook(() => useNewsKeyboardNav(ITEMS))

    dispatchKey("Enter")

    expect(mockNavigateFn).not.toHaveBeenCalled()
    expect(result.current.activeIndex).toBe(-1)
  })

  // -------------------------------------------------------------------------
  // Escape (lines 72-75)
  // -------------------------------------------------------------------------
  it("'Escape' resets activeIndex to -1 (lines 73-74)", () => {
    const { result } = renderHook(() => useNewsKeyboardNav(ITEMS))

    dispatchKey("j") // 0
    expect(result.current.activeIndex).toBe(0)
    dispatchKey("Escape")
    expect(result.current.activeIndex).toBe(-1)
  })

  // -------------------------------------------------------------------------
  // empty items short-circuit (line 32)
  // -------------------------------------------------------------------------
  it("does not register a listener when items is empty (line 32)", () => {
    const { result } = renderHook(() => useNewsKeyboardNav([]))

    dispatchKey("j")

    expect(result.current.activeIndex).toBe(-1)
  })

  // -------------------------------------------------------------------------
  // listener cleanup on unmount (line 80 removeEventListener)
  // -------------------------------------------------------------------------
  it("removes the keydown listener on unmount (line 80)", () => {
    const { result, unmount } = renderHook(() => useNewsKeyboardNav(ITEMS))

    dispatchKey("j")
    expect(result.current.activeIndex).toBe(0)

    unmount()

    const before = result.current.activeIndex
    dispatchKey("j")
    expect(result.current.activeIndex).toBe(before)
  })

  // -------------------------------------------------------------------------
  // reset-on-items-change effect (lines 84-86)
  // -------------------------------------------------------------------------
  it("resets activeIndex to -1 when items change (lines 84-86)", () => {
    const { result, rerender } = renderHook(({ items }) => useNewsKeyboardNav(items), {
      initialProps: { items: ITEMS },
    })

    dispatchKey("j") // 0
    expect(result.current.activeIndex).toBe(0)

    rerender({ items: [{ id: "x" }] })

    expect(result.current.activeIndex).toBe(-1)
  })
})
