import { act, cleanup, renderHook } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { useScheduleKeyboardNav } from "@/hooks/useScheduleKeyboardNav"
import { collectWindowErrors } from "@/tests/helpers/windowErrors"

type Options = Parameters<typeof useScheduleKeyboardNav>[0]
const ownedElements = new Set<HTMLElement>()
function options(
  overrides: Partial<Pick<Options, "colCount" | "rowCount" | "todayColIdx" | "enabled">> = {}
) {
  return {
    colCount: 3,
    rowCount: 3,
    todayColIdx: 1,
    onSelect: vi.fn(),
    onOpen: vi.fn(),
    onEdit: vi.fn(),
    onDelete: vi.fn(),
    onToggleShortcuts: vi.fn(),
    ...overrides,
  }
}
function cell(row: number, col: number) {
  const element = document.createElement("div")
  element.id = `sched-cell-${row}-${col}`
  element.setAttribute("role", "gridcell")
  element.tabIndex = -1
  document.body.appendChild(element)
  ownedElements.add(element)
  return element
}
function press(key: string, init: KeyboardEventInit = {}, target: EventTarget = document.body) {
  const event = new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true, ...init })
  expect(
    collectWindowErrors(() =>
      act(() => {
        target.dispatchEvent(event)
      })
    )
  ).toEqual([])
  return event
}
afterEach(() => {
  try {
    cleanup()
  } finally {
    for (const element of ownedElements) element.remove()
    ownedElements.clear()
  }
})
describe("schedule keyboard interaction", () => {
  it.each([
    ["ArrowRight", 1, 1, 1, 2],
    ["ArrowLeft", 1, 1, 1, 0],
    ["ArrowDown", 1, 1, 2, 1],
    ["ArrowUp", 1, 1, 0, 1],
    ["ArrowRight", 1, 2, 1, 2],
    ["ArrowLeft", 1, 0, 1, 0],
    ["ArrowDown", 2, 1, 2, 1],
    ["ArrowUp", 0, 1, 0, 1],
  ] as const)("%s from (%i,%i) selects (%i,%i)", (key, row, col, nextRow, nextCol) => {
    const destination = cell(nextRow, nextCol),
      opts = options()
    const { result } = renderHook(() => useScheduleKeyboardNav(opts))
    act(() => result.current.setActiveCell({ row, col }))
    expect(press(key).defaultPrevented).toBe(true)
    expect(result.current.activeCell).toEqual({ row: nextRow, col: nextCol })
    expect(opts.onSelect).toHaveBeenCalledExactlyOnceWith(nextRow, nextCol)
    expect(destination).toHaveFocus()
  })
  it("opens the current selection once without moving focus", () => {
    const destination = cell(1, 1),
      opts = options()
    const { result } = renderHook(() => useScheduleKeyboardNav(opts))
    expect(result.current.activeCell).toBeNull()
    press("ArrowRight")
    press("ArrowDown")
    expect(press("Enter").defaultPrevented).toBe(true)
    expect(opts.onOpen).toHaveBeenCalledExactlyOnceWith(1, 1)
    expect(result.current.activeCell).toEqual({ row: 1, col: 1 })
    expect(destination).toHaveFocus()
  })
  it.each([
    ["e", "onEdit"],
    ["E", "onEdit"],
    ["Delete", "onDelete"],
    ["Backspace", "onDelete"],
    ["?", "onToggleShortcuts"],
  ] as const)("handles %s once", (key, callback) => {
    const opts = options()
    renderHook(() => useScheduleKeyboardNav(opts))
    expect(press(key).defaultPrevented).toBe(true)
    expect(opts[callback]).toHaveBeenCalledExactlyOnceWith()
  })
  it.each(["t", "T"])("%s reaches today at column zero retaining row", (key) => {
    const destination = cell(1, 0),
      opts = options({ todayColIdx: 0 })
    const { result } = renderHook(() => useScheduleKeyboardNav(opts))
    press("ArrowRight")
    press("ArrowDown")
    opts.onSelect.mockClear()
    expect(press(key).defaultPrevented).toBe(true)
    expect(opts.onSelect).toHaveBeenCalledExactlyOnceWith(1, 0)
    expect(result.current.activeCell).toEqual({ row: 1, col: 0 })
    expect(destination).toHaveFocus()
  })
  it("leaves selection and defaults alone when today is hidden", () => {
    const destination = cell(1, 1),
      opts = options({ todayColIdx: -1 })
    const { result } = renderHook(() => useScheduleKeyboardNav(opts))
    press("ArrowRight")
    press("ArrowDown")
    opts.onSelect.mockClear()
    for (const key of ["t", "T"]) expect(press(key).defaultPrevented).toBe(false)
    expect(opts.onSelect).not.toHaveBeenCalled()
    expect(result.current.activeCell).toEqual({ row: 1, col: 1 })
    expect(destination).toHaveFocus()
  })
  it.each(["ctrlKey", "metaKey"] as const)("leaves modified shortcuts with %s", (modifier) => {
    const destination = cell(1, 1),
      opts = options({ todayColIdx: 0 })
    const { result } = renderHook(() => useScheduleKeyboardNav(opts))
    press("ArrowRight")
    press("ArrowDown")
    opts.onSelect.mockClear()
    for (const key of ["e", "E", "Delete", "Backspace", "t", "T"])
      expect(press(key, { [modifier]: true }).defaultPrevented).toBe(false)
    expect(opts.onEdit).not.toHaveBeenCalled()
    expect(opts.onDelete).not.toHaveBeenCalled()
    expect(opts.onSelect).not.toHaveBeenCalled()
    expect(result.current.activeCell).toEqual({ row: 1, col: 1 })
    expect(destination).toHaveFocus()
  })
  it.each(["input", "textarea", "select"] as const)("leaves %s controls alone", (tag) => {
    const control = document.createElement(tag)
    document.body.appendChild(control)
    ownedElements.add(control)
    const opts = options(),
      { result } = renderHook(() => useScheduleKeyboardNav(opts))
    press("ArrowRight")
    opts.onSelect.mockClear()
    control.focus()
    for (const key of ["ArrowRight", "Enter", "e", "Delete", "t", "?", "Escape"])
      expect(press(key, {}, control).defaultPrevented).toBe(false)
    expect(result.current.activeCell).toEqual({ row: 0, col: 1 })
    expect(control).toHaveFocus()
    for (const callback of [
      opts.onSelect,
      opts.onOpen,
      opts.onEdit,
      opts.onDelete,
      opts.onToggleShortcuts,
    ])
      expect(callback).not.toHaveBeenCalled()
  })
  it.each([{ rowCount: 0 }, { colCount: 0 }, { enabled: false }])(
    "does not consume keys for unavailable grid %j",
    (unavailable) => {
      const opts = options(unavailable),
        { result } = renderHook(() => useScheduleKeyboardNav(opts))
      for (const key of ["ArrowDown", "Enter", "e", "Delete", "t", "?", "Escape"])
        expect(press(key).defaultPrevented).toBe(false)
      expect(result.current.activeCell).toBeNull()
      for (const callback of [
        opts.onSelect,
        opts.onOpen,
        opts.onEdit,
        opts.onDelete,
        opts.onToggleShortcuts,
      ])
        expect(callback).not.toHaveBeenCalled()
    }
  )
  it("supports optional callbacks and clearing", () => {
    const destination = cell(0, 1),
      { result } = renderHook(() =>
        useScheduleKeyboardNav({ colCount: 3, rowCount: 3, todayColIdx: 1 })
      )
    expect(press("ArrowRight").defaultPrevented).toBe(true)
    expect(result.current.activeCell).toEqual({ row: 0, col: 1 })
    expect(destination).toHaveFocus()
    for (const key of ["Enter", "e", "Delete", "?", "t"])
      expect(press(key).defaultPrevented).toBe(true)
    expect(press("Escape").defaultPrevented).toBe(true)
    expect(result.current.activeCell).toBeNull()
    press("ArrowRight")
    act(() => result.current.clearSelection())
    expect(result.current.activeCell).toBeNull()
  })
  it("selects and opens a cell without its DOM node", () => {
    const opts = options(),
      { result } = renderHook(() => useScheduleKeyboardNav(opts))
    expect(press("ArrowDown").defaultPrevented).toBe(true)
    expect(result.current.activeCell).toEqual({ row: 1, col: 0 })
    expect(opts.onSelect).toHaveBeenCalledExactlyOnceWith(1, 0)
    expect(press("Enter").defaultPrevented).toBe(true)
    expect(opts.onOpen).toHaveBeenCalledExactlyOnceWith(1, 0)
  })
  it("leaves an unknown key and selection alone", () => {
    const destination = cell(0, 1),
      opts = options(),
      { result } = renderHook(() => useScheduleKeyboardNav(opts))
    press("ArrowRight")
    opts.onSelect.mockClear()
    expect(press("a").defaultPrevented).toBe(false)
    expect(result.current.activeCell).toEqual({ row: 0, col: 1 })
    expect(opts.onSelect).not.toHaveBeenCalled()
    expect(destination).toHaveFocus()
  })
  it("uses changed bounds, today and callbacks", () => {
    const original = options(),
      { result, rerender } = renderHook((opts: Options) => useScheduleKeyboardNav(opts), {
        initialProps: original,
      })
    for (const key of ["ArrowRight", "ArrowRight", "ArrowDown", "ArrowDown"]) press(key)
    original.onSelect.mockClear()
    const current = options({ rowCount: 2, colCount: 2, todayColIdx: 0 }),
      last = cell(1, 1),
      today = cell(1, 0)
    rerender(current)
    press("ArrowDown")
    expect(result.current.activeCell).toEqual({ row: 1, col: 1 })
    expect(last).toHaveFocus()
    expect(current.onSelect).toHaveBeenCalledExactlyOnceWith(1, 1)
    expect(original.onSelect).not.toHaveBeenCalled()
    press("t")
    expect(result.current.activeCell).toEqual({ row: 1, col: 0 })
    expect(today).toHaveFocus()
    expect(current.onSelect).toHaveBeenLastCalledWith(1, 0)
  })
  it("uses only current action callbacks", () => {
    const original = options(),
      { rerender } = renderHook((opts: Options) => useScheduleKeyboardNav(opts), {
        initialProps: original,
      }),
      current = options()
    rerender(current)
    for (const key of ["Enter", "e", "Delete", "?"]) press(key)
    expect(current.onOpen).toHaveBeenCalledExactlyOnceWith(0, 0)
    for (const key of ["onEdit", "onDelete", "onToggleShortcuts"] as const)
      expect(current[key]).toHaveBeenCalledExactlyOnceWith()
    for (const key of ["onOpen", "onEdit", "onDelete", "onToggleShortcuts"] as const)
      expect(original[key]).not.toHaveBeenCalled()
  })
  it("stops while disabled and after unmount", () => {
    const opts = options({ enabled: true }),
      { result, rerender, unmount } = renderHook(
        (current: Options) => useScheduleKeyboardNav(current),
        { initialProps: opts }
      )
    press("ArrowRight")
    opts.onSelect.mockClear()
    rerender({ ...opts, enabled: false })
    expect(press("ArrowDown").defaultPrevented).toBe(false)
    expect(result.current.activeCell).toEqual({ row: 0, col: 1 })
    expect(opts.onSelect).not.toHaveBeenCalled()
    rerender(opts)
    expect(press("ArrowDown").defaultPrevented).toBe(true)
    expect(result.current.activeCell).toEqual({ row: 1, col: 1 })
    expect(opts.onSelect).toHaveBeenCalledExactlyOnceWith(1, 1)
    opts.onSelect.mockClear()
    unmount()
    expect(press("ArrowDown").defaultPrevented).toBe(false)
    expect(opts.onSelect).not.toHaveBeenCalled()
  })
})
