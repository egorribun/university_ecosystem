import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { act, renderHook, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { useNotifications } from "../useNotifications"
import type { NotificationEntry, NotificationsListResult } from "@/api/notifications"

const { generatedCheckSchedule, logWarning } = vi.hoisted(() => ({
  generatedCheckSchedule: vi.fn(),
  logWarning: vi.fn(),
}))

vi.mock("@/app/logger", () => ({ logWarning }))
vi.mock("@/api/generated", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/api/generated")>()),
  checkScheduleAndGenerateApiV1NotificationsCheckSchedulePost: generatedCheckSchedule,
}))

/**
 * useNotifications — list query + markRead/markAll/clearAll mutations +
 * cursor-paginated fetchMore (merge + dedup) + a mount-time checkSchedule
 * side effect.
 *
 * `@/api/notifications` is module-mocked, so the network never fires and the
 * setupTests contract validator (which only runs on MSW `response:mocked`
 * events) is never engaged — this is why the hook can be driven deterministically
 * here where s11 had to defer it. Coverage of the hook's own logic (normalize,
 * mutation callbacks, the fetchMore setQueryData merge/dedup) is unaffected by
 * the module being mocked: the hook code still executes.
 */

vi.mock("@/api/notifications", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/api/notifications")>()),
  fetchNotificationsList: vi.fn(),
  markNotificationRead: vi.fn(),
  markAllNotificationsRead: vi.fn(),
  clearNotifications: vi.fn(),
}))

import {
  clearNotifications,
  fetchNotificationsList,
  markAllNotificationsRead,
  markNotificationRead,
} from "@/api/notifications"

const entry = (id: string, over: Partial<NotificationEntry> = {}): NotificationEntry => ({
  id,
  title: `Notification ${id}`,
  body: null,
  title_en: null,
  body_en: null,
  type: null,
  url: `/notifications/${id}`,
  created_at: "2026-01-01T00:00:00Z",
  read: false,
  read_at: null,
  ...over,
})

const listResult = (
  items: NotificationEntry[],
  over: Partial<NotificationsListResult> = {}
): NotificationsListResult => ({
  items,
  unread_count: items.filter((i) => !i.read).length,
  has_more: false,
  next_cursor: null,
  ...over,
})

const checkScheduleSuccess = {
  data: { items: [], unread_count: 0, has_more: false, next_cursor: null },
  status: 200,
  statusText: "OK",
  headers: {},
  config: { headers: {} },
  request: {},
  error: undefined,
}

function setup() {
  const qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false, refetchOnWindowFocus: false },
      mutations: { retry: false },
    },
  })
  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  )
  return { qc, ...renderHook(() => useNotifications(), { wrapper }) }
}

beforeEach(() => {
  vi.clearAllMocks()
  generatedCheckSchedule.mockResolvedValue(checkScheduleSuccess)
  vi.mocked(markNotificationRead).mockResolvedValue(undefined as never)
  vi.mocked(markAllNotificationsRead).mockResolvedValue(undefined as never)
  vi.mocked(clearNotifications).mockResolvedValue(undefined as never)
})

describe("useNotifications — list query", () => {
  it("normalizes the list response (url→link, unread_count→unreadCount, paging)", async () => {
    vi.mocked(fetchNotificationsList).mockResolvedValue(
      listResult([entry("1"), entry("2", { read: true, url: null })], {
        has_more: true,
        next_cursor: "cursor-2",
      })
    )
    const { result } = setup()
    await waitFor(() => expect(result.current.isLoading).toBe(false))

    expect(result.current.data).toHaveLength(2)
    expect(result.current.data[0]!.link).toBe("/notifications/1")
    expect(result.current.data[1]!.link).toBeUndefined()
    expect(result.current.unreadCount).toBe(1)
    expect(result.current.hasMore).toBe(true)
    expect(result.current.nextCursor).toBe("cursor-2")
  })

  it("checks the schedule exactly once on mount", async () => {
    vi.mocked(fetchNotificationsList).mockResolvedValue(listResult([]))
    const { result } = setup()
    await waitFor(() => expect(result.current.isLoading).toBe(false))
    expect(generatedCheckSchedule).toHaveBeenCalledTimes(1)
  })

  it("contains and reports a fulfilled SDK schedule error through the real wrapper", async () => {
    const failure = { detail: [{ loc: ["query"], msg: "invalid", type: "validation" }] }
    generatedCheckSchedule.mockResolvedValueOnce({
      data: undefined,
      error: failure,
      name: "AxiosError",
      message: "Request failed with status code 422",
      code: "ERR_BAD_REQUEST",
      config: { headers: {} },
      request: {},
      response: {
        data: failure,
        status: 422,
        statusText: "Unprocessable Entity",
        headers: {},
        config: { headers: {} },
      },
      status: 422,
      isAxiosError: true,
      toJSON: () => ({}),
    })
    vi.mocked(fetchNotificationsList).mockResolvedValue(listResult([]))

    const { result } = setup()
    await waitFor(() => expect(result.current.isLoading).toBe(false))
    await waitFor(() =>
      expect(logWarning).toHaveBeenCalledWith("Failed to generate schedule notifications", failure)
    )
  })

  it("surfaces an error when the list request rejects", async () => {
    vi.mocked(fetchNotificationsList).mockRejectedValue(new Error("boom"))
    const { result } = setup()
    await waitFor(() => expect(result.current.isError).toBe(true))
    expect(result.current.data).toEqual([])
    expect(result.current.unreadCount).toBe(0)
  })
})

