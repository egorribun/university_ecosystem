import type { ReactNode } from "react"
import { act, cleanup, render, renderHook, screen } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import type { UserState } from "@/types/Auth"
import { useAuthStore } from "@/stores/useAuthStore"
import { acceptBrowserSessionGeneration } from "@/stores/sessionEpoch"
import { useAuthApi } from "@/hooks/auth/useAuthApi"
import LivePushToasts from "@/components/feedback/LivePushToasts"

const network = vi.hoisted(() => ({
  post: vi.fn(),
  releasePushServerBinding: vi.fn(),
}))

vi.mock("framer-motion", async () =>
  (await import("@/tests/helpers/framerMotionMock")).framerMotionMock()
)
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))
vi.mock("@/api/client", () => ({
  API_UNAUTHORIZED_EVENT: "auth:unauthorized",
  default: { post: network.post },
}))
vi.mock("@/api/interceptors/etagCache", () => ({ incrementSessionEpoch: vi.fn() }))
vi.mock("@/hooks/auth/useProfileSync", () => ({ fetchCurrentUser: vi.fn() }))
vi.mock("@/push/subscribe", () => ({
  hasPushConsent: () => false,
  setPushConsent: vi.fn(),
  syncPushForConfirmedIdentity: async () => null,
  releasePushServerBinding: network.releasePushServerBinding,
}))
vi.mock("@/i18n/config", () => ({ default: { language: "en", resolvedLanguage: "en" } }))
vi.mock("@/hooks/useDashboardStories", () => ({ prefetchDashboardStories: vi.fn() }))
vi.mock("@/hooks/useDashboardNews", () => ({ prefetchDashboardNews: vi.fn() }))
vi.mock("@/hooks/useDashboardEvents", () => ({ prefetchDashboardEvents: vi.fn() }))
vi.mock("@/api/hooks/events", () => ({ EVENTS_PAGE_SIZE: 20, prefetchEventsListQuery: vi.fn() }))
vi.mock("@/app/logger", () => ({ logWarning: vi.fn(), logError: vi.fn() }))

const USER_A = { id: "push-owner-a", spotify_connected: false } as UserState
const USER_B = { id: "push-owner-b", spotify_connected: false } as UserState
const KEY_A = "livePushToastBuffer:push-owner-a"
const KEY_B = "livePushToastBuffer:push-owner-b"

function createAuthHook() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return renderHook(
    () => {
      const { user, setUser, authOperation, setAuthOperation } = useAuthStore()
      return useAuthApi(
        user,
        setUser,
        () => undefined,
        () => useAuthStore.setState({ user: null, loading: false }),
        () => undefined,
        authOperation,
        setAuthOperation,
        () => undefined
      )
    },
    {
      wrapper: ({ children }: { children: ReactNode }) => (
        <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
      ),
    }
  )
}

function deliver(worker: EventTarget, recipientUserId: string, id: string, title: string) {
  act(() => {
    worker.dispatchEvent(
      new MessageEvent("message", {
        data: {
          type: "PUSH_NOTIFICATION",
          recipientUserId,
          toast: { id, title, body: `Private ${title}` },
        },
      })
    )
  })
}

