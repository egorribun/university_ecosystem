import { renderHook, act } from "@testing-library/react"
import { describe, it, expect, vi, beforeEach } from "vitest"

import { useScheduleKeyboardNav } from "@/hooks/useScheduleKeyboardNav"

function makeOpts(over: Record<string, unknown> = {}) {
  return {
    colCount: 5,
    rowCount: 7,
    todayColIdx: 2,
    onSelect: vi.fn(),
    onOpen: vi.fn(),
    onEdit: vi.fn(),
    onDelete: vi.fn(),
    onToggleShortcuts: vi.fn(),
    enabled: true,
    ...over,
  }
}

function press(key: string, init: KeyboardEventInit = {}) {
  act(() => {
    document.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true, ...init }))
  })
}

describe("useScheduleKeyboardNav", () => {
  beforeEach(() => {
    document.body.innerHTML = ""
  })

  it("moves the active cell with arrow keys and fires onSelect (clamped to bounds)", () => {
    const opts = makeOpts()
    const { result } = renderHook(() => useScheduleKeyboardNav(opts))
    press("ArrowRight")
    expect(result.current.activeCell).toEqual({ row: 0, col: 1 })
    expect(opts.onSelect).toHaveBeenLastCalledWith(0, 1)
    press("ArrowDown")
    expect(result.current.activeCell).toEqual({ row: 1, col: 1 })
    // clamp: ArrowLeft past col 0 from (1,1)->(1,0); again stays at 0
    press("ArrowLeft")
    press("ArrowLeft")
    expect(result.current.activeCell).toEqual({ row: 1, col: 0 })
    // clamp: ArrowUp past row 0
    press("ArrowUp")
    press("ArrowUp")
    expect(result.current.activeCell).toEqual({ row: 0, col: 0 })
  })

  it("focuses and scrolls the destination cell when it exists", () => {
    const target = document.createElement("button")
    target.id = "sched-cell-0-1"
    target.scrollIntoView = vi.fn()
    document.body.appendChild(target)
    const focus = vi.spyOn(target, "focus")
    const opts = makeOpts()
    renderHook(() => useScheduleKeyboardNav(opts))

    press("ArrowRight")

    expect(focus).toHaveBeenCalledWith({ preventScroll: false })
    expect(target.scrollIntoView).toHaveBeenCalledWith({
      behavior: "smooth",
      block: "nearest",
      inline: "nearest",
    })
  })

  it("fires the action callbacks for Enter / E / Delete / ? and jumps to today on T", () => {
    const opts = makeOpts()
    renderHook(() => useScheduleKeyboardNav(opts))
    press("Enter")
    expect(opts.onOpen).toHaveBeenCalledOnce()
    press("e")
    expect(opts.onEdit).toHaveBeenCalledOnce()
    press("Delete")
    expect(opts.onDelete).toHaveBeenCalledOnce()
    press("Backspace")
    expect(opts.onDelete).toHaveBeenCalledTimes(2)
    press("?")
    expect(opts.onToggleShortcuts).toHaveBeenCalledOnce()
    press("t")
    expect(opts.onSelect).toHaveBeenLastCalledWith(0, 2)
  })

  it("respects the ctrl/meta modifier guard on E / Delete / T", () => {
    const opts = makeOpts()
    renderHook(() => useScheduleKeyboardNav(opts))
    press("e", { ctrlKey: true })
    press("Delete", { metaKey: true })
    press("t", { ctrlKey: true })
    expect(opts.onEdit).not.toHaveBeenCalled()
    expect(opts.onDelete).not.toHaveBeenCalled()
  })

  it("clears the active cell on Escape and clearSelection()", () => {
    const opts = makeOpts()
    const { result } = renderHook(() => useScheduleKeyboardNav(opts))
    press("ArrowRight")
    expect(result.current.activeCell).not.toBeNull()
    press("Escape")
    expect(result.current.activeCell).toBeNull()
    press("ArrowRight")
    act(() => result.current.clearSelection())
    expect(result.current.activeCell).toBeNull()
  })

  it("ignores keys when typing in an input and when disabled or empty", () => {
    const opts = makeOpts()
    const { rerender } = renderHook(({ o }) => useScheduleKeyboardNav(o), {
      initialProps: { o: opts },
    })
    const input = document.createElement("input")
    document.body.appendChild(input)
    act(() => {
      input.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowRight", bubbles: true }))
    })
    expect(opts.onSelect).not.toHaveBeenCalled()

    // disabled → listener not attached
    const disabled = makeOpts({ enabled: false })
    rerender({ o: disabled })
    press("ArrowRight")
    expect(disabled.onSelect).not.toHaveBeenCalled()

    // empty grid → early return
    const empty = makeOpts({ rowCount: 0 })
    rerender({ o: empty })
    press("ArrowRight")
    expect(empty.onSelect).not.toHaveBeenCalled()
  })
})
