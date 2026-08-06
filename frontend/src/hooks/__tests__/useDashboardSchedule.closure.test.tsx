import { createElement, type PropsWithChildren } from "react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { renderHook, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

const { mockGet } = vi.hoisted(() => ({
  mockGet: vi.fn(),
}))

vi.mock("@/api/client", () => ({
  default: { get: mockGet },
}))

import {
  createScheduleQueryOptions,
  prefetchDashboardSchedule,
  useDashboardSchedule,
  type DashboardLesson,
} from "@/hooks/useDashboardSchedule"
import type { User } from "@/types/User"

const studentRole = "student" as User["role"]
const adminRole = "admin" as User["role"]
const lesson: DashboardLesson = {
  id: "lesson-1",
  subject: "Algorithms",
  teacher: "Ada Lovelace",
  room: "A-101",
  lesson_type: "lecture",
  weekday: "monday",
  start_time: "09:00",
  end_time: "10:30",
  parity: "both",
}

const queryContext = (signal?: AbortSignal) => ({ signal })

function createClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } })
}

function Wrapper({ children, client }: PropsWithChildren<{ client: QueryClient }>) {
  return createElement(QueryClientProvider, { client }, children)
}

describe("useDashboardSchedule closure", () => {
  beforeEach(() => {
    mockGet.mockReset()
  })

  it("short-circuits non-student and missing-group requests", async () => {
    const client = createClient()
    const nonStudent = createScheduleQueryOptions(client, adminRole, "group-1")
    const missingGroup = createScheduleQueryOptions(client, studentRole, null)

    expect(nonStudent.enabled).toBe(false)
    expect(await nonStudent.queryFn?.(queryContext())).toEqual([])
    expect(await missingGroup.queryFn?.(queryContext())).toEqual([])
    expect(mockGet).not.toHaveBeenCalled()
  })

  it("loads and sanitizes a successful schedule response", async () => {
    mockGet.mockResolvedValueOnce({ status: 200, data: [lesson, null, false] })
    const client = createClient()
    const options = createScheduleQueryOptions(client, studentRole, "group-1")
    const controller = new AbortController()

    expect(options.enabled).toBe(true)
    expect(await options.queryFn?.(queryContext(controller.signal))).toEqual([lesson])
    expect(mockGet).toHaveBeenCalledWith(
      "/schedule/group-1",
      expect.objectContaining({
        signal: controller.signal,
        etagCacheKey: "schedule:group:group-1",
      })
    )
    const requestConfig = mockGet.mock.calls[0]?.[1] as {
      validateStatus: (status: number) => boolean
    }
    expect(requestConfig.validateStatus(200)).toBe(true)
    expect(requestConfig.validateStatus(399)).toBe(true)
    expect(requestConfig.validateStatus(199)).toBe(false)
    expect(requestConfig.validateStatus(400)).toBe(false)

    mockGet.mockResolvedValueOnce({ status: 200, data: { unexpected: true } })
    expect(await options.queryFn?.(queryContext())).toEqual([])
  })

  it("uses cached data for a not-modified or recoverable failure", async () => {
    const client = createClient()
    const options = createScheduleQueryOptions(client, studentRole, 42)
    client.setQueryData(options.queryKey, [lesson])

    mockGet.mockResolvedValueOnce({ status: 304, data: [] })
    expect(await options.queryFn?.(queryContext())).toEqual([lesson])

    mockGet.mockRejectedValueOnce(new Error("temporary outage"))
    expect(await options.queryFn?.(queryContext())).toEqual([lesson])
  })

  it("rethrows aborted and uncached failures", async () => {
    const client = createClient()
    const options = createScheduleQueryOptions(client, studentRole, "group-2")
    const aborted = new Error("aborted")
    const controller = new AbortController()
    controller.abort()
    mockGet.mockRejectedValueOnce(aborted)
    await expect(options.queryFn?.(queryContext(controller.signal))).rejects.toBe(aborted)

    const uncached = new Error("uncached outage")
    mockGet.mockRejectedValueOnce(uncached)
    await expect(options.queryFn?.(queryContext())).rejects.toBe(uncached)
  })

  it("prefetches through the same query options and supports the React hook", async () => {
    mockGet.mockResolvedValue({ status: 200, data: [lesson] })
    const client = createClient()
    await expect(prefetchDashboardSchedule(client, studentRole, "group-3")).resolves.toBeUndefined()
    expect(mockGet).toHaveBeenCalledWith("/schedule/group-3", expect.any(Object))

    const { result } = renderHook(() => useDashboardSchedule(studentRole, "group-3"), {
      wrapper: ({ children }) => createElement(Wrapper, { client }, children),
    })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data).toEqual([lesson])
  })
})
