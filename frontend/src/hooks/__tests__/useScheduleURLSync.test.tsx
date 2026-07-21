import { renderHook, act } from "@testing-library/react"
import { describe, expect, it, vi, beforeEach } from "vitest"
import { useScheduleURLSync } from "../useScheduleURLSync"
import { useURLState } from "@/hooks/useURLState"
import { useScheduleUIStore } from "@/stores/scheduleUIStore"

// Mock hooks
vi.mock("@/hooks/useURLState")
vi.mock("@/stores/scheduleUIStore")

describe("useScheduleURLSync", () => {
  const mockSetParam = vi.fn()
  const mockSetWeekOffset = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()

    // Default mocks
    vi.mocked(useURLState).mockReturnValue({
      params: { w: "" },
      setParam: mockSetParam,
      setParams: vi.fn(),
    })

    vi.mocked(useScheduleUIStore).mockImplementation((selector) => {
      const state = {
        weekOffset: 0,
        setWeekOffset: mockSetWeekOffset,
      } as any
      return selector(state)
    })
  })

  it("syncs URL to store on mount", () => {
    vi.mocked(useURLState).mockReturnValue({
      params: { w: "2" },
      setParam: mockSetParam,
      setParams: vi.fn(),
    })

    renderHook(() => useScheduleURLSync())

    expect(mockSetWeekOffset).toHaveBeenCalledWith(2)
  })

  it("does NOT write to URL on mount (URL is authoritative at mount time)", () => {
    // W179 SW10 — store→URL effect skips its first run so that a stale
    // weekOffset=0 does not clear a valid ?w=N URL param before the
    // URL→store effect has a chance to push the parsed value into the store.
    vi.mocked(useURLState).mockReturnValue({
      params: { w: "1" },
      setParam: mockSetParam,
      setParams: vi.fn(),
    })

    vi.mocked(useScheduleUIStore).mockImplementation((selector) => {
      const state = {
        weekOffset: 0, // stale store value at mount
        setWeekOffset: mockSetWeekOffset,
      } as any
      return selector(state)
    })

    renderHook(() => useScheduleURLSync())

    // setParam MUST NOT be called on mount — that would strip ?w=1 from the
    // URL, triggering a spurious navigation and a 90s E2E teardown hang.
    expect(mockSetParam).not.toHaveBeenCalled()
    // But the URL→store direction must still fire.
    expect(mockSetWeekOffset).toHaveBeenCalledWith(1)
  })

  it("syncs store to URL when weekOffset changes after mount", () => {
    let currentWeekOffset = 0

    vi.mocked(useScheduleUIStore).mockImplementation((selector) => {
      const state = {
        weekOffset: currentWeekOffset,
        setWeekOffset: mockSetWeekOffset,
      } as any
      return selector(state)
    })

    const { rerender } = renderHook(() => useScheduleURLSync())

    // First render (mount) — store→URL is skipped, setParam NOT called.
    expect(mockSetParam).not.toHaveBeenCalled()

    // Simulate weekOffset changing to 3 after mount (e.g. user clicks "next week").
    currentWeekOffset = 3
    act(() => {
      rerender()
    })

    // W147 SW5 — setParam now takes `number` for `w` after schedule schema
    // changed to `v.union([v.number(), v.pipe(v.string(), v.transform(...))])`
    expect(mockSetParam).toHaveBeenCalledWith("w", 3)
  })

  it("removes 'w' param when weekOffset resets to 0 after mount", () => {
    let currentWeekOffset = 1

    vi.mocked(useURLState).mockReturnValue({
      params: { w: "1" },
      setParam: mockSetParam,
      setParams: vi.fn(),
    })

    vi.mocked(useScheduleUIStore).mockImplementation((selector) => {
      const state = {
        weekOffset: currentWeekOffset,
        setWeekOffset: mockSetWeekOffset,
      } as any
      return selector(state)
    })

    const { rerender } = renderHook(() => useScheduleURLSync())

    // On mount: weekOffset=1, urlWeek="1" → no write needed.
    expect(mockSetParam).not.toHaveBeenCalled()

    // User navigates back to current week → weekOffset resets to 0.
    currentWeekOffset = 0
    act(() => {
      rerender()
    })

    expect(mockSetParam).toHaveBeenCalledWith("w", "")
  })
})
