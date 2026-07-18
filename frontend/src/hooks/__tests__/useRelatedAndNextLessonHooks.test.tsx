import { describe, expect, it, vi } from "vitest"
import { renderHook } from "@testing-library/react"
import { useNextLesson } from "../useNextLesson"
import { useRelatedEvents } from "../useRelatedEvents"
import { useRelatedNews } from "../useRelatedNews"
import { useRouteType } from "../useRouteType"

// Mock dependencies
const mockUseScheduleData = vi.fn()
vi.mock("@/hooks/useScheduleData", () => ({
  useScheduleData: () => mockUseScheduleData(),
}))

const mockGetQueriesData = vi.fn()
vi.mock("@tanstack/react-query", () => ({
  useQueryClient: () => ({
    getQueriesData: mockGetQueriesData,
  }),
  QueryClient: class {},
}))

const mockUseRouterState = vi.fn()
vi.mock("@tanstack/react-router", () => ({
  useRouterState: (opts?: { select: Function }) => {
    const val = mockUseRouterState()
    if (opts?.select) {
      return opts.select({ location: { pathname: val } })
    }
    return val
  },
}))

describe("useNextLesson, useRelatedEvents, useRelatedNews, useRouteType hooks", () => {
  describe("useNextLesson", () => {
    it("returns null when no next lesson", () => {
      mockUseScheduleData.mockReturnValue({
        nextLesson: null,
        timeLeftShort: "",
      })
      const { result } = renderHook(() => useNextLesson())
      expect(result.current).toBeNull()
    })

    it("returns null for room with missing building prefix structure", () => {
      mockUseScheduleData.mockReturnValue({
        nextLesson: {
          room: "101",
          subject: "Math",
        },
        timeLeftShort: "5m",
      })
      const { result } = renderHook(() => useNextLesson())
      expect(result.current).toBeNull()
    })

    it("returns null for invalid building", () => {
      mockUseScheduleData.mockReturnValue({
        nextLesson: {
          room: "INVALID-101",
          subject: "Math",
        },
        timeLeftShort: "5m",
      })
      const { result } = renderHook(() => useNextLesson())
      expect(result.current).toBeNull()
    })

    it("returns null for room with missing floor prefix pattern", () => {
      mockUseScheduleData.mockReturnValue({
        nextLesson: {
          room: "ГУК-XXX",
          subject: "Math",
        },
        timeLeftShort: "5m",
      })
      const { result } = renderHook(() => useNextLesson())
      expect(result.current).toBeNull()
    })

    it("returns null for room with floor 0", () => {
      mockUseScheduleData.mockReturnValue({
        nextLesson: {
          room: "ГУК-001",
          subject: "Math",
        },
        timeLeftShort: "5m",
      })
      const { result } = renderHook(() => useNextLesson())
      expect(result.current).toBeNull()
    })

    it("returns parsed lesson info for valid room and fallback empty subject", () => {
      mockUseScheduleData.mockReturnValue({
        nextLesson: {
          room: "ГУК-305",
        },
        timeLeftShort: "5m",
      })
      const { result } = renderHook(() => useNextLesson())
      expect(result.current).toEqual({
        building: "ГУК",
        floor: 3,
        roomId: "ГУК-305",
        subject: "",
        timeLeft: "5m",
      })
    })
  })

  describe("useRelatedEvents", () => {
    it("returns related events correctly, checking event_type_en fallback and limit bounds", () => {
      const mockEvents = [
        { id: "1", event_type: "lecture", title: "L1" },
        { id: "2", event_type_en: "lecture", title: "L2" },
        { id: "3", event_type: "seminar", title: "S1" },
        { id: "4", event_type: "lecture", title: "L3" },
      ]
      mockGetQueriesData.mockReturnValue([
        ["events-query-key", { pages: [{ items: mockEvents }] }],
      ])

      // Limit of 2: will return 2 sameCategory
      const { result } = renderHook(() => useRelatedEvents("1", "lecture", 2))
      expect(result.current).toHaveLength(2)
      expect(result.current![0]!.id).toBe("2")
      expect(result.current![1]!.id).toBe("4")

      // Limit of 4: will return all sameCategory + remaining
      const { result: res2 } = renderHook(() => useRelatedEvents("1", "lecture", 4))
      expect(res2.current.length).toBeGreaterThanOrEqual(3)
    })
  })

  describe("useRelatedNews", () => {
    it("returns related news correctly, checking limit bounds", () => {
      const mockNews = [
        { id: "1", title: "News 1", content: "general content" },
        { id: "2", title: "News 2", content: "academic content with study exam" },
        { id: "3", title: "News 3", content: "sports content" },
        { id: "4", title: "News 4", content: "study exam info" },
      ]
      mockGetQueriesData.mockReturnValue([
        ["news-query-key", { pages: [{ items: mockNews }] }],
      ])

      // Limit of 2: will return 2 sameCategory
      const { result } = renderHook(() => useRelatedNews("1", "education", 2))
      expect(result.current).toHaveLength(2)
      expect(result.current![0]!.id).toBe("2")
      expect(result.current![1]!.id).toBe("4")

      // Limit of 4: will return all sameCategory + remaining
      const { result: res2 } = renderHook(() => useRelatedNews("1", "education", 4))
      expect(res2.current.length).toBeGreaterThanOrEqual(3)
    })
  })

  describe("useRouteType", () => {
    it("identifies route types correctly", () => {
      mockUseRouterState.mockReturnValue("/login")
      let { result } = renderHook(() => useRouteType())
      expect(result.current.isCompactPage).toBe(true)
      expect(result.current.isAuth).toBe(true)

      mockUseRouterState.mockReturnValue("/messenger")
      result = renderHook(() => useRouteType()).result
      expect(result.current.isMessenger).toBe(true)
      expect(result.current.hideFooter).toBe(true)

      mockUseRouterState.mockReturnValue("/profile")
      result = renderHook(() => useRouteType()).result
      expect(result.current.isProfile).toBe(true)

      mockUseRouterState.mockReturnValue("/settings")
      result = renderHook(() => useRouteType()).result
      expect(result.current.isSettings).toBe(true)
    })
  })
})
