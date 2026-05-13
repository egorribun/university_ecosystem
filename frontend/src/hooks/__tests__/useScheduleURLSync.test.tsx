/* eslint-disable @typescript-eslint/no-explicit-any */
import { renderHook } from "@testing-library/react"
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

  it("syncs store to URL when weekOffset changes", () => {
    vi.mocked(useScheduleUIStore).mockImplementation((selector) => {
      const state = {
        weekOffset: 3,
        setWeekOffset: mockSetWeekOffset,
      } as any
      return selector(state)
    })

    renderHook(() => useScheduleURLSync())

    // W147 SW5 — setParam now takes `number` for `w` after schedule schema
    // changed to `v.union([v.number(), v.pipe(v.string(), v.transform(...))])`.
    // Same union pattern as W120 SW5 mapSearchSchema; closes pre-W147 500
    // bug where `?w=1` was rejected by `v.string()` validateSearch.
    expect(mockSetParam).toHaveBeenCalledWith("w", 3)
  })

  it("removes 'w' param when weekOffset is 0", () => {
    vi.mocked(useURLState).mockReturnValue({
      params: { w: "1" },
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

    renderHook(() => useScheduleURLSync())

    expect(mockSetParam).toHaveBeenCalledWith("w", "")
  })
})
