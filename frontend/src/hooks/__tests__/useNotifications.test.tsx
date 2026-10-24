import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { act, renderHook, waitFor } from "@testing-library/react"
import { renderToString } from "react-dom/server"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { useAuthStore } from "@/stores/useAuthStore"
import { acceptBrowserSessionGeneration } from "@/stores/sessionEpoch"
import type { UserState } from "@/types/Auth"
import { useNotifications } from "../useNotifications"
import { navigateAfterNotificationRead } from "@/components/feedback/NotificationsBell"
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
  localStorage.clear()
  acceptBrowserSessionGeneration()
  vi.clearAllMocks()
  useAuthStore.setState({
    user: { id: "notifications-test-user" } as UserState,
    loading: false,
  })
  generatedCheckSchedule.mockResolvedValue(checkScheduleSuccess)
  vi.mocked(markNotificationRead).mockResolvedValue(undefined as never)
  vi.mocked(markAllNotificationsRead).mockResolvedValue(undefined as never)
  vi.mocked(clearNotifications).mockResolvedValue(undefined as never)
})

describe("useNotifications — list query", () => {
  it("uses the stable server identity snapshot when rendered on the server", () => {
    function ServerProbe() {
      const notifications = useNotifications()
      return <span>{notifications.data.length}</span>
    }

    const markup = renderToString(
      <QueryClientProvider client={new QueryClient()}>
        <ServerProbe />
      </QueryClientProvider>
    )

    expect(markup).toContain("<span>0</span>")
  })

  it("invalidates once for duplicate live/Web Push messages with the same canonical id", async () => {
    vi.mocked(fetchNotificationsList).mockResolvedValue(listResult([]))
    const listeners = new Set<(event: MessageEvent) => void>()
    const serviceWorker = {
      addEventListener: vi.fn((_type: string, listener: (event: MessageEvent) => void) => {
        listeners.add(listener)
      }),
      removeEventListener: vi.fn((_type: string, listener: (event: MessageEvent) => void) => {
        listeners.delete(listener)
      }),
    }
    vi.stubGlobal("navigator", { ...navigator, serviceWorker })

    const { result, unmount } = setup()
    await waitFor(() => expect(result.current.isLoading).toBe(false))
    expect(fetchNotificationsList).toHaveBeenCalledTimes(1)

    const message = new MessageEvent("message", {
      data: {
        type: "PUSH_NOTIFICATION",
        notificationId: "018f10c0-0000-7000-8000-000000000001",
        recipientUserId: "notifications-test-user",
      },
    })
    for (const listener of listeners) listener(message)
    for (const listener of listeners) listener(message)

    await waitFor(() => expect(fetchNotificationsList).toHaveBeenCalledTimes(2))
    unmount()
    expect(serviceWorker.removeEventListener).toHaveBeenCalledOnce()
  })

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
    const failure = {
      detail: [{ loc: ["query"], msg: "invalid", type: "validation" }],
    }
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

describe("useNotifications — loaded pages survive a refetch", () => {
  it("keeps later pages after a mutation refetches the list", async () => {
    vi.mocked(fetchNotificationsList).mockImplementation((params) =>
      params?.cursor === "c1"
        ? Promise.resolve(listResult([entry("3")], { has_more: false }))
        : Promise.resolve(
            listResult([entry("1"), entry("2")], {
              has_more: true,
              next_cursor: "c1",
            })
          )
    )
    const { qc, result } = setup()
    await waitFor(() => expect(result.current.data).toHaveLength(2))
    await act(async () => {
      await result.current.fetchMore("c1")
    })
    await waitFor(() => expect(result.current.data.map((i) => i.id)).toEqual(["1", "2", "3"]))

    await act(async () => {
      await result.current.markRead("1")
    })

    // The refetch replays every loaded page, so the second page is requested again.
    await waitFor(() =>
      expect(vi.mocked(fetchNotificationsList).mock.calls.length).toBeGreaterThanOrEqual(4)
    )
    await waitFor(() => expect(qc.isFetching()).toBe(0))
    expect(result.current.data.map((i) => i.id)).toEqual(["1", "2", "3"])
    expect(result.current.hasMore).toBe(false)
  })
})

describe("useNotifications — mutations invalidate the list", () => {
  it("markRead calls the API with the id and refetches the list", async () => {
    vi.mocked(fetchNotificationsList).mockResolvedValue(listResult([entry("1")]))
    const { result } = setup()
    await waitFor(() => expect(result.current.isLoading).toBe(false))

    await act(async () => {
      await result.current.markRead("1")
    })
    await waitFor(() => expect(markNotificationRead).toHaveBeenCalledWith("1"))
    await waitFor(() => expect(fetchNotificationsList).toHaveBeenCalledTimes(2))
  })

  it("markAll calls the API and refetches the list", async () => {
    vi.mocked(fetchNotificationsList).mockResolvedValue(listResult([entry("1")]))
    const { result } = setup()
    await waitFor(() => expect(result.current.isLoading).toBe(false))

    await act(async () => {
      await result.current.markAll()
    })
    await waitFor(() => expect(markAllNotificationsRead).toHaveBeenCalledTimes(1))
    await waitFor(() => expect(fetchNotificationsList).toHaveBeenCalledTimes(2))
  })

  it("clearAll calls the API and refetches the list", async () => {
    vi.mocked(fetchNotificationsList).mockResolvedValue(listResult([entry("1")]))
    const { result } = setup()
    await waitFor(() => expect(result.current.isLoading).toBe(false))

    await act(async () => {
      await result.current.clearAll()
    })
    await waitFor(() => expect(clearNotifications).toHaveBeenCalledTimes(1))
    await waitFor(() => expect(fetchNotificationsList).toHaveBeenCalledTimes(2))
  })

  it("reports background invalidation failures without delaying a successful mutation", async () => {
    vi.mocked(fetchNotificationsList).mockResolvedValue(listResult([entry("1")]))
    const { qc, result } = setup()
    await waitFor(() => expect(result.current.isLoading).toBe(false))
    vi.spyOn(qc, "invalidateQueries").mockRejectedValueOnce(new Error("refetch failed"))

    await act(async () => {
      await result.current.markRead("1")
    })
    await waitFor(() =>
      expect(logWarning).toHaveBeenCalledWith(
        "Failed to refresh notifications after a mutation",
        new Error("refetch failed")
      )
    )
  })

  it.each(["markAll", "clearAll"] as const)(
    "%s obsoletes an earlier item-read failure and its retry target",
    async (operation) => {
      vi.mocked(fetchNotificationsList).mockResolvedValue(listResult([entry("1")]))
      vi.mocked(markNotificationRead).mockRejectedValueOnce(new Error("read failed"))
      const { result } = setup()
      await waitFor(() => expect(result.current.isLoading).toBe(false))

      await act(async () => {
        await result.current.markRead("1").catch(() => undefined)
      })
      await waitFor(() => expect(result.current.mutationFailures).toHaveLength(1))
      const obsoleteFailure = result.current.mutationFailures[0]!

      await act(async () => {
        await result.current[operation]()
      })

      expect(result.current.mutationFailures).toEqual([])
      await expect(result.current.retryMutationFailure(obsoleteFailure)).rejects.toThrow(
        "no longer current"
      )
    }
  )

  it("drops an account A failure and refuses its retry after switching to account B", async () => {
    vi.mocked(fetchNotificationsList).mockResolvedValue(listResult([entry("1")]))
    vi.mocked(markNotificationRead).mockRejectedValueOnce(new Error("request failed"))
    useAuthStore.setState({
      user: { id: "notifications-account-A" } as UserState,
      loading: false,
    })
    const { result } = setup()
    await waitFor(() => expect(result.current.isLoading).toBe(false))

    await act(async () => {
      await result.current.markRead("1").catch(() => undefined)
    })
    await waitFor(() => expect(result.current.mutationFailures).toHaveLength(1))
    const failedAccountAOperation = result.current.mutationFailures[0]!
    expect(failedAccountAOperation).toMatchObject({
      operation: "mark-read",
      ownerId: "notifications-account-A",
      notificationId: "1",
    })

    act(() => {
      useAuthStore.setState({
        user: { id: "notifications-account-B" } as UserState,
        loading: false,
      })
    })
    await waitFor(() => expect(result.current.mutationFailures).toHaveLength(0))
    await expect(result.current.retryMutationFailure(failedAccountAOperation)).rejects.toThrow(
      "account changed"
    )
    expect(markNotificationRead).toHaveBeenCalledTimes(1)
  })

  it("rejects callbacks captured under an old account and all actions without an account", async () => {
    vi.mocked(fetchNotificationsList).mockResolvedValue(listResult([entry("1")]))
    useAuthStore.setState({
      user: { id: "notifications-account-A" } as UserState,
      loading: false,
    })
    const { result } = setup()
    await waitFor(() => expect(result.current.isLoading).toBe(false))
    const markReadFromAccountA = result.current.markRead

    act(() => {
      useAuthStore.setState({
        user: { id: "notifications-account-B" } as UserState,
        loading: false,
      })
    })
    await expect(markReadFromAccountA("1")).rejects.toThrow("account changed")
    expect(markNotificationRead).not.toHaveBeenCalled()

    act(() => {
      useAuthStore.setState({ user: null, loading: false })
    })
    await waitFor(() => expect(result.current.mutationFailures).toHaveLength(0))
    await expect(result.current.markRead("1")).rejects.toThrow("account changed")
    await expect(result.current.markAll()).rejects.toThrow("account changed")
    await expect(result.current.clearAll()).rejects.toThrow("account changed")
    expect(markNotificationRead).not.toHaveBeenCalled()
    expect(markAllNotificationsRead).not.toHaveBeenCalled()
    expect(clearNotifications).not.toHaveBeenCalled()
  })

  it("expires an account failure when the same user returns under a new identity revision", async () => {
    vi.mocked(fetchNotificationsList).mockResolvedValue(listResult([entry("1")]))
    vi.mocked(markNotificationRead).mockRejectedValueOnce(new Error("request failed"))
    useAuthStore.setState({
      user: { id: "notifications-account-A" } as UserState,
      loading: false,
    })
    const { result } = setup()
    await waitFor(() => expect(result.current.isLoading).toBe(false))

    await act(async () => {
      await result.current.markRead("1").catch(() => undefined)
    })
    await waitFor(() => expect(result.current.mutationFailures).toHaveLength(1))
    const failedOperation = result.current.mutationFailures[0]!

    act(() => {
      useAuthStore.setState({
        user: { id: "notifications-account-B" } as UserState,
        loading: false,
      })
      useAuthStore.setState({
        user: { id: "notifications-account-A" } as UserState,
        loading: false,
      })
    })

    await waitFor(() => expect(result.current.mutationFailures).toHaveLength(0))
    await expect(result.current.retryMutationFailure(failedOperation)).rejects.toThrow(
      "account changed"
    )
    expect(markNotificationRead).toHaveBeenCalledTimes(1)
  })

  it("does not navigate when account A's pending mark-read succeeds after switching to account B", async () => {
    vi.mocked(fetchNotificationsList).mockResolvedValue(listResult([entry("1")]))
    let resolveRead!: () => void
    const readGate = new Promise<void>((resolve) => {
      resolveRead = resolve
    })
    vi.mocked(markNotificationRead).mockImplementationOnce(() => readGate as never)
    useAuthStore.setState({
      user: { id: "notifications-account-A" } as UserState,
      loading: false,
    })
    const { result } = setup()
    await waitFor(() => expect(result.current.isLoading).toBe(false))

    const navigate = vi.fn()
    let navigationPromise: Promise<void> = Promise.resolve()
    act(() => {
      navigationPromise = navigateAfterNotificationRead(
        result.current.markRead,
        "1",
        "/news/from-account-a",
        navigate
      )
    })
    await waitFor(() => expect(markNotificationRead).toHaveBeenCalledWith("1"))

    act(() => {
      useAuthStore.setState({
        user: { id: "notifications-account-B" } as UserState,
        loading: false,
      })
    })
    await act(async () => {
      resolveRead()
      await navigationPromise.catch(() => undefined)
    })

    await expect(navigationPromise).rejects.toThrow("account changed")
    expect(navigate).not.toHaveBeenCalled()
    expect(result.current.mutationFailures).toHaveLength(0)
  })

  it("navigates after the API succeeds without waiting for its background refetch", async () => {
    let listRequests = 0
    let resolveRefetch!: (response: NotificationsListResult) => void
    const refetchGate = new Promise<NotificationsListResult>((resolve) => {
      resolveRefetch = resolve
    })
    vi.mocked(fetchNotificationsList).mockImplementation(() => {
      listRequests += 1
      return listRequests === 1 ? Promise.resolve(listResult([entry("1")])) : refetchGate
    })
    vi.mocked(markNotificationRead).mockResolvedValue(undefined as never)
    useAuthStore.setState({
      user: { id: "notifications-account-A" } as UserState,
      loading: false,
    })
    const { result } = setup()
    await waitFor(() => expect(result.current.isLoading).toBe(false))

    const navigate = vi.fn()
    let navigationPromise: Promise<void> = Promise.resolve()
    act(() => {
      navigationPromise = navigateAfterNotificationRead(
        result.current.markRead,
        "1",
        "/news/from-account-a",
        navigate
      )
    })
    await waitFor(() => expect(listRequests).toBe(2))
    await expect(navigationPromise).resolves.toBeUndefined()
    expect(navigate).toHaveBeenCalledWith("/news/from-account-a")

    act(() => {
      useAuthStore.setState({
        user: { id: "notifications-account-B" } as UserState,
        loading: false,
      })
    })
    await act(async () => {
      resolveRefetch(listResult([entry("1", { read: true })]))
    })

    expect(navigate).toHaveBeenCalledOnce()
  })

  it("rejects a stale same-target retry after a newer attempt starts", async () => {
    vi.mocked(fetchNotificationsList).mockResolvedValue(listResult([entry("1")]))
    let resolveRetry!: () => void
    const retryGate = new Promise<void>((resolve) => {
      resolveRetry = resolve
    })
    vi.mocked(markNotificationRead)
      .mockRejectedValueOnce(new Error("request failed"))
      .mockImplementationOnce(() => retryGate as never)
    const { result } = setup()
    await waitFor(() => expect(result.current.isLoading).toBe(false))

    await act(async () => {
      await result.current.markRead("1").catch(() => undefined)
    })
    await waitFor(() => expect(result.current.mutationFailures).toHaveLength(1))
    const staleFailure = result.current.mutationFailures[0]!

    let newerAttempt: Promise<void> = Promise.resolve()
    act(() => {
      newerAttempt = result.current.markRead("1")
    })
    await waitFor(() => expect(markNotificationRead).toHaveBeenCalledTimes(2))
    await expect(result.current.retryMutationFailure(staleFailure)).rejects.toThrow(
      "no longer current"
    )
    expect(markNotificationRead).toHaveBeenCalledTimes(2)

    await act(async () => {
      resolveRetry()
      await newerAttempt
    })
  })

  it("does not navigate after an older same-target request is superseded", async () => {
    vi.mocked(fetchNotificationsList).mockResolvedValue(listResult([entry("1")]))
    const releaseReads: Array<() => void> = []
    vi.mocked(markNotificationRead).mockImplementation(
      () => new Promise<void>((resolve) => releaseReads.push(resolve)) as never
    )
    const { result } = setup()
    await waitFor(() => expect(result.current.isLoading).toBe(false))

    const navigate = vi.fn()
    let oldNavigation: Promise<void> = Promise.resolve()
    act(() => {
      oldNavigation = navigateAfterNotificationRead(
        result.current.markRead,
        "1",
        "/news/old-attempt",
        navigate
      )
    })
    await waitFor(() => expect(markNotificationRead).toHaveBeenCalledTimes(1))

    let newAttempt: Promise<void> = Promise.resolve()
    act(() => {
      newAttempt = result.current.markRead("1")
    })
    await waitFor(() => expect(markNotificationRead).toHaveBeenCalledTimes(2))

    await act(async () => {
      releaseReads[0]!()
      await oldNavigation.catch(() => undefined)
    })
    await expect(oldNavigation).rejects.toThrow("no longer current")
    expect(navigate).not.toHaveBeenCalled()

    await act(async () => {
      releaseReads[1]!()
      await newAttempt
    })
  })

  it("does not navigate when an older same-target mutation succeeds after a newer attempt", async () => {
    vi.mocked(fetchNotificationsList).mockResolvedValue(listResult([entry("1")]))
    const releaseReads: Array<() => void> = []
    vi.mocked(markNotificationRead).mockImplementation(
      () => new Promise<void>((resolve) => releaseReads.push(resolve)) as never
    )
    const { result } = setup()
    await waitFor(() => expect(result.current.isLoading).toBe(false))

    const navigate = vi.fn()
    let oldNavigation: Promise<void> = Promise.resolve()
    act(() => {
      oldNavigation = navigateAfterNotificationRead(
        result.current.markRead,
        "1",
        "/news/old-attempt",
        navigate
      )
    })
    await waitFor(() => expect(markNotificationRead).toHaveBeenCalledTimes(1))

    let newAttempt: Promise<void> = Promise.resolve()
    act(() => {
      newAttempt = result.current.markRead("1")
    })
    await waitFor(() => expect(markNotificationRead).toHaveBeenCalledTimes(2))

    await act(async () => {
      releaseReads[0]!()
      await oldNavigation.catch(() => undefined)
    })
    await expect(oldNavigation).rejects.toThrow("no longer current")
    expect(navigate).not.toHaveBeenCalled()

    await act(async () => {
      releaseReads[1]!()
      await newAttempt
    })
  })

  it("suppresses a pending item-read failure after a later mark-all succeeds", async () => {
    vi.mocked(fetchNotificationsList).mockResolvedValue(listResult([entry("1")]))
    let rejectRead!: (error: Error) => void
    const readGate = new Promise<void>((_resolve, reject) => {
      rejectRead = reject
    })
    vi.mocked(markNotificationRead).mockImplementationOnce(() => readGate as never)
    const { result } = setup()
    await waitFor(() => expect(result.current.isLoading).toBe(false))

    let readPromise: Promise<void> = Promise.resolve()
    act(() => {
      readPromise = result.current.markRead("1")
    })
    await waitFor(() => expect(markNotificationRead).toHaveBeenCalledOnce())

    await act(async () => {
      await result.current.markAll()
    })
    await act(async () => {
      rejectRead(new Error("read request failed late"))
      await readPromise.catch(() => undefined)
    })

    expect(result.current.mutationFailures).toEqual([])
  })

  it("preserves a later item-read failure when an older mark-all succeeds late", async () => {
    vi.mocked(fetchNotificationsList).mockResolvedValue(listResult([entry("1")]))
    let resolveMarkAll!: () => void
    const markAllGate = new Promise<void>((resolve) => {
      resolveMarkAll = resolve
    })
    vi.mocked(markAllNotificationsRead).mockImplementationOnce(() => markAllGate as never)
    vi.mocked(markNotificationRead).mockRejectedValueOnce(new Error("newer read failed"))
    const { result } = setup()
    await waitFor(() => expect(result.current.isLoading).toBe(false))

    let markAllPromise: Promise<void> = Promise.resolve()
    act(() => {
      markAllPromise = result.current.markAll()
    })
    await waitFor(() => expect(markAllNotificationsRead).toHaveBeenCalledOnce())

    await act(async () => {
      await result.current.markRead("1").catch(() => undefined)
    })
    expect(result.current.mutationFailures).toHaveLength(1)

    await act(async () => {
      resolveMarkAll()
      await markAllPromise
    })

    expect(result.current.mutationFailures).toHaveLength(1)
    expect(result.current.mutationFailures[0]).toMatchObject({
      operation: "mark-read",
      notificationId: "1",
    })
  })

  it("suppresses an earlier item-read failure after a later clear succeeds", async () => {
    vi.mocked(fetchNotificationsList).mockResolvedValue(listResult([entry("1")]))
    let rejectRead!: (error: Error) => void
    const readGate = new Promise<void>((_resolve, reject) => {
      rejectRead = reject
    })
    vi.mocked(markNotificationRead).mockImplementationOnce(() => readGate as never)
    const { result } = setup()
    await waitFor(() => expect(result.current.isLoading).toBe(false))

    let readPromise: Promise<void> = Promise.resolve()
    act(() => {
      readPromise = result.current.markRead("1")
    })
    await waitFor(() => expect(markNotificationRead).toHaveBeenCalledOnce())

    await act(async () => {
      await result.current.clearAll()
    })
    await act(async () => {
      rejectRead(new Error("read request failed late"))
      await readPromise.catch(() => undefined)
    })

    expect(result.current.mutationFailures).toEqual([])
  })

  it("keeps cache invalidation from an older same-target success and preserves the newer failure", async () => {
    let listRequests = 0
    let resolveRefetch!: (response: NotificationsListResult) => void
    const refetchGate = new Promise<NotificationsListResult>((resolve) => {
      resolveRefetch = resolve
    })
    vi.mocked(fetchNotificationsList).mockImplementation(() => {
      listRequests += 1
      return listRequests === 1 ? Promise.resolve(listResult([entry("1")])) : refetchGate
    })
    let resolveOlderRead!: () => void
    const olderReadGate = new Promise<void>((resolve) => {
      resolveOlderRead = resolve
    })
    vi.mocked(markNotificationRead)
      .mockImplementationOnce(() => olderReadGate as never)
      .mockRejectedValueOnce(new Error("latest attempt failed"))
    const { result } = setup()
    await waitFor(() => expect(result.current.isLoading).toBe(false))

    let olderAttempt: Promise<void> = Promise.resolve()
    act(() => {
      olderAttempt = result.current.markRead("1")
    })
    await waitFor(() => expect(markNotificationRead).toHaveBeenCalledTimes(1))

    await act(async () => {
      await result.current.markRead("1").catch(() => undefined)
    })
    await waitFor(() => expect(result.current.mutationFailures).toHaveLength(1))

    await act(async () => {
      resolveOlderRead()
      await olderAttempt.catch(() => undefined)
    })
    await waitFor(() => expect(listRequests).toBe(2))
    await expect(olderAttempt).rejects.toThrow("no longer current")
    expect(result.current.mutationFailures).toHaveLength(1)
    expect(result.current.mutationFailures[0]).toMatchObject({
      operation: "mark-read",
      notificationId: "1",
    })

    await act(async () => {
      resolveRefetch(listResult([entry("1", { read: true })]))
    })
  })

  it("resets broad-success watermarks when the same account returns in a new revision", async () => {
    vi.mocked(fetchNotificationsList).mockResolvedValue(listResult([entry("1")]))
    vi.mocked(markNotificationRead).mockRejectedValueOnce(new Error("new revision failed"))
    useAuthStore.setState({
      user: { id: "notifications-account-A" } as UserState,
      loading: false,
    })
    const { result } = setup()
    await waitFor(() => expect(result.current.isLoading).toBe(false))
    await act(async () => {
      await result.current.markAll()
    })

    act(() => {
      useAuthStore.setState({
        user: { id: "notifications-account-B" } as UserState,
        loading: false,
      })
      useAuthStore.setState({
        user: { id: "notifications-account-A" } as UserState,
        loading: false,
      })
    })

    await act(async () => {
      await result.current.markRead("1").catch(() => undefined)
    })
    expect(result.current.mutationFailures).toHaveLength(1)
  })

  it.each(["markAll", "clearAll"] as const)(
    "does not keep %s pending when the same account id returns under a new revision",
    async (operation) => {
      vi.mocked(fetchNotificationsList).mockResolvedValue(listResult([entry("1")]))
      let resolveOperation!: () => void
      const operationGate = new Promise<void>((resolve) => {
        resolveOperation = resolve
      })
      const request = operation === "markAll" ? markAllNotificationsRead : clearNotifications
      vi.mocked(request).mockImplementationOnce(() => operationGate as never)
      useAuthStore.setState({
        user: { id: "notifications-account-A" } as UserState,
        loading: false,
      })
      const { result } = setup()
      await waitFor(() => expect(result.current.isLoading).toBe(false))

      let operationPromise: Promise<void> = Promise.resolve()
      act(() => {
        operationPromise = result.current[operation]()
      })
      await waitFor(() => expect(request).toHaveBeenCalledOnce())

      act(() => {
        useAuthStore.setState({
          user: { id: "notifications-account-B" } as UserState,
          loading: false,
        })
        useAuthStore.setState({
          user: { id: "notifications-account-A" } as UserState,
          loading: false,
        })
      })
      const pendingFlag = operation === "markAll" ? "isMarkingAll" : "isClearing"
      await waitFor(() => expect(result.current[pendingFlag]).toBe(false))

      await act(async () => {
        resolveOperation()
        await operationPromise.catch(() => undefined)
      })
      await expect(operationPromise).rejects.toThrow("account changed")
    }
  )
})

describe("useNotifications — fetchMore", () => {
  it("merges the next page and deduplicates by id", async () => {
    // Cursor-keyed so the result is independent of call count / refetch timing.
    vi.mocked(fetchNotificationsList).mockImplementation((params) =>
      params?.cursor === "c1"
        ? Promise.resolve(
            listResult([entry("2"), entry("3")], {
              has_more: false,
              unread_count: 0,
            })
          )
        : Promise.resolve(
            listResult([entry("1"), entry("2")], {
              has_more: true,
              next_cursor: "c1",
            })
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

  it("does not load a later page while the first page is missing", async () => {
    // Initial list rejects, so there is no cursor to continue from: a later page
    // must not be requested with the stale cursor.
    vi.mocked(fetchNotificationsList).mockRejectedValue(new Error("no initial list"))
    const { result } = setup()
    await waitFor(() => expect(result.current.isError).toBe(true))

    await act(async () => {
      await result.current.fetchMore("seed")
    })

    expect(fetchNotificationsList).not.toHaveBeenCalledWith({ cursor: "seed" })
    expect(result.current.data).toEqual([])
  })

  it("reads a cache without pages as an empty, settled list", async () => {
    const { qc, result } = setup()
    await waitFor(() => expect(result.current.isLoading).toBe(false))
    vi.mocked(fetchNotificationsList).mockClear()

    act(() => {
      qc.setQueryData(["notifications", "list"], { pages: [], pageParams: [] })
    })

    await waitFor(() => expect(result.current.hasMore).toBe(false))
    expect(result.current.data).toEqual([])
    expect(result.current.unreadCount).toBe(0)
    expect(result.current.nextCursor).toBeNull()
  })

  it("reports a failed later-page request and keeps the loaded items", async () => {
    vi.mocked(fetchNotificationsList).mockImplementation((params) =>
      params?.cursor === "c1"
        ? Promise.reject(new Error("page failed"))
        : Promise.resolve(listResult([entry("1")], { has_more: true, next_cursor: "c1" }))
    )
    const { result } = setup()
    await waitFor(() => expect(result.current.data).toHaveLength(1))

    await act(async () => {
      await result.current.fetchMore("c1")
    })

    await waitFor(() => expect(result.current.isFetchMoreError).toBe(true))
    expect(result.current.fetchMoreError).toEqual(new Error("page failed"))
    expect(result.current.data.map((i) => i.id)).toEqual(["1"])
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
