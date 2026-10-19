import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { act, cleanup, renderHook, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import type { ReactNode } from "react"

import { useScheduleData } from "../useScheduleData"
import { CampusTimezoneProvider, useCampusTimezone } from "@/contexts/CampusTimezoneContext"
import { scheduleGroupsQueryOptions, pageScheduleQueryOptions } from "@/api/hooks/schedule"
import { currentUserQueryOptions } from "@/api/hooks/users"
import type { ScheduleGroup, Lesson } from "@/components/schedule/scheduleUtils"
import { useAuthStore } from "@/stores/useAuthStore"
import type { UserState } from "@/types/Auth"

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

vi.mock("@/db/lazy", () => ({
  getDatabase: vi.fn(),
  getDatabaseLazily: vi.fn(),
}))

import api from "@/api/client"
import { useAuth } from "@/contexts/AuthContext"
import { getDatabaseLazily } from "@/db/lazy"

const apiGetMock = vi.mocked(api.get)
const useAuthMock = vi.mocked(useAuth)
const getDatabaseMock = vi.mocked(getDatabaseLazily)

function setAuthFixture(user: UserState | null) {
  useAuthMock.mockReturnValue({ user } as never)
  useAuthStore.setState({ user, loading: false })
}

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

function campusBoundaryClient(groupId: string): QueryClient {
  const client = newClient()
  const lessons: Lesson[] = [
    {
      id: "odd-early",
      group_id: groupId,
      weekday: "monday",
      start_time: "00:15",
      end_time: "00:45",
      subject: "Early campus lesson",
      teacher: "Teacher",
      room: "101",
      lesson_type: "lecture",
      parity: "odd",
    },
    {
      id: "even-only",
      group_id: groupId,
      weekday: "monday",
      start_time: "00:20",
      end_time: "00:40",
      subject: "Other parity",
      teacher: "Teacher",
      room: "102",
      lesson_type: "lecture",
      parity: "even",
    },
    {
      id: "odd-late",
      group_id: groupId,
      weekday: "monday",
      start_time: "01:00",
      end_time: "02:00",
      subject: "Later campus lesson",
      teacher: "Teacher",
      room: "103",
      lesson_type: "lecture",
      parity: "odd",
    },
  ]
  client.setQueryData(scheduleGroupsQueryOptions().queryKey, [{ id: groupId, name: "Campus" }])
  client.setQueryData(pageScheduleQueryOptions(groupId).queryKey, lessons)
  setAuthFixture({ id: "campus-fixture-user", role: "student", group_id: groupId } as UserState)
  return client
}

describe("useScheduleData (Wave 130 SW1 factory integration)", () => {
  beforeEach(() => {
    apiGetMock.mockReset()
    useAuthMock.mockReset()
    getDatabaseMock.mockReset()
    setAuthFixture({ id: "schedule-cache-test-user" } as UserState)
    getDatabaseMock.mockResolvedValue({
      schedule: { bulkUpsert: vi.fn().mockResolvedValue(undefined) },
    } as never)
  })

  afterEach(() => {
    vi.useRealTimers()
    cleanup()
    useAuthStore.setState({ user: null, loading: true })
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

    setAuthFixture({ id: "u1", role: "admin", group_id: null } as UserState)

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

    setAuthFixture({ id: "u1", role: "student", group_id: "group-2" } as UserState)

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

    setAuthFixture({ id: "u1", role: "student", group_id: "group-MISSING" } as UserState)

    apiGetMock.mockResolvedValueOnce({ data: [], status: 200 })

    const { result } = renderHook(() => useScheduleData(), { wrapper: wrapper(client) })

    await waitFor(() => {
      // Auto-select falls back to groups[0] since user.group_id doesn't exist.
      expect(result.current.selectedGroup).toBe("group-1")
    })
  })

  it("does not select a group while the available group list is empty", async () => {
    const client = newClient()
    client.setQueryData(scheduleGroupsQueryOptions().queryKey, [])
    setAuthFixture({ id: "u-empty", role: "admin", group_id: null } as UserState)

    const { result } = renderHook(() => useScheduleData(), { wrapper: wrapper(client) })

    await waitFor(() => expect(result.current.groups).toEqual([]))
    expect(result.current.selectedGroup).toBeNull()
  })

  it("schedule queryKey matches pageScheduleQueryOptions(groupId) shape", () => {
    const opts = pageScheduleQueryOptions("group-test")
    expect(opts.queryKey).toEqual(["schedule", "group", "group-test"])
  })

  it("groups queryKey shape preserved across factory refactor (cache identity)", () => {
    const opts = scheduleGroupsQueryOptions()
    expect(opts.queryKey).toEqual(["schedule", "groups"])
  })

  /**
   * Wave 133 SW3 — full-SSR loader integration test. Asserts the cache-
   * identity invariant for the new sequential prefetch chain:
   *   Loader: ensureQueryData(currentUserQueryOptions())
   *         + ensureQueryData(scheduleGroupsQueryOptions())
   *         + ensureQueryData(pageScheduleQueryOptions(user.group_id))
   * Pre-populating all three cache slots BEFORE useScheduleData renders
   * should yield zero network calls — full SSR-rendered schedule.
   */
  it("Wave 133 SW3 — reads SSR-prefetched lessons cache for user's group without re-fetching network", async () => {
    const groups: ScheduleGroup[] = [
      { id: "group-A", name: "Group A" },
      { id: "group-B", name: "Group B" },
    ]
    const lessons: Lesson[] = [
      {
        id: "lesson-1",
        group_id: "group-A",
        weekday: "monday",
        start_time: "09:00",
        end_time: "10:30",
        subject: "Math",
        teacher: "Dr. Smith",
        room: "101",
        lesson_type: "lecture",
        parity: "both",
      },
    ]
    const client = newClient()

    // Simulate SSR loader's three ensureQueryData calls populating the cache.
    client.setQueryData(currentUserQueryOptions().queryKey, {
      id: "u1",
      role: "student",
      group_id: "group-A",
    })
    client.setQueryData(scheduleGroupsQueryOptions().queryKey, groups)
    client.setQueryData(pageScheduleQueryOptions("group-A").queryKey, lessons)

    // useAuth mirrors what AuthProvider would surface from /users/me on hydration.
    setAuthFixture({ id: "u1", role: "student", group_id: "group-A" } as UserState)

    const { result } = renderHook(() => useScheduleData(), { wrapper: wrapper(client) })

    await waitFor(() => {
      expect(result.current.groups).toEqual(groups)
      expect(result.current.selectedGroup).toBe("group-A")
      // useScheduleData exposes prefetched lessons as `rawSchedule` (raw query
      // payload) + `schedule` (parity-filtered subset). Asserting `rawSchedule`
      // matches the SSR-prefetched lessons confirms cache identity.
      expect(result.current.rawSchedule).toEqual(lessons)
    })

    // Critical assertion: NO network calls. All three cache slots consumed.
    expect(apiGetMock).not.toHaveBeenCalled()
  })

  it("persists object-shaped fields and applies optimistic updates with refresh", async () => {
    const groups: ScheduleGroup[] = [{ id: "group-object", name: "Object Group" }]
    const lessons = [
      {
        id: "lesson-object",
        group_id: "group-object",
        weekday: "monday",
        start_time: "09:00",
        end_time: "10:30",
        subject: { name: "Object subject" },
        teacher: { name: "Object teacher" },
        room: 101,
        building: { name: "Main" },
        lesson_type: "lecture",
        parity: "both",
      },
      {
        id: "lesson-empty-object",
        group_id: "group-object",
        weekday: "tuesday",
        start_time: "11:00",
        end_time: "12:30",
        subject: {},
        teacher: {},
        room: "202",
        building: "North",
        lesson_type: "seminar",
        parity: "odd",
      },
      {
        id: "lesson-empty-name",
        group_id: "group-object",
        weekday: "wednesday",
        start_time: "13:00",
        end_time: "14:30",
        subject: { name: undefined },
        teacher: { name: undefined },
        room: "303",
        building: "South",
        lesson_type: "lab",
        parity: "even",
      },
    ] as unknown as Lesson[]
    const client = newClient()
    client.setQueryData(scheduleGroupsQueryOptions().queryKey, groups)
    client.setQueryData(pageScheduleQueryOptions("group-object").queryKey, lessons)

    const bulkUpsert = vi.fn().mockResolvedValue(undefined)
    getDatabaseMock.mockResolvedValue({ schedule: { bulkUpsert } } as never)
    setAuthFixture({ id: "u-object", role: "student", group_id: "group-object" } as UserState)

    const { result } = renderHook(() => useScheduleData(), { wrapper: wrapper(client) })

    await waitFor(() => {
      expect(result.current.selectedGroup).toBe("group-object")
      expect(result.current.rawSchedule).toHaveLength(3)
    })
    await waitFor(() => expect(bulkUpsert).toHaveBeenCalledOnce())

    expect(bulkUpsert).toHaveBeenCalledWith(
      expect.arrayContaining([
        expect.objectContaining({
          subject: "Object subject",
          teacher: "Object teacher",
          room: "101",
          building: "[object Object]",
        }),
        expect.objectContaining({
          subject: "[object Object]",
          teacher: "[object Object]",
          room: "202",
          building: "North",
        }),
        expect.objectContaining({ subject: "", teacher: "", room: "303", building: "South" }),
      ])
    )

    await act(async () => {
      result.current.applyScheduleUpdate((previous) => [
        ...previous,
        { ...lessons[0]!, id: "lesson-added", parity: "both" },
      ])
    })
    expect(client.getQueryData(pageScheduleQueryOptions("group-object").queryKey)).toHaveLength(4)

    const invalidateQueries = vi.spyOn(client, "invalidateQueries")
    act(() => {
      result.current.refresh()
    })
    expect(invalidateQueries).toHaveBeenCalledWith({
      queryKey: pageScheduleQueryOptions("group-object").queryKey,
    })
  })

  it("skips unknown calendar days and safely handles empty optimistic cache", async () => {
    const groups: ScheduleGroup[] = [{ id: "group-defensive", name: "Defensive Group" }]
    const lessons: Lesson[] = [
      {
        id: "lesson-sunday",
        group_id: "group-defensive",
        weekday: "sunday",
        start_time: "09:00",
        end_time: "10:00",
        subject: "Sunday lesson",
        teacher: "Dr. Sunday",
        room: "101",
        lesson_type: "lecture",
        parity: "both",
      },
      {
        id: "lesson-unknown-day",
        group_id: "group-defensive",
        weekday: "not-a-weekday",
        start_time: "11:00",
        end_time: "12:00",
        subject: "Unknown day",
        teacher: "Dr. Unknown",
        room: "102",
        lesson_type: "seminar",
        parity: "both",
      },
    ]
    const client = newClient()
    client.setQueryData(scheduleGroupsQueryOptions().queryKey, groups)
    client.setQueryData(pageScheduleQueryOptions("group-defensive").queryKey, lessons)
    setAuthFixture({ id: "u-defensive", role: "student", group_id: "group-defensive" } as UserState)

    const { result } = renderHook(() => useScheduleData(), { wrapper: wrapper(client) })

    await waitFor(() => {
      expect(result.current.selectedGroup).toBe("group-defensive")
      expect(result.current.rawSchedule).toHaveLength(2)
    })

    const scheduleKey = pageScheduleQueryOptions("group-defensive").queryKey
    client.setQueryData(scheduleKey, null)
    await waitFor(() => expect(result.current.rawSchedule).toEqual([]))

    act(() => {
      result.current.applyScheduleUpdate((previous) => [
        ...previous,
        { ...lessons[0]!, id: "lesson-added-after-empty-cache" },
      ])
    })
    expect(client.getQueryData(scheduleKey)).toEqual([
      expect.objectContaining({ id: "lesson-added-after-empty-cache" }),
    ])

    const noGroupClient = newClient()
    act(() => setAuthFixture(null))
    noGroupClient.setQueryData(scheduleGroupsQueryOptions(true).queryKey, [])
    const noGroup = renderHook(() => useScheduleData(), { wrapper: wrapper(noGroupClient) })
    expect(() => {
      noGroup.result.current.applyScheduleUpdate((previous) => previous)
      noGroup.result.current.refresh()
    }).not.toThrow()
  })

  it("normalizes falsy persistence fields and skips today calculations on Sunday", async () => {
    vi.useFakeTimers({ toFake: ["Date"] })
    vi.setSystemTime(new Date("2026-08-09T12:00:00.000Z"))

    const groups: ScheduleGroup[] = [{ id: "group-falsy", name: "Falsy Group" }]
    const lessons = [
      {
        id: undefined,
        group_id: "group-falsy",
        weekday: "monday",
        start_time: undefined,
        end_time: null,
        subject: 0,
        teacher: null,
        room: 0,
        building: null,
        lesson_type: undefined,
        parity: undefined,
      },
    ] as unknown as Lesson[]
    const client = newClient()
    client.setQueryData(scheduleGroupsQueryOptions().queryKey, groups)
    client.setQueryData(pageScheduleQueryOptions("group-falsy").queryKey, lessons)
    const bulkUpsert = vi.fn().mockResolvedValue(undefined)
    getDatabaseMock.mockResolvedValue({ schedule: { bulkUpsert } } as never)
    setAuthFixture({ id: "u-falsy", role: "student", group_id: "group-falsy" } as UserState)

    const { result } = renderHook(() => useScheduleData(), { wrapper: wrapper(client) })

    await waitFor(() => {
      expect(result.current.selectedGroup).toBe("group-falsy")
      expect(result.current.rawSchedule).toHaveLength(1)
      expect(result.current.hasToday).toBe(false)
      expect(result.current.todayLessons).toEqual([])
    })
    await waitFor(() => expect(bulkUpsert).toHaveBeenCalledOnce())

    expect(bulkUpsert).toHaveBeenCalledWith([
      expect.objectContaining({
        id: "",
        subject: "0",
        teacher: "",
        room: "0",
        building: "",
        start_time: "",
        end_time: "",
        parity: "both",
        lesson_type: "lecture",
      }),
    ])
  })

  it("sorts the current weekday lessons and excludes parity mismatches", async () => {
    vi.useFakeTimers({ toFake: ["Date"] })
    vi.setSystemTime(new Date("2026-08-15T12:00:00.000Z"))

    const groups: ScheduleGroup[] = [{ id: "group-today", name: "Today Group" }]
    const lessons: Lesson[] = [
      {
        id: "later",
        group_id: "group-today",
        weekday: "saturday",
        start_time: "11:00",
        end_time: "12:00",
        subject: "Later",
        teacher: "Teacher",
        room: "2",
        lesson_type: "lecture",
        parity: "both",
      },
      {
        id: "earlier",
        group_id: "group-today",
        weekday: "saturday",
        start_time: "09:00",
        end_time: "10:00",
        subject: "Earlier",
        teacher: "Teacher",
        room: "1",
        lesson_type: "lecture",
        parity: "both",
      },
      {
        id: "other-parity",
        group_id: "group-today",
        weekday: "saturday",
        start_time: "08:00",
        end_time: "09:00",
        subject: "Other parity",
        teacher: "Teacher",
        room: "0",
        lesson_type: "lecture",
        parity: "even",
      },
    ]
    const client = newClient()
    client.setQueryData(scheduleGroupsQueryOptions().queryKey, groups)
    client.setQueryData(pageScheduleQueryOptions("group-today").queryKey, lessons)
    setAuthFixture({ id: "u-today", role: "student", group_id: "group-today" } as UserState)

    const { result } = renderHook(() => useScheduleData(), { wrapper: wrapper(client) })

    await waitFor(() => expect(result.current.selectedGroup).toBe("group-today"))
    expect(result.current.hasToday).toBe(true)
    expect(result.current.todayLessons.map((lesson) => lesson.id)).toEqual(["earlier", "later"])
  })

  it("starts on the parity of the current ISO week, not always the odd week", async () => {
    vi.useFakeTimers({ toFake: ["Date"] })
    // 2026-08-19 is a Wednesday in ISO week 34, an even week.
    vi.setSystemTime(new Date("2026-08-19T12:00:00.000Z"))

    const groups: ScheduleGroup[] = [{ id: "group-even", name: "Even Group" }]
    const lessons: Lesson[] = [
      {
        id: "odd-only",
        group_id: "group-even",
        weekday: "wednesday",
        start_time: "09:00",
        end_time: "10:00",
        subject: "Odd week",
        teacher: "Teacher",
        room: "1",
        lesson_type: "lecture",
        parity: "odd",
      },
      {
        id: "even-only",
        group_id: "group-even",
        weekday: "wednesday",
        start_time: "11:00",
        end_time: "12:00",
        subject: "Even week",
        teacher: "Teacher",
        room: "2",
        lesson_type: "lecture",
        parity: "even",
      },
    ]
    const client = newClient()
    client.setQueryData(scheduleGroupsQueryOptions().queryKey, groups)
    client.setQueryData(pageScheduleQueryOptions("group-even").queryKey, lessons)
    setAuthFixture({ id: "u-even", role: "student", group_id: "group-even" } as UserState)

    const { result } = renderHook(() => useScheduleData(), { wrapper: wrapper(client) })

    await waitFor(() => expect(result.current.selectedGroup).toBe("group-even"))
    expect(result.current.currentParity).toBe("even")
    expect(result.current.todayLessons.map((lesson) => lesson.id)).toEqual(["even-only"])
  })

  it.each([
    { timeZone: "UTC", parity: "even" },
    { timeZone: "Europe/Moscow", parity: "odd" },
  ])("initializes parity in the configured campus zone $timeZone", async ({ timeZone, parity }) => {
    vi.useFakeTimers({ toFake: ["Date"] })
    // The same instant is Sunday/week 42 in UTC and Monday/week 43 in Moscow.
    vi.setSystemTime(new Date("2026-10-18T21:30:00.000Z"))
    const groups: ScheduleGroup[] = [{ id: "group-boundary", name: "Boundary" }]
    const lessons: Lesson[] = [
      {
        id: "odd-only",
        group_id: "group-boundary",
        weekday: "monday",
        start_time: "09:00",
        end_time: "10:00",
        subject: "Odd week",
        teacher: "Teacher",
        room: "1",
        lesson_type: "lecture",
        parity: "odd",
      },
      {
        id: "even-only",
        group_id: "group-boundary",
        weekday: "monday",
        start_time: "11:00",
        end_time: "12:00",
        subject: "Even week",
        teacher: "Teacher",
        room: "2",
        lesson_type: "lecture",
        parity: "even",
      },
    ]
    const client = newClient()
    client.setQueryData(scheduleGroupsQueryOptions().queryKey, groups)
    client.setQueryData(pageScheduleQueryOptions("group-boundary").queryKey, lessons)
    setAuthFixture({ id: "u-boundary", role: "student", group_id: "group-boundary" } as UserState)

    const { result } = renderHook(() => useScheduleData(), {
      wrapper: ({ children }: { children: ReactNode }) => (
        <QueryClientProvider client={client}>
          <CampusTimezoneProvider timeZone={timeZone}>{children}</CampusTimezoneProvider>
        </QueryClientProvider>
      ),
    })

    await waitFor(() => expect(result.current.selectedGroup).toBe("group-boundary"))
    expect(result.current.currentParity).toBe(parity)
    expect(result.current.schedule.map((lesson) => lesson.id)).toEqual([parity + "-only"])
  })

  it("lists lesson days for the month the mini-calendar shows, not only today", async () => {
    vi.useFakeTimers({ toFake: ["Date"] })
    vi.setSystemTime(new Date("2026-08-15T12:00:00.000Z"))

    const groups: ScheduleGroup[] = [{ id: "group-cal", name: "Calendar Group" }]
    const lessons: Lesson[] = [
      {
        id: "monday",
        group_id: "group-cal",
        weekday: "monday",
        start_time: "09:00",
        end_time: "10:00",
        subject: "Weekly",
        teacher: "Teacher",
        room: "1",
        lesson_type: "lecture",
        parity: "both",
      },
      {
        id: "unknown-weekday",
        group_id: "group-cal",
        weekday: "not-a-weekday",
        start_time: "09:00",
        end_time: "10:00",
        subject: "Ignored",
        teacher: "Teacher",
        room: "2",
        lesson_type: "lecture",
        parity: "both",
      },
    ]
    const client = newClient()
    client.setQueryData(scheduleGroupsQueryOptions().queryKey, groups)
    client.setQueryData(pageScheduleQueryOptions("group-cal").queryKey, lessons)
    setAuthFixture({ id: "u-cal", role: "student", group_id: "group-cal" } as UserState)

    const { result } = renderHook(() => useScheduleData(), { wrapper: wrapper(client) })

    await waitFor(() => expect(result.current.selectedGroup).toBe("group-cal"))
    // September 2026: the Mondays are the 7th, 14th, 21st and 28th.
    const september = [...result.current.lessonDaysForMonth(new Date(2026, 8, 1))]
    expect(september.sort((a, b) => a - b)).toEqual([7, 14, 21, 28])
  })

  it("normalizes nullish persistence fields without throwing", async () => {
    const groups: ScheduleGroup[] = [{ id: "group-nullish", name: "Nullish Group" }]
    const lessons = [
      {
        id: "lesson-nullish",
        group_id: "group-nullish",
        weekday: null,
        start_time: null,
        end_time: undefined,
        subject: null,
        teacher: undefined,
        room: null,
        building: undefined,
        lesson_type: null,
        parity: null,
      },
    ] as unknown as Lesson[]
    const client = newClient()
    client.setQueryData(scheduleGroupsQueryOptions().queryKey, groups)
    client.setQueryData(pageScheduleQueryOptions("group-nullish").queryKey, lessons)
    const bulkUpsert = vi.fn().mockResolvedValue(undefined)
    getDatabaseMock.mockResolvedValue({ schedule: { bulkUpsert } } as never)
    setAuthFixture({ id: "u-nullish", role: "student", group_id: "group-nullish" } as UserState)

    const { result } = renderHook(() => useScheduleData(), { wrapper: wrapper(client) })

    await waitFor(() => {
      expect(result.current.selectedGroup).toBe("group-nullish")
      expect(result.current.rawSchedule).toEqual(lessons)
    })
    await waitFor(() => expect(bulkUpsert).toHaveBeenCalledOnce())

    expect(bulkUpsert).toHaveBeenCalledWith([
      expect.objectContaining({
        weekday: "",
        start_time: "",
        end_time: "",
        subject: "",
        teacher: "",
        room: "",
        building: "",
        parity: "both",
        lesson_type: "lecture",
      }),
    ])
  })

  it("swallows both database-open and bulk-persistence failures", async () => {
    const lesson = {
      id: "lesson-failure",
      group_id: "group-failure",
      weekday: "monday",
      start_time: "09:00",
      end_time: "10:00",
      subject: "Failure-safe",
      teacher: "Teacher",
      room: "1",
      building: "Main",
      parity: "both",
      lesson_type: "lecture",
    } as Lesson
    const groups: ScheduleGroup[] = [{ id: "group-failure", name: "Failure Group" }]
    setAuthFixture({ id: "u-failure", role: "student", group_id: "group-failure" } as UserState)

    const firstClient = newClient()
    firstClient.setQueryData(scheduleGroupsQueryOptions().queryKey, groups)
    firstClient.setQueryData(pageScheduleQueryOptions("group-failure").queryKey, [lesson])
    const bulkUpsert = vi.fn().mockRejectedValue(new Error("write failed"))
    getDatabaseMock.mockResolvedValueOnce({ schedule: { bulkUpsert } } as never)
    const first = renderHook(() => useScheduleData(), { wrapper: wrapper(firstClient) })
    await waitFor(() => expect(bulkUpsert).toHaveBeenCalledOnce())
    first.unmount()

    const secondClient = newClient()
    secondClient.setQueryData(scheduleGroupsQueryOptions().queryKey, groups)
    secondClient.setQueryData(pageScheduleQueryOptions("group-failure").queryKey, [lesson])
    getDatabaseMock.mockRejectedValueOnce(new Error("database unavailable"))
    const second = renderHook(() => useScheduleData(), { wrapper: wrapper(secondClient) })
    await waitFor(() => expect(getDatabaseMock).toHaveBeenCalledTimes(2))
    expect(second.result.current.rawSchedule).toEqual([lesson])
  })

  it.each([
    { zone: "UTC", parity: "even", day: -1, today: [], current: null, next: null },
    {
      zone: "Europe/Moscow",
      parity: "odd",
      day: 0,
      today: ["odd-early", "odd-late"],
      current: "odd-early",
      next: "odd-late",
    },
  ])("uses the $zone campus day and clock at the week boundary", async (expected) => {
    vi.useFakeTimers({ toFake: ["Date"] })
    vi.setSystemTime(new Date("2026-10-18T21:30:00Z"))
    const groupId = "campus-boundary"
    const client = campusBoundaryClient(groupId)
    const { result } = renderHook(() => useScheduleData(), {
      wrapper: ({ children }: { children: ReactNode }) => (
        <QueryClientProvider client={client}>
          <CampusTimezoneProvider timeZone={expected.zone}>{children}</CampusTimezoneProvider>
        </QueryClientProvider>
      ),
    })

    await waitFor(() => expect(result.current.selectedGroup).toBe(groupId))
    expect(result.current.currentParity).toBe(expected.parity)
    expect(result.current.todayIdx).toBe(expected.day)
    expect(result.current.hasToday).toBe(expected.day >= 0)
    expect(result.current.todayLessons.map((lesson) => lesson.id)).toEqual(expected.today)
    expect(result.current.currentLesson?.id ?? null).toBe(expected.current)
    expect(result.current.nextLesson?.id ?? null).toBe(expected.next)
  })

  it("updates automatic parity after campus timezone resolution and refresh", async () => {
    vi.useFakeTimers({ toFake: ["Date"] })
    vi.setSystemTime(new Date("2026-10-18T21:30:00Z"))
    const groupId = "campus-refresh"
    const client = campusBoundaryClient(groupId)
    let timeZone: string | null = null
    const contextWrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={client}>
        <CampusTimezoneProvider timeZone={timeZone}>{children}</CampusTimezoneProvider>
      </QueryClientProvider>
    )
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ campus_timezone: "UTC" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      })
    )
    try {
      const { result, rerender } = renderHook(
        () => ({ data: useScheduleData(), timeZone: useCampusTimezone() }),
        { wrapper: contextWrapper }
      )
      await waitFor(() => {
        expect(result.current.timeZone).toBe("UTC")
        expect(result.current.data.selectedGroup).toBe(groupId)
        expect(result.current.data.currentParity).toBe("even")
      })

      timeZone = "Europe/Moscow"
      rerender()
      await waitFor(() => {
        expect(result.current.timeZone).toBe("Europe/Moscow")
        expect(result.current.data.currentParity).toBe("odd")
      })
      expect(result.current.data.schedule.map((lesson) => lesson.id)).toEqual([
        "odd-early",
        "odd-late",
      ])
    } finally {
      fetchSpy.mockRestore()
    }
  })

  it("preserves an explicit current-parity choice and queued functional updates", async () => {
    vi.useFakeTimers({ toFake: ["Date"] })
    vi.setSystemTime(new Date("2026-10-18T21:30:00Z"))
    const groupId = "campus-manual"
    const client = campusBoundaryClient(groupId)
    let timeZone = "UTC"
    const contextWrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={client}>
        <CampusTimezoneProvider timeZone={timeZone}>{children}</CampusTimezoneProvider>
      </QueryClientProvider>
    )
    const { result, rerender } = renderHook(() => useScheduleData(), { wrapper: contextWrapper })
    await waitFor(() => {
      expect(result.current.selectedGroup).toBe(groupId)
      expect(result.current.currentParity).toBe("even")
    })

    act(() => result.current.setCurrentParity((previous) => previous))
    timeZone = "Europe/Moscow"
    rerender()
    expect(result.current.currentParity).toBe("even")
    expect(result.current.schedule.map((lesson) => lesson.id)).toEqual(["even-only"])

    act(() => {
      result.current.setCurrentParity((previous) => (previous === "even" ? "odd" : "even"))
      result.current.setCurrentParity((previous) => (previous === "even" ? "odd" : "even"))
    })
    expect(result.current.currentParity).toBe("even")

    act(() => result.current.setCurrentParity("odd"))
    expect(result.current.currentParity).toBe("odd")
    expect(result.current.schedule.map((lesson) => lesson.id)).toEqual(["odd-early", "odd-late"])
  })

  it.each([
    { zone: "UTC", parity: "even", day: -1, today: [], next: null },
    {
      zone: "Europe/Moscow",
      parity: "odd",
      day: 0,
      today: ["odd-early", "odd-late"],
      next: "odd-early",
    },
  ])("refreshes the $zone campus date after a hidden boundary", async (expected) => {
    vi.useFakeTimers({ toFake: ["Date", "setInterval", "clearInterval"] })
    vi.setSystemTime(new Date("2026-10-18T20:59:30Z"))
    const groupId = "campus-midnight"
    const client = campusBoundaryClient(groupId)
    const originalVisibility = Object.getOwnPropertyDescriptor(document, "visibilityState")
    let visibility: DocumentVisibilityState = "hidden"
    let unmount: (() => void) | undefined
    try {
      Object.defineProperty(document, "visibilityState", {
        configurable: true,
        get: () => visibility,
      })
      const rendered = renderHook(() => useScheduleData(), {
        wrapper: ({ children }: { children: ReactNode }) => (
          <QueryClientProvider client={client}>
            <CampusTimezoneProvider timeZone={expected.zone}>{children}</CampusTimezoneProvider>
          </QueryClientProvider>
        ),
      })
      unmount = rendered.unmount
      await waitFor(() => expect(rendered.result.current.selectedGroup).toBe(groupId))
      expect(rendered.result.current.currentParity).toBe("even")
      expect(rendered.result.current.todayIdx).toBe(-1)
      expect(rendered.result.current.hasToday).toBe(false)

      await act(async () => {
        vi.advanceTimersByTime(30_000)
      })
      expect(rendered.result.current.todayIdx).toBe(-1)
      visibility = "visible"
      act(() => document.dispatchEvent(new Event("visibilitychange")))

      await waitFor(() => {
        expect(rendered.result.current.currentParity).toBe(expected.parity)
        expect(rendered.result.current.todayIdx).toBe(expected.day)
      })
      expect(rendered.result.current.hasToday).toBe(expected.day >= 0)
      const today = rendered.result.current.todayLessons.map((lesson) => lesson.id)
      expect(today).toEqual(expected.today)
      expect(rendered.result.current.currentLesson).toBeNull()
      expect(rendered.result.current.nextLesson?.id ?? null).toBe(expected.next)
    } finally {
      unmount?.()
      if (originalVisibility) {
        Object.defineProperty(document, "visibilityState", originalVisibility)
      } else {
        Reflect.deleteProperty(document, "visibilityState")
      }
      vi.useRealTimers()
    }
  })
})
