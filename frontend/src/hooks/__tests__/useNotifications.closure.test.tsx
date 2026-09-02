import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { act, renderHook, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

const api = vi.hoisted(() => ({
  checkSchedule: vi.fn(),
  clearNotifications: vi.fn(),
  fetchNotificationsList: vi.fn(),
  markAllNotificationsRead: vi.fn(),
  markNotificationRead: vi.fn(),
}))

vi.mock("@/api/notifications", () => api)
vi.mock("@/app/logger", () => ({ logWarning: vi.fn() }))

import { useNotifications } from "../useNotifications"

function setup() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, refetchOnWindowFocus: false },
      mutations: { retry: false },
    },
  })
  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )
  return { queryClient, ...renderHook(() => useNotifications(), { wrapper }) }
}

beforeEach(() => {
  vi.clearAllMocks()
  api.checkSchedule.mockResolvedValue(undefined)
  api.fetchNotificationsList.mockResolvedValue({
    items: [],
    unread_count: 0,
    has_more: false,
    next_cursor: null,
  })
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe("useNotifications live-message closure", () => {
  it("runs without registering push listeners during SSR-like navigator absence", async () => {
    vi.stubGlobal("navigator", undefined)

    const { result } = setup()

    await waitFor(() => expect(result.current.isLoading).toBe(false))
    expect(result.current.data).toEqual([])
  })

  it("rejects malformed push messages and deduplicates canonical notification ids", async () => {
    const listeners = new Set<(event: MessageEvent<unknown>) => void>()
    const serviceWorker = {
      addEventListener: vi.fn((_type: string, listener: (event: MessageEvent<unknown>) => void) => {
        listeners.add(listener)
      }),
      removeEventListener: vi.fn(
        (_type: string, listener: (event: MessageEvent<unknown>) => void) => {
          listeners.delete(listener)
        }
      ),
    }
    vi.stubGlobal("navigator", { serviceWorker })
    const { queryClient, result, unmount } = setup()
    const invalidate = vi.spyOn(queryClient, "invalidateQueries").mockResolvedValue(undefined)
    await waitFor(() => expect(result.current.isLoading).toBe(false))

    const dispatch = (data: unknown) => {
      const event = new MessageEvent("message", { data })
      for (const listener of listeners) listener(event)
    }
    act(() => {
      dispatch(null)
      dispatch("not-an-object")
      dispatch({})
      dispatch({ type: "OTHER", notificationId: "notification-1" })
      dispatch({ type: "PUSH_NOTIFICATION", notificationId: 7 })
      dispatch({ type: "PUSH_NOTIFICATION", notificationId: "   " })
    })
    expect(invalidate).not.toHaveBeenCalled()

    act(() => {
      dispatch({ type: "PUSH_NOTIFICATION", notificationId: " notification-1 " })
      dispatch({ type: "PUSH_NOTIFICATION", notificationId: "notification-1" })
    })
    expect(invalidate).toHaveBeenCalledOnce()

    unmount()
    expect(serviceWorker.removeEventListener).toHaveBeenCalledOnce()
  })

  it("bounds the live-id deduplication set and accepts an evicted id again", async () => {
    const listeners = new Set<(event: MessageEvent<unknown>) => void>()
    const serviceWorker = {
      addEventListener: vi.fn((_type: string, listener: (event: MessageEvent<unknown>) => void) => {
        listeners.add(listener)
      }),
      removeEventListener: vi.fn(),
    }
    vi.stubGlobal("navigator", { serviceWorker })
    const { queryClient, result, unmount } = setup()
    const invalidate = vi.spyOn(queryClient, "invalidateQueries").mockResolvedValue(undefined)
    await waitFor(() => expect(result.current.isLoading).toBe(false))

    const dispatch = (notificationId: string) => {
      const event = new MessageEvent("message", {
        data: { type: "PUSH_NOTIFICATION", notificationId },
      })
      for (const listener of listeners) listener(event)
    }
    act(() => {
      for (let index = 0; index <= 256; index += 1) dispatch(`notification-${index}`)
      dispatch("notification-0")
    })

    expect(invalidate).toHaveBeenCalledTimes(258)
    unmount()
  })
})