describe("LivePushToasts account isolation through auth and worker delivery", () => {
  let worker: EventTarget
  let visibility: ReturnType<typeof vi.spyOn>
  let originalServiceWorker: PropertyDescriptor | undefined

  beforeEach(() => {
    window.localStorage.clear()
    acceptBrowserSessionGeneration()
    useAuthStore.setState({ user: USER_A, loading: false, authOperation: false })
    originalServiceWorker = Object.getOwnPropertyDescriptor(navigator, "serviceWorker")
    worker = new EventTarget()
    Object.defineProperty(navigator, "serviceWorker", { configurable: true, value: worker })
    visibility = vi.spyOn(document, "visibilityState", "get").mockReturnValue("hidden")
    network.post.mockReset()
    network.post.mockImplementation(async (path: string) =>
      path === "/auth/login" ? { status: 200, data: { user: USER_B } } : { status: 200 }
    )
    network.releasePushServerBinding.mockReset().mockResolvedValue(undefined)
  })

  afterEach(() => {
    cleanup()
    useAuthStore.setState({ user: null, loading: false, authOperation: false })
    visibility.mockRestore()
    if (originalServiceWorker) {
      Object.defineProperty(navigator, "serviceWorker", originalServiceWorker)
    } else {
      Reflect.deleteProperty(navigator, "serviceWorker")
    }
    window.localStorage.clear()
    acceptBrowserSessionGeneration()
  })

  it("restores the owner's persisted buffer after remount and clears it on real logout", async () => {
    const auth = createAuthHook()
    const firstView = render(<LivePushToasts />)
    deliver(worker, "push-owner-a", "a-before-remount", "A before remount")
    expect(window.localStorage.getItem(KEY_A)).toContain("a-before-remount")

    firstView.unmount()
    render(<LivePushToasts />)
    visibility.mockReturnValue("visible")
    act(() => document.dispatchEvent(new Event("visibilitychange")))
    expect(screen.getByText("A before remount")).toBeInTheDocument()

    visibility.mockReturnValue("hidden")
    deliver(worker, "push-owner-a", "a-at-logout", "A at logout")
    expect(window.localStorage.getItem(KEY_A)).toContain("a-at-logout")
    await act(async () => auth.result.current.logout())
    expect(window.localStorage.getItem(KEY_A)).toBeNull()
    expect(screen.queryByText("A before remount")).not.toBeInTheDocument()

    await act(async () => auth.result.current.login("user-b", "unused"))
    deliver(worker, "push-owner-a", "late-a", "Late A")
    deliver(worker, "push-owner-b", "b-after-login", "B after login")
    expect(window.localStorage.getItem(KEY_A)).toBeNull()
    expect(window.localStorage.getItem(KEY_B)).toContain("b-after-login")
    expect(window.localStorage.getItem(KEY_B)).not.toContain("late-a")

    visibility.mockReturnValue("visible")
    act(() => document.dispatchEvent(new Event("visibilitychange")))
    expect(screen.getByText("B after login")).toBeInTheDocument()
    expect(screen.queryByText("A at logout")).not.toBeInTheDocument()
    expect(screen.queryByText("Late A")).not.toBeInTheDocument()

    visibility.mockReturnValue("hidden")
    deliver(worker, "push-owner-b", "b-at-logout", "B at logout")
    expect(window.localStorage.getItem(KEY_B)).toContain("b-at-logout")
    await act(async () => auth.result.current.logout())
    expect(window.localStorage.getItem(KEY_B)).toBeNull()
    expect(screen.queryByText("B after login")).not.toBeInTheDocument()
  })

  it("preserves the new owner's buffer when the previous logout completes late", async () => {
    let completeLogout!: (value: { status: number }) => void
    const pendingLogout = new Promise<{ status: number }>((resolve) => {
      completeLogout = resolve
    })
    network.post.mockImplementation((path: string) =>
      path === "/auth/logout"
        ? pendingLogout
        : Promise.resolve({ status: 200, data: { user: USER_B } })
    )
    const auth = createAuthHook()
    render(<LivePushToasts />)
    deliver(worker, "push-owner-a", "a-in-flight", "A in flight")

    let logout!: Promise<void>
    await act(async () => {
      logout = auth.result.current.logout()
      await Promise.resolve()
    })
    expect(network.post).toHaveBeenCalledWith("/auth/logout")
    await act(async () => auth.result.current.login("user-b", "unused"))
    deliver(worker, "push-owner-a", "a-late-message", "A late message")
    deliver(worker, "push-owner-b", "b-owned", "B owned")
    expect(window.localStorage.getItem(KEY_A)).toBeNull()
    expect(window.localStorage.getItem(KEY_B)).toContain("b-owned")
    expect(window.localStorage.getItem(KEY_B)).not.toContain("a-late-message")

    await act(async () => {
      completeLogout({ status: 200 })
      await logout
    })
    expect(useAuthStore.getState().user?.id).toBe("push-owner-b")
    expect(window.localStorage.getItem(KEY_B)).toContain("b-owned")
    visibility.mockReturnValue("visible")
    act(() => document.dispatchEvent(new Event("visibilitychange")))
    expect(screen.getByText("B owned")).toBeInTheDocument()
    expect(screen.queryByText("A in flight")).not.toBeInTheDocument()
    expect(screen.queryByText("A late message")).not.toBeInTheDocument()
  })

  it("does not show a hidden notification from A after B signs in", async () => {
    const auth = createAuthHook()
    render(<LivePushToasts />)
    deliver(worker, "push-owner-a", "a-before-switch", "A before switch")

    await act(async () => auth.result.current.login("user-b", "unused"))
    deliver(worker, "push-owner-b", "b-before-visible", "B before visible")
    visibility.mockReturnValue("visible")
    act(() => document.dispatchEvent(new Event("visibilitychange")))

    expect(screen.queryByText("A before switch")).not.toBeInTheDocument()
    expect(screen.getByText("B before visible")).toBeInTheDocument()
  })
})