describe("useNotifications — mutations invalidate the list", () => {
  it("markRead calls the API with the id and refetches the list", async () => {
    vi.mocked(fetchNotificationsList).mockResolvedValue(listResult([entry("1")]))
    const { result } = setup()
    await waitFor(() => expect(result.current.isLoading).toBe(false))

    act(() => result.current.markRead("1"))
    await waitFor(() => expect(markNotificationRead).toHaveBeenCalledWith("1"))
    await waitFor(() => expect(fetchNotificationsList).toHaveBeenCalledTimes(2))
  })

  it("markAll calls the API and refetches the list", async () => {
    vi.mocked(fetchNotificationsList).mockResolvedValue(listResult([entry("1")]))
    const { result } = setup()
    await waitFor(() => expect(result.current.isLoading).toBe(false))

    act(() => result.current.markAll())
    await waitFor(() => expect(markAllNotificationsRead).toHaveBeenCalledTimes(1))
    await waitFor(() => expect(fetchNotificationsList).toHaveBeenCalledTimes(2))
  })

  it("clearAll calls the API and refetches the list", async () => {
    vi.mocked(fetchNotificationsList).mockResolvedValue(listResult([entry("1")]))
    const { result } = setup()
    await waitFor(() => expect(result.current.isLoading).toBe(false))

    act(() => result.current.clearAll())
    await waitFor(() => expect(clearNotifications).toHaveBeenCalledTimes(1))
    await waitFor(() => expect(fetchNotificationsList).toHaveBeenCalledTimes(2))
  })
})

describe("useNotifications — fetchMore", () => {
  it("merges the next page and deduplicates by id", async () => {
    // Cursor-keyed so the result is independent of call count / refetch timing.
    vi.mocked(fetchNotificationsList).mockImplementation((params) =>
      params?.cursor === "c1"
        ? Promise.resolve(
            listResult([entry("2"), entry("3")], { has_more: false, unread_count: 0 })
          )
        : Promise.resolve(
            listResult([entry("1"), entry("2")], { has_more: true, next_cursor: "c1" })
          )
    )
    const { result } = setup()
    await waitFor(() => expect(result.current.data).toHaveLength(2))

    await act(async () => {
      await result.current.fetchMore("c1")
    })

    await waitFor(() => expect(result.current.data.map((i) => i.id)).toEqual(["1", "2", "3"]))
    expect(result.current.hasMore).toBe(false)
    expect(result.current.unreadCount).toBe(0)
    expect(result.current.nextCursor).toBeNull()
    expect(fetchNotificationsList).toHaveBeenLastCalledWith({ cursor: "c1" })
  })

  it("stores the page as-is when the cache is empty (no prior list)", async () => {
    // Initial list rejects → cache holds no data; the fetchMore merge takes the
    // `!current` early-return branch and stores the page verbatim.
    vi.mocked(fetchNotificationsList).mockImplementation((params) =>
      params?.cursor === "seed"
        ? Promise.resolve(listResult([entry("9"), entry("10")]))
        : Promise.reject(new Error("no initial list"))
    )
    const { result } = setup()
    await waitFor(() => expect(result.current.isError).toBe(true))

    await act(async () => {
      await result.current.fetchMore("seed")
    })

    await waitFor(() => expect(result.current.data.map((i) => i.id)).toEqual(["9", "10"]))
  })

  it("is a no-op when called without a cursor", async () => {
    vi.mocked(fetchNotificationsList).mockResolvedValue(listResult([entry("1")]))
    const { result } = setup()
    await waitFor(() => expect(result.current.isLoading).toBe(false))

    await act(async () => {
      await result.current.fetchMore()
    })
    await act(async () => {
      await result.current.fetchMore(null)
    })

    expect(fetchNotificationsList).toHaveBeenCalledTimes(1)
    expect(result.current.isFetchingMore).toBe(false)
  })
})
