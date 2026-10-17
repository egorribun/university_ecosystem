import { act, cleanup, renderHook } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { useScheduleKeyboardNav } from "@/hooks/useScheduleKeyboardNav"
import { collectWindowErrors } from "@/tests/helpers/windowErrors"
type Options = Parameters<typeof useScheduleKeyboardNav>[0]
const ownedElements = new Set<HTMLElement>()
function cell(row: number, col: number) {
  const element = document.createElement("div")
  element.id = `sched-cell-${row}-${col}`
  element.setAttribute("role", "gridcell")
  element.tabIndex = -1
  document.body.appendChild(element)
  ownedElements.add(element)
  return element
}
function press(key: string) {
  const event = new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true })
  expect(
    collectWindowErrors(() =>
      act(() => {
        document.body.dispatchEvent(event)
      })
    )
  ).toEqual([])
  return event
}
function last() {
  for (const key of ["ArrowRight", "ArrowRight", "ArrowDown", "ArrowDown"]) press(key)
}
afterEach(() => {
  try {
    cleanup()
  } finally {
    for (const el of ownedElements) el.remove()
    ownedElements.clear()
  }
})
describe("schedule selection after visible dimensions change", () => {
  it.each([
    { rowCount: 2, colCount: 3, settingsOpen: false },
    { rowCount: 3, colCount: 2, settingsOpen: false },
    { rowCount: 2, colCount: 2, settingsOpen: false },
    { rowCount: 2, colCount: 2, settingsOpen: true },
  ])("repairs Enter selection after %j", (scenario) => {
    const previous = cell(2, 2),
      original = {
        rowCount: 3,
        colCount: 3,
        todayColIdx: 0,
        onSelect: vi.fn(),
        onOpen: vi.fn(),
        enabled: true,
      }
    const { result, rerender } = renderHook<ReturnType<typeof useScheduleKeyboardNav>, Options>(
      (opts) => useScheduleKeyboardNav(opts),
      {
        initialProps: original,
      }
    )
    last()
    expect(result.current.activeCell).toEqual({ row: 2, col: 2 })
    expect(previous).toHaveFocus()
    original.onSelect.mockClear()
    if (scenario.settingsOpen) rerender({ ...original, enabled: false })
    previous.remove()
    const rows = Array.from({ length: scenario.rowCount }, (_, row) =>
        Array.from({ length: scenario.colCount }, (_, col) => `Lesson ${row},${col}`)
      ),
      row = scenario.rowCount - 1,
      col = scenario.colCount - 1,
      destination = cell(row, col),
      opened: string[] = []
    const current = {
      rowCount: scenario.rowCount,
      colCount: scenario.colCount,
      todayColIdx: 0,
      onSelect: vi.fn(),
      onOpen: (r: number, c: number) => {
        const lesson = rows[r]?.[c]
        if (lesson) opened.push(lesson)
      },
      enabled: !scenario.settingsOpen,
    }
    rerender(current)
    if (scenario.settingsOpen) {
      expect(press("Enter").defaultPrevented).toBe(false)
      expect(opened).toEqual([])
      expect(current.onSelect).not.toHaveBeenCalled()
      rerender({ ...current, enabled: true })
    }
    expect(result.current.activeCell).toEqual({ row: 2, col: 2 })
    expect(destination).not.toHaveFocus()
    expect(current.onSelect).not.toHaveBeenCalled()
    expect(opened).toEqual([])
    expect(press("Enter").defaultPrevented).toBe(true)
    expect(opened).toEqual([`Lesson ${row},${col}`])
    expect(result.current.activeCell).toEqual({ row, col })
    expect(destination).toHaveFocus()
    expect(current.onSelect).toHaveBeenCalledExactlyOnceWith(row, col)
    expect(original.onSelect).not.toHaveBeenCalled()
    expect(original.onOpen).not.toHaveBeenCalled()
  })
  it("opens valid selection without repeated selection focus or scroll", () => {
    const destination = cell(1, 1),
      opts = { rowCount: 3, colCount: 3, todayColIdx: 0, onSelect: vi.fn(), onOpen: vi.fn() },
      { result, rerender } = renderHook((o: Options) => useScheduleKeyboardNav(o), {
        initialProps: opts,
      })
    press("ArrowRight")
    press("ArrowDown")
    opts.onSelect.mockClear()
    const focus = vi.spyOn(destination, "focus"),
      scroll = vi.spyOn(destination, "scrollIntoView")
    try {
      rerender({ ...opts, rowCount: 2, colCount: 2 })
      expect(press("Enter").defaultPrevented).toBe(true)
      expect(opts.onOpen).toHaveBeenCalledExactlyOnceWith(1, 1)
      expect(opts.onSelect).not.toHaveBeenCalled()
      expect(focus).not.toHaveBeenCalled()
      expect(scroll).not.toHaveBeenCalled()
      expect(result.current.activeCell).toEqual({ row: 1, col: 1 })
      expect(destination).toHaveFocus()
    } finally {
      focus.mockRestore()
      scroll.mockRestore()
    }
  })
  it("opens origin without creating selection", () => {
    const origin = cell(0, 0),
      opts = { rowCount: 1, colCount: 1, todayColIdx: 0, onSelect: vi.fn(), onOpen: vi.fn() },
      { result } = renderHook(() => useScheduleKeyboardNav(opts))
    expect(press("Enter").defaultPrevented).toBe(true)
    expect(opts.onOpen).toHaveBeenCalledExactlyOnceWith(0, 0)
    expect(opts.onSelect).not.toHaveBeenCalled()
    expect(result.current.activeCell).toBeNull()
    expect(origin).not.toHaveFocus()
  })
  it.each([
    { rowCount: 0, colCount: 3 },
    { rowCount: 3, colCount: 0 },
  ])("leaves retained selection for empty grid %j", (dimensions) => {
    const opts = { rowCount: 3, colCount: 3, todayColIdx: 0, onSelect: vi.fn(), onOpen: vi.fn() },
      { result, rerender } = renderHook((o: Options) => useScheduleKeyboardNav(o), {
        initialProps: opts,
      })
    last()
    opts.onSelect.mockClear()
    rerender({ ...opts, ...dimensions })
    expect(press("Enter").defaultPrevented).toBe(false)
    expect(result.current.activeCell).toEqual({ row: 2, col: 2 })
    expect(opts.onSelect).not.toHaveBeenCalled()
    expect(opts.onOpen).not.toHaveBeenCalled()
  })
  it("keeps arrow movement relative before clamping", () => {
    const destination = cell(1, 1),
      opts = { rowCount: 3, colCount: 3, todayColIdx: 0, onSelect: vi.fn() },
      { result, rerender } = renderHook((o: Options) => useScheduleKeyboardNav(o), {
        initialProps: opts,
      })
    last()
    opts.onSelect.mockClear()
    rerender({ ...opts, rowCount: 2, colCount: 2 })
    expect(press("ArrowLeft").defaultPrevented).toBe(true)
    expect(result.current.activeCell).toEqual({ row: 1, col: 1 })
    expect(opts.onSelect).toHaveBeenCalledExactlyOnceWith(1, 1)
    expect(destination).toHaveFocus()
  })
  it("repairs without callbacks or DOM destination", () => {
    const opts = { rowCount: 3, colCount: 3, todayColIdx: 0 },
      { result, rerender } = renderHook((o: Options) => useScheduleKeyboardNav(o), {
        initialProps: opts,
      })
    last()
    rerender({ ...opts, rowCount: 1, colCount: 1 })
    expect(press("Enter").defaultPrevented).toBe(true)
    expect(result.current.activeCell).toEqual({ row: 0, col: 0 })
  })
})
