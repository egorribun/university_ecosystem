import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { renderHook, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import type { ReactNode } from "react"

import { useScheduleData } from "../useScheduleData"
import {
  scheduleGroupsQueryOptions,
  pageScheduleQueryOptions,
} from "@/api/hooks/schedule"
import type { ScheduleGroup } from "@/components/schedule/scheduleUtils"

/**
 * Wave 130 polish — closes §Honesty probe #4 (vitest count delta from
 * useScheduleData refactor = 0).
 *
 * Asserts the SSR-loader integration path end-to-end:
 *  1. When the QueryClient cache is pre-populated with groups (as the
 *     /schedule SSR loader does via ensureQueryData(scheduleGroupsQueryOptions())),
 *     the hook reads from cache without re-fetching.
 *  2. Auto-select picks user.group_id from the prefetched cache.
 *  3. The schedule query fires with the resolved groupId.
 *  4. Cache identity preservation: queryKey shapes match the factory
 *     output exactly so SSR-prefetched entries hydrate cleanly into
 *     client-side useScheduleData consumption.
 */

vi.mock("@/api/client", () => ({
  default: {
    get: vi.fn(),
  },
}))

vi.mock("@/contexts/AuthContext", () => ({
  useAuth: vi.fn(),
}))

import api from "@/api/client"
import { useAuth } from "@/contexts/AuthContext"

const apiGetMock = vi.mocked(api.get)
const useAuthMock = vi.mocked(useAuth)

function newClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
    },
  })
}

function wrapper(client: QueryClient) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>
  }
}

describe("useScheduleData (Wave 130 SW1 factory integration)", () => {
  beforeEach(() => {
    apiGetMock.mockReset()
    useAuthMock.mockReset()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it("reads SSR-prefetched groups cache without re-fetching network", async () => {
    const groups: ScheduleGroup[] = [
      { id: "group-1", name: "Group 1" },
      { id: "group-2", name: "Group 2" },
    ]
    const client = newClient()

    // Simulate SSR loader: ensureQueryData(scheduleGroupsQueryOptions())
    // populates the cache. Cache identity must match exactly.
    const opts = scheduleGroupsQueryOptions()
    client.setQueryData(opts.queryKey, groups)

    useAuthMock.mockReturnValue({
      user: { id: "u1", role: "admin", group_id: null },
    } as never)

    const { result } = renderHook(() => useScheduleData(), { wrapper: wrapper(client) })

    await waitFor(() => {
      expect(result.current.groups).toEqual(groups)
    })

    // Critical assertion: groups query consumed cache, no network call fired.
    expect(apiGetMock).not.toHaveBeenCalledWith("/groups", expect.anything())
  })

  it("auto-selects user.group_id from prefetched groups cache", async () => {
    const groups: ScheduleGroup[] = [
      { id: "group-1", name: "Group 1" },
      { id: "group-2", name: "Group 2" },
    ]
    const client = newClient()
    client.setQueryData(scheduleGroupsQueryOptions().queryKey, groups)

    useAuthMock.mockReturnValue({
      user: { id: "u1", role: "student", group_id: "group-2" },
    } as never)

    // Mock /schedule/{groupId} response — auto-select effect should fire it
    // once group_id is resolved on next tick.
    apiGetMock.mockResolvedValueOnce({ data: [], status: 200 })

    const { result } = renderHook(() => useScheduleData(), { wrapper: wrapper(client) })

    await waitFor(() => {
      expect(result.current.selectedGroup).toBe("group-2")
    })

    // Schedule query for the user's group should have fired.
    await waitFor(() => {
      expect(apiGetMock).toHaveBeenCalledWith("/schedule/group-2", expect.anything())
    })
  })

  it("falls back to first group when user.group_id is not in groups list", async () => {
    const groups: ScheduleGroup[] = [
      { id: "group-1", name: "Group 1" },
      { id: "group-2", name: "Group 2" },
    ]
    const client = newClient()
    client.setQueryData(scheduleGroupsQueryOptions().queryKey, groups)

    useAuthMock.mockReturnValue({
      user: { id: "u1", role: "student", group_id: "group-MISSING" },
    } as never)

    apiGetMock.mockResolvedValueOnce({ data: [], status: 200 })

    const { result } = renderHook(() => useScheduleData(), { wrapper: wrapper(client) })

    await waitFor(() => {
      // Auto-select falls back to groups[0] since user.group_id doesn't exist.
      expect(result.current.selectedGroup).toBe("group-1")
    })
  })

  it("schedule queryKey matches pageScheduleQueryOptions(groupId) shape", () => {
    const opts = pageScheduleQueryOptions("group-test")
    expect(opts.queryKey).toEqual(["schedule", "group", "group-test"])
  })

  it("groups queryKey shape preserved across factory refactor (cache identity)", () => {
    const opts = scheduleGroupsQueryOptions()
    expect(opts.queryKey).toEqual(["schedule", "groups"])
  })
})
