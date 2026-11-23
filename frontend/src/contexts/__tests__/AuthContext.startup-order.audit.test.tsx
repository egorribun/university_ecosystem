import { useContext, useEffect } from "react"
import { CancelledError, onlineManager, QueryClientProvider } from "@tanstack/react-query"
import { act, cleanup, render, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { AxiosError, AxiosHeaders } from "axios"
import { hydrateRoot } from "react-dom/client"
import { renderToString } from "react-dom/server"
import api from "@/api/client"
import { createQueryClient, setQueryCacheIdentity } from "@/app/queryClient"
import { AuthProvider, useAuth } from "@/contexts/AuthContext"
import { AuthBootstrapContext, useAuthBootstrapQueryGate } from "@/contexts/AuthBootstrapContext"
import { prefetchEventsListQuery, useEventsListQuery } from "@/api/hooks/events"
import { hasActiveProfileBootstrap } from "@/hooks/auth/profileBootstrapActivity"
import { useNotifications } from "@/hooks/useNotifications"
import { useAuthStore } from "@/stores/useAuthStore"
import { acceptBrowserSessionGeneration, rotateBrowserSession } from "@/stores/sessionEpoch"
import { testUser } from "@/tests/mocks/handlers"
import { cryptoWorker } from "@/utils/cryptoWorker"
import * as logger from "@/app/logger"

type NotificationsApi = typeof import("@/api/notifications")
type GeneratedSdk = typeof import("@/api/generated/sdk.gen")

const mocks = vi.hoisted(() => ({ notifications: vi.fn(), events: vi.fn(), schedule: vi.fn() }))
vi.mock("@/api/notifications", async (load) => ({
  ...(await load<NotificationsApi>()),
  fetchNotificationsList: mocks.notifications,
  checkSchedule: mocks.schedule,
}))
vi.mock("@/api/generated/sdk.gen", async (load) => ({
  ...(await load<GeneratedSdk>()),
  allEventsApiV1EventsGet: mocks.events,
}))

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((done) => {
    resolve = done
  })
  return { promise, resolve }
}
function StartupViews() {
  useNotifications()
  useEventsListQuery({ language: "en", limit: 12, is_active: true, order: "starts_at_desc" })
  const auth = useAuth()
  return <span data-testid="auth-loading">{String(auth.loading)}</span>
}
let originalWorker: PropertyDescriptor | undefined
let root: HTMLElement
beforeEach(() => {
  localStorage.clear()
  sessionStorage.clear()
  localStorage.setItem(
    "ecosystem.session.generation.v1",
    JSON.stringify({ nonce: "same-generation", hash: "same-hash" })
  )
  acceptBrowserSessionGeneration()
  useAuthStore.setState(useAuthStore.getInitialState(), true)
  setQueryCacheIdentity(null)
  root = document.createElement("div")
  root.id = "root"
  root.setAttribute("data-ssr-auth", "authenticated:student")
  document.body.appendChild(root)
  originalWorker = Object.getOwnPropertyDescriptor(navigator, "serviceWorker")
  vi.spyOn(cryptoWorker, "pbkdf2").mockResolvedValue("same-hash")
  mocks.notifications
    .mockReset()
    .mockResolvedValue({ items: [], unread_count: 0, has_more: false, next_cursor: null })
  mocks.schedule.mockReset().mockResolvedValue(undefined)
  mocks.events.mockReset().mockResolvedValue({
    status: 200,
    data: { items: [], total: 0, limit: 12, has_more: false, next_cursor: null },
  })
})
afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  onlineManager.setOnline(true)
  if (originalWorker) Object.defineProperty(navigator, "serviceWorker", originalWorker)
  else Reflect.deleteProperty(navigator, "serviceWorker")
  root.remove()
  localStorage.clear()
  sessionStorage.clear()
  acceptBrowserSessionGeneration()
  useAuthStore.setState(useAuthStore.getInitialState(), true)
  setQueryCacheIdentity(null)
})

describe("authenticated startup request order", () => {
  it("waits for profile and key bootstrap before starting online private list reads", async () => {
    const profile = deferred<{ data: typeof testUser }>()
    const signing = deferred<{ data: { signing_key: string } }>()
    vi.spyOn(api, "get").mockImplementation((url) => {
      if (url === "/users/me") return profile.promise
      if (url === "/auth/session/signing-key") return signing.promise
      throw new Error(`Unexpected request ${url}`)
    })
    const messages: string[] = []
    let ackPort: MessagePort | undefined
    Object.defineProperty(navigator, "serviceWorker", {
      configurable: true,
      value: {
        controller: {
          postMessage: (message: { type: string }, ports?: MessagePort[]) => {
            messages.push(message.type)
            if (ports) ackPort = ports[0]
          },
        },
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      },
    })
    const queryClient = createQueryClient()
    const view = render(
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <StartupViews />
        </AuthProvider>
      </QueryClientProvider>
    )
    await waitFor(() => expect(api.get).toHaveBeenCalledWith("/users/me", expect.anything()))
    expect(view.getByTestId("auth-loading")).toHaveTextContent("false")
    expect(mocks.notifications).not.toHaveBeenCalled()
    expect(api.get).toHaveBeenCalledWith("/users/me", expect.anything())
    expect(api.get).not.toHaveBeenCalledWith("/auth/session/signing-key", expect.anything())
    expect(mocks.events).not.toHaveBeenCalled()
    await act(async () => {
      profile.resolve({ data: testUser })
    })
    await waitFor(() =>
      expect(api.get).toHaveBeenCalledWith("/auth/session/signing-key", expect.anything())
    )
    expect(mocks.events).not.toHaveBeenCalled()
    expect(mocks.notifications).not.toHaveBeenCalled()
    await act(async () => {
      signing.resolve({ data: { signing_key: "session-key" } })
    })
    await waitFor(() => expect(ackPort).toBeDefined())
    expect(messages).toContain("SET_API_SESSION_CACHE_KEY")
    expect(mocks.events).not.toHaveBeenCalled()
    expect(mocks.notifications).not.toHaveBeenCalled()
    await act(async () => {
      ackPort!.postMessage(true)
    })
    await waitFor(() => expect(mocks.events).toHaveBeenCalledOnce())
    await waitFor(() => expect(mocks.notifications).toHaveBeenCalledOnce())
    queryClient.clear()
  })
  it("commits a first-session profile if its worker controller changes during SET", async () => {
    localStorage.clear()
    acceptBrowserSessionGeneration()
    vi.spyOn(api, "get").mockImplementation((url) => {
      if (url === "/users/me") return Promise.resolve({ data: testUser })
      if (url === "/auth/session/signing-key")
        return Promise.resolve({ data: { signing_key: "session-key" } })
      throw new Error(`Unexpected request ${url}`)
    })
    let ackPort: MessagePort | undefined
    const oldController = {
      postMessage: vi.fn((_message: unknown, ports?: MessagePort[]) => {
        if (ports) ackPort = ports[0]
      }),
    }
    const newController = { postMessage: vi.fn() }
    const listeners = new Map<string, EventListener>()
    const worker = {
      controller: oldController,
      addEventListener: vi.fn((type: string, listener: EventListener) =>
        listeners.set(type, listener)
      ),
      removeEventListener: vi.fn((type: string) => listeners.delete(type)),
    }
    Object.defineProperty(navigator, "serviceWorker", { configurable: true, value: worker })
    const client = createQueryClient()
    const view = render(
      <QueryClientProvider client={client}>
        <AuthProvider>
          <StartupViews />
        </AuthProvider>
      </QueryClientProvider>
    )
    await waitFor(() => expect(ackPort).toBeDefined())
    await act(async () => {
      worker.controller = newController
      listeners.get("controllerchange")?.(new Event("controllerchange"))
      ackPort!.postMessage(true)
    })
    await waitFor(() => expect(useAuthStore.getState().user?.id).toBe(testUser.id))
    await waitFor(() => expect(mocks.notifications).toHaveBeenCalled())
    expect(newController.postMessage).toHaveBeenCalledWith(
      expect.objectContaining({ type: "SET_API_SESSION_CACHE_KEY" })
    )
    view.unmount()
    client.clear()
  })

  it("runs unchanged outside an auth provider", async () => {
    const client = createQueryClient()
    render(
      <QueryClientProvider client={client}>
        <StartupViews />
      </QueryClientProvider>
    )
    await waitFor(() => expect(mocks.notifications).toHaveBeenCalledOnce())
    expect(mocks.schedule).toHaveBeenCalledOnce()
    client.clear()
  })

  it("does not start an ownerless cold list while profile bootstrap is paused offline", async () => {
    onlineManager.setOnline(false)
    const get = vi.spyOn(api, "get")
    const client = createQueryClient()
    const view = render(
      <QueryClientProvider client={client}>
        <AuthProvider>
          <StartupViews />
        </AuthProvider>
      </QueryClientProvider>
    )
    await waitFor(() => expect(mocks.schedule).toHaveBeenCalledOnce())
    expect(mocks.notifications).not.toHaveBeenCalled()
    expect(get).not.toHaveBeenCalledWith("/auth/session/signing-key", expect.anything())
    view.unmount()
    client.clear()
  })

  it("retains offline-first list requests for an already confirmed owner", async () => {
    onlineManager.setOnline(false)
    useAuthStore.setState({ user: testUser, loading: false })
    const client = createQueryClient()
    render(
      <QueryClientProvider client={client}>
        <AuthBootstrapContext.Provider value={true}>
          <StartupViews />
        </AuthBootstrapContext.Provider>
      </QueryClientProvider>
    )
    await waitFor(() => expect(mocks.notifications).toHaveBeenCalledOnce())
    expect(mocks.schedule).toHaveBeenCalledOnce()
    client.clear()
  })

  it("runs the list after the existing bootstrap settles signed out", async () => {
    const unauthorized = new AxiosError(
      "Unauthenticated",
      AxiosError.ERR_BAD_REQUEST,
      undefined,
      undefined,
      {
        status: 401,
        statusText: "Unauthorized",
        headers: {},
        config: { headers: new AxiosHeaders() },
        data: {},
      }
    )
    vi.spyOn(api, "get").mockRejectedValue(unauthorized)
    const client = createQueryClient()
    render(
      <QueryClientProvider client={client}>
        <AuthProvider>
          <StartupViews />
        </AuthProvider>
      </QueryClientProvider>
    )
    await waitFor(() => expect(mocks.notifications).toHaveBeenCalled())
    expect(mocks.events).not.toHaveBeenCalled()
    expect(mocks.schedule).toHaveBeenCalled()
    client.clear()
  })

  it("runs the list after an online bootstrap error", async () => {
    vi.spyOn(logger, "logError").mockImplementation(() => undefined)
    vi.spyOn(api, "get").mockRejectedValue(new Error("offline backend"))
    const client = createQueryClient()
    render(
      <QueryClientProvider client={client}>
        <AuthProvider>
          <StartupViews />
        </AuthProvider>
      </QueryClientProvider>
    )
    await waitFor(() => expect(mocks.notifications).toHaveBeenCalledOnce())
    expect(mocks.events).not.toHaveBeenCalled()
    client.clear()
  })

  it("does not use an old profile to start key initialization after the browser session rotates", async () => {
    const profile = deferred<{ data: typeof testUser }>()
    vi.spyOn(api, "get").mockReturnValue(profile.promise)
    const client = createQueryClient()
    render(
      <QueryClientProvider client={client}>
        <AuthProvider>
          <StartupViews />
        </AuthProvider>
      </QueryClientProvider>
    )
    await waitFor(() => expect(api.get).toHaveBeenCalledWith("/users/me", expect.anything()))
    act(rotateBrowserSession)
    await act(async () => {
      profile.resolve({ data: testUser })
    })
    await waitFor(() => expect(mocks.notifications).toHaveBeenCalledOnce())
    expect(api.get).not.toHaveBeenCalledWith("/auth/session/signing-key", expect.anything())
    expect(mocks.events).not.toHaveBeenCalled()
    client.clear()
  })

  it("preserves SSR hydration while bootstrap is pending", async () => {
    const profile = deferred<{ data: typeof testUser }>()
    vi.spyOn(api, "get").mockReturnValue(profile.promise)
    const serverClient = createQueryClient()
    const serverTree = (
      <QueryClientProvider client={serverClient}>
        <AuthProvider>
          <StartupViews />
        </AuthProvider>
      </QueryClientProvider>
    )
    root.innerHTML = renderToString(serverTree)
    const client = createQueryClient()
    const errors: unknown[] = []
    let hydrated!: ReturnType<typeof hydrateRoot>
    await act(async () => {
      hydrated = hydrateRoot(
        root,
        <QueryClientProvider client={client}>
          <AuthProvider>
            <StartupViews />
          </AuthProvider>
        </QueryClientProvider>,
        {
          onRecoverableError: (error) => errors.push(error),
        }
      )
    })
    await waitFor(() => expect(api.get).toHaveBeenCalledWith("/users/me", expect.anything()))
    expect(errors).toEqual([])
    expect(mocks.notifications).not.toHaveBeenCalled()
    await act(async () => {
      hydrated.unmount()
      profile.resolve({ data: testUser })
    })
    serverClient.clear()
    client.clear()
  })

  it("waits for the same cold bootstrap across offline to online reconnect", async () => {
    onlineManager.setOnline(false)
    const profile = deferred<{ data: typeof testUser }>()
    const signing = deferred<{ data: { signing_key: string } }>()
    const get = vi.spyOn(api, "get").mockImplementation((url) => {
      if (url === "/users/me") return profile.promise
      if (url === "/auth/session/signing-key") return signing.promise
      throw new Error(`Unexpected request ${url}`)
    })
    const client = createQueryClient()
    const view = render(
      <QueryClientProvider client={client}>
        <AuthProvider>
          <StartupViews />
        </AuthProvider>
      </QueryClientProvider>
    )
    try {
      await waitFor(() => {
        const bootstrap = client.getQueryCache().findAll({
          queryKey: ["auth", "bootstrap", "current-user"],
          exact: false,
        })
        expect(bootstrap).toHaveLength(1)
        expect(bootstrap[0]?.state.fetchStatus).toBe("paused")
      })
      expect(get).not.toHaveBeenCalled()
      expect(mocks.notifications).not.toHaveBeenCalled()
      await act(async () => {
        onlineManager.setOnline(true)
      })
      await waitFor(() => expect(get).toHaveBeenCalledWith("/users/me", expect.anything()))
      expect(mocks.notifications).not.toHaveBeenCalled()
      await act(async () => {
        profile.resolve({ data: testUser })
      })
      await waitFor(() =>
        expect(get).toHaveBeenCalledWith("/auth/session/signing-key", expect.anything())
      )
      expect(mocks.notifications).not.toHaveBeenCalled()
      await act(async () => {
        signing.resolve({ data: { signing_key: "session-key" } })
      })
      await waitFor(() => expect(mocks.notifications).toHaveBeenCalledTimes(1))
      expect(useAuthStore.getState().user?.id).toBe(testUser.id)
    } finally {
      view.unmount()
      client.clear()
    }
  })
  it("confirmed owner must not start online reads during key bootstrap", async () => {
    const profile = deferred<{ data: typeof testUser }>()
    const signing = deferred<{ data: { signing_key: string } }>()
    vi.spyOn(api, "get").mockImplementation((url) => {
      if (url === "/users/me") return profile.promise
      if (url === "/auth/session/signing-key") return signing.promise
      throw new Error(`Unexpected request ${url}`)
    })
    let auth!: ReturnType<typeof useAuth>
    let pending = false
    let notifications!: ReturnType<typeof useNotifications>
    function ConfirmedOwnerProbe() {
      const currentAuth = useAuth()
      const currentPending = useContext(AuthBootstrapContext)
      useEffect(() => {
        auth = currentAuth
        pending = currentPending
      }, [currentAuth, currentPending])
      const currentNotifications = useNotifications()
      useEffect(() => {
        notifications = currentNotifications
      }, [currentNotifications])
      useEventsListQuery({ language: "en", limit: 12, is_active: true, order: "starts_at_desc" })
      return <span data-testid="owner-probe">{String(currentPending)}</span>
    }
    const client = createQueryClient()
    const view = render(
      <QueryClientProvider client={client}>
        <AuthProvider>
          <ConfirmedOwnerProbe />
        </AuthProvider>
      </QueryClientProvider>
    )
    try {
      await waitFor(() => expect(api.get).toHaveBeenCalledWith("/users/me", expect.anything()))
      await act(async () => {
        profile.resolve({ data: testUser })
      })
      await waitFor(() =>
        expect(api.get).toHaveBeenCalledWith("/auth/session/signing-key", expect.anything())
      )
      expect(pending).toBe(true)
      await act(async () => {
        auth.setUser(testUser)
      })
      await waitFor(() => expect(useAuthStore.getState().user?.id).toBe(testUser.id))
      expect(pending).toBe(true)
      expect(notifications.isLoading).toBe(true)
      expect(notifications.data).toEqual([])
      expect({
        notifications: mocks.notifications.mock.calls.length,
        events: mocks.events.mock.calls.length,
      }).toEqual({ notifications: 0, events: 0 })
      await act(async () => {
        signing.resolve({ data: { signing_key: "session-key" } })
      })
      await waitFor(() => expect(mocks.notifications).toHaveBeenCalledOnce())
      await waitFor(() => expect(mocks.events).toHaveBeenCalledOnce())
      await waitFor(() => expect(notifications.isLoading).toBe(false))
    } finally {
      view.unmount()
      await act(async () => {
        signing.resolve({ data: { signing_key: "session-key" } })
      })
      client.clear()
    }
  })

  it.each(["ordinary", "before rerender"])(
    "reconnect %s: confirmed offline owner must wait for worker ACK before online refetch",
    async (ordering) => {
      const profile = deferred<{ data: typeof testUser }>()
      const signing = deferred<{ data: { signing_key: string } }>()
      vi.spyOn(api, "get").mockImplementation((url) => {
        if (url === "/users/me") return profile.promise
        if (url === "/auth/session/signing-key") return signing.promise
        throw new Error(`Unexpected request ${url}`)
      })
      let ackPort: MessagePort | undefined
      Object.defineProperty(navigator, "serviceWorker", {
        configurable: true,
        value: {
          controller: {
            postMessage: (_message: unknown, ports?: MessagePort[]) => {
              if (ports) ackPort = ports[0]
            },
          },
          addEventListener: vi.fn(),
          removeEventListener: vi.fn(),
        },
      })
      let auth!: ReturnType<typeof useAuth>
      let pending = false
      let notifications!: ReturnType<typeof useNotifications>
      function ReconnectProbe() {
        const currentAuth = useAuth()
        const currentPending = useContext(AuthBootstrapContext)
        useEffect(() => {
          auth = currentAuth
          pending = currentPending
        }, [currentAuth, currentPending])
        const currentNotifications = useNotifications()
        useEffect(() => {
          notifications = currentNotifications
        }, [currentNotifications])
        const filters = {
          language: "en",
          limit: 12,
          is_active: true,
          order: "starts_at_desc" as const,
        }
        const first = useEventsListQuery(filters)
        const second = useEventsListQuery(filters)
        return (
          <>
            <span>{String(currentPending)}</span>
            <span data-testid="first">{first.events[0]?.id}</span>
            <span data-testid="second">{second.events[0]?.id}</span>
          </>
        )
      }
      mocks.notifications.mockResolvedValueOnce({
        items: [{ id: "synthetic", url: null }],
        unread_count: 1,
        has_more: false,
        next_cursor: null,
      })
      mocks.events
        .mockResolvedValueOnce({
          status: 200,
          data: {
            items: [{ id: "offline-item" }],
            total: 1,
            limit: 12,
            has_more: false,
            next_cursor: null,
          },
        })
        .mockResolvedValueOnce({
          status: 200,
          data: {
            items: [{ id: "online-item" }],
            total: 1,
            limit: 12,
            has_more: false,
            next_cursor: null,
          },
        })
      const client = createQueryClient()
      const view = render(
        <QueryClientProvider client={client}>
          <AuthProvider>
            <ReconnectProbe />
          </AuthProvider>
        </QueryClientProvider>
      )
      try {
        await waitFor(() => expect(api.get).toHaveBeenCalledWith("/users/me", expect.anything()))
        await act(async () => {
          profile.resolve({ data: testUser })
        })
        await waitFor(() =>
          expect(api.get).toHaveBeenCalledWith("/auth/session/signing-key", expect.anything())
        )
        await act(async () => {
          onlineManager.setOnline(false)
          auth.setUser(testUser)
        })
        await waitFor(() => expect(useAuthStore.getState().user?.id).toBe(testUser.id))
        expect(pending).toBe(true)
        await waitFor(() => expect(mocks.notifications).toHaveBeenCalledTimes(1))
        await waitFor(() => expect(notifications.data[0]?.id).toBe("synthetic"))
        expect(notifications.isLoading).toBe(false)
        await waitFor(() => expect(mocks.events).toHaveBeenCalledTimes(1))
        await waitFor(() => expect(view.getByTestId("first")).toHaveTextContent("offline-item"))
        expect(view.getByTestId("second")).toHaveTextContent("offline-item")
        const otherKey = ["synthetic-neighbor", "list"] as const
        const otherData = { payload: "unchanged" }
        client.setQueryData(otherKey, otherData)
        const notificationsBefore = client.getQueryData(["notifications", "list"])
        const eventBefore = client
          .getQueryCache()
          .getAll()
          .find((q) => q.queryKey[0] === "events" && q.queryKey[1] === "list")
        expect(notificationsBefore).toBeDefined()
        expect(eventBefore?.state.data).toBeDefined()
        expect(eventBefore?.getObserversCount()).toBe(2)
        const eventDataBefore = eventBefore?.state.data
        await act(async () => {
          onlineManager.setOnline(true)
          if (ordering === "before rerender") client.getQueryCache().onOnline()
        })
        expect(pending).toBe(true)
        expect({
          notifications: mocks.notifications.mock.calls.length,
          events: mocks.events.mock.calls.length,
        }).toEqual({ notifications: 1, events: 1 })
        expect(client.getQueryData(["notifications", "list"])).toBe(notificationsBefore)
        expect(notifications.data[0]?.id).toBe("synthetic")
        expect(notifications.isLoading).toBe(false)
        expect(eventBefore?.state.data).toBe(eventDataBefore)
        expect(client.getQueryState(["notifications", "list"])?.status).toBe("success")
        expect(eventBefore?.state.status).toBe("success")
        expect(client.getQueryData(otherKey)).toBe(otherData)
        expect(client.getQueryState(otherKey)?.isInvalidated).toBe(false)
        await act(async () => {
          signing.resolve({ data: { signing_key: "session-key" } })
        })
        await waitFor(() => expect(ackPort).toBeDefined())
        expect({
          notifications: mocks.notifications.mock.calls.length,
          events: mocks.events.mock.calls.length,
        }).toEqual({ notifications: 1, events: 1 })
        await act(async () => {
          ackPort!.postMessage(true)
        })
        await waitFor(() => expect(pending).toBe(false))
        await waitFor(() => expect(mocks.notifications).toHaveBeenCalledTimes(2), { timeout: 1200 })
        await waitFor(() => expect(mocks.events).toHaveBeenCalledTimes(2))
        await waitFor(() => expect(view.getByTestId("first")).toHaveTextContent("online-item"))
        expect(view.getByTestId("second")).toHaveTextContent("online-item")
        expect(client.getQueryData(otherKey)).toBe(otherData)
        expect(client.getQueryState(otherKey)?.isInvalidated).toBe(false)
        view.unmount()
        expect(eventBefore?.getObserversCount()).toBe(0)
      } finally {
        view.unmount()
        await act(async () => {
          signing.resolve({ data: { signing_key: "session-key" } })
        })
        client.clear()
      }
    }
  )

  it.each(["disabled", "fresh", "callback-disabled"])(
    "reconnect policy %s: do not refetch a fresh list unnecessarily",
    async (variant) => {
      onlineManager.setOnline(false)
      useAuthStore.setState({ user: testUser, loading: false })
      function OptionsProbe() {
        const reconnect = variant === "disabled" ? false : variant === "fresh" ? true : () => false
        useEventsListQuery(
          { language: "en", limit: 12, is_active: true, order: "starts_at_desc" },
          { refetchOnReconnect: reconnect, staleTime: Infinity }
        )
        return null
      }
      const client = createQueryClient()
      const tree = (pending: boolean) => (
        <QueryClientProvider client={client}>
          <AuthBootstrapContext.Provider value={pending}>
            <OptionsProbe />
          </AuthBootstrapContext.Provider>
        </QueryClientProvider>
      )
      const view = render(tree(true))
      try {
        await waitFor(() => expect(mocks.events).toHaveBeenCalledTimes(1))
        await act(async () => {
          onlineManager.setOnline(true)
        })
        expect(mocks.events).toHaveBeenCalledTimes(1)
        await act(async () => {
          view.rerender(tree(false))
        })
        expect(mocks.events).toHaveBeenCalledTimes(1)
      } finally {
        view.unmount()
        client.clear()
      }
    }
  )

  it("timeout does not permanently block startup", async () => {
    const profile = deferred<{ data: typeof testUser }>()
    const signing = deferred<{ data: { signing_key: string } }>()
    vi.spyOn(api, "get").mockImplementation((url) => {
      if (url === "/users/me") return profile.promise
      if (url === "/auth/session/signing-key") return signing.promise
      throw new Error(`Unexpected request ${url}`)
    })
    let ackPort: MessagePort | undefined
    Object.defineProperty(navigator, "serviceWorker", {
      configurable: true,
      value: {
        controller: {
          postMessage: (_message: unknown, ports?: MessagePort[]) => {
            if (ports) ackPort = ports[0]
          },
        },
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      },
    })
    let auth!: ReturnType<typeof useAuth>
    let pending = false
    function LostAckProbe() {
      const currentAuth = useAuth()
      const currentPending = useContext(AuthBootstrapContext)
      useEffect(() => {
        auth = currentAuth
        pending = currentPending
      }, [currentAuth, currentPending])
      useNotifications()
      useEventsListQuery({ language: "en", limit: 12, is_active: true, order: "starts_at_desc" })
      return <span>{String(currentPending)}</span>
    }
    const client = createQueryClient()
    const view = render(
      <QueryClientProvider client={client}>
        <AuthProvider>
          <LostAckProbe />
        </AuthProvider>
      </QueryClientProvider>
    )
    try {
      await waitFor(() => expect(api.get).toHaveBeenCalledWith("/users/me", expect.anything()))
      await act(async () => {
        profile.resolve({ data: testUser })
      })
      await waitFor(() =>
        expect(api.get).toHaveBeenCalledWith("/auth/session/signing-key", expect.anything())
      )
      await act(async () => {
        auth.setUser(testUser)
      })
      expect(pending).toBe(true)
      vi.useFakeTimers()
      await act(async () => {
        signing.resolve({ data: { signing_key: "session-key" } })
      })
      expect(ackPort).toBeDefined()
      expect(pending).toBe(true)
      expect(mocks.events).not.toHaveBeenCalled()
      expect(mocks.notifications).not.toHaveBeenCalled()
      await act(async () => {
        await vi.advanceTimersByTimeAsync(1001)
      })
      expect(pending).toBe(false)
      vi.useRealTimers()
      await waitFor(() => expect(mocks.events).toHaveBeenCalledOnce())
      await waitFor(() => expect(mocks.notifications).toHaveBeenCalledOnce())
    } finally {
      vi.useRealTimers()
      view.unmount()
      await act(async () => {
        signing.resolve({ data: { signing_key: "session-key" } })
      })
      client.clear()
    }
  })
  it("deduplicates reconnect and leaves unrelated key untouched", async () => {
    onlineManager.setOnline(false)
    useAuthStore.setState({ user: testUser, loading: false })
    function SharedProbe() {
      useEventsListQuery({ language: "en", limit: 12, is_active: true, order: "starts_at_desc" })
      useEventsListQuery({ language: "en", limit: 12, is_active: true, order: "starts_at_desc" })
      return null
    }
    const client = createQueryClient()
    const other = ["synthetic-neighbor", "list"] as const
    const original = { payload: "unchanged" }
    client.setQueryData(other, original)
    const tree = (pending: boolean) => (
      <QueryClientProvider client={client}>
        <AuthBootstrapContext.Provider value={pending}>
          <SharedProbe />
        </AuthBootstrapContext.Provider>
      </QueryClientProvider>
    )
    const view = render(tree(true))
    try {
      await waitFor(() => expect(mocks.events).toHaveBeenCalledTimes(1))
      const query = client
        .getQueryCache()
        .getAll()
        .find((q) => q.queryKey[0] === "events" && q.queryKey[1] === "list")
      expect(query?.getObserversCount()).toBe(2)
      const cached = query?.state.data
      await act(async () => {
        onlineManager.setOnline(true)
        client.getQueryCache().onOnline()
      })
      expect(mocks.events).toHaveBeenCalledTimes(1)
      expect(query?.state.data).toBe(cached)
      expect(client.getQueryData(other)).toBe(original)
      expect(client.getQueryState(other)?.isInvalidated).toBe(false)
      await act(async () => {
        view.rerender(tree(false))
      })
      await waitFor(() => expect(mocks.events).toHaveBeenCalledTimes(2))
      expect(client.getQueryData(other)).toBe(original)
    } finally {
      view.unmount()
      client.clear()
    }
  })

  it("no online listener when bootstrap is settled", () => {
    const original = onlineManager.subscribe
    let active = 0
    const subscribe = vi.spyOn(onlineManager, "subscribe").mockImplementation((listener) => {
      active += 1
      const unsubscribe = original(listener)
      return () => {
        active -= 1
        unsubscribe()
      }
    })
    const client = createQueryClient()
    const key = ["synthetic-gate"] as const
    function GateProbe() {
      useAuthBootstrapQueryGate(client, key)
      return null
    }
    const tree = (pending: boolean) => (
      <AuthBootstrapContext.Provider value={pending}>
        <GateProbe />
      </AuthBootstrapContext.Provider>
    )
    const view = render(tree(false))
    try {
      expect(subscribe).not.toHaveBeenCalled()
      expect(active).toBe(0)
      view.rerender(tree(true))
      expect(active).toBe(1)
      view.rerender(tree(false))
      expect(active).toBe(0)
    } finally {
      view.unmount()
      client.clear()
    }
  })
  it.each(["initial", "cached"])(
    "paused %s retry uses committed bootstrap state after offline completion",
    async (mode) => {
      const profile = deferred<{ data: typeof testUser }>()
      const signing = deferred<{ data: { signing_key: string } }>()
      vi.spyOn(api, "get").mockImplementation((url) => {
        if (url === "/users/me") return profile.promise
        if (url === "/auth/session/signing-key") return signing.promise
        throw new Error(`Unexpected request ${url}`)
      })
      let ackPort: MessagePort | undefined
      Object.defineProperty(navigator, "serviceWorker", {
        configurable: true,
        value: {
          controller: {
            postMessage: (_message: unknown, ports?: MessagePort[]) => {
              if (ports) ackPort = ports[0]
            },
          },
          addEventListener: vi.fn(),
          removeEventListener: vi.fn(),
        },
      })
      let auth!: ReturnType<typeof useAuth>
      let pending = true
      function RetryProbe() {
        const currentAuth = useAuth()
        const currentPending = useContext(AuthBootstrapContext)
        useEffect(() => {
          auth = currentAuth
          pending = currentPending
        }, [currentAuth, currentPending])
        useNotifications()
        useEventsListQuery({ language: "en", limit: 12, is_active: true, order: "starts_at_desc" })
        return null
      }
      const client = createQueryClient()
      client.setDefaultOptions({
        ...client.getDefaultOptions(),
        queries: { ...client.getDefaultOptions().queries, retryDelay: 0 },
      })
      if (mode === "initial") {
        mocks.events.mockRejectedValueOnce(new Error("synthetic offline"))
        mocks.notifications.mockRejectedValueOnce(new Error("synthetic offline"))
      }
      const view = render(
        <QueryClientProvider client={client}>
          <AuthProvider>
            <RetryProbe />
          </AuthProvider>
        </QueryClientProvider>
      )
      try {
        await waitFor(() => expect(api.get).toHaveBeenCalledWith("/users/me", expect.anything()))
        await act(async () => {
          profile.resolve({ data: testUser })
        })
        await waitFor(() =>
          expect(api.get).toHaveBeenCalledWith("/auth/session/signing-key", expect.anything())
        )
        await act(async () => {
          onlineManager.setOnline(false)
          auth.setUser(testUser)
        })
        await waitFor(() => expect(mocks.events).toHaveBeenCalledTimes(1))
        await waitFor(() => expect(mocks.notifications).toHaveBeenCalledTimes(1))
        const eventQuery = client
          .getQueryCache()
          .getAll()
          .find((q) => q.queryKey[0] === "events" && q.queryKey[1] === "list")!
        const notificationsKey = ["notifications", "list"] as const
        if (mode === "cached") {
          await waitFor(() => expect(eventQuery.state.status).toBe("success"))
          await waitFor(() =>
            expect(client.getQueryState(notificationsKey)?.status).toBe("success")
          )
          mocks.events.mockRejectedValueOnce(new Error("synthetic offline"))
          mocks.notifications.mockRejectedValueOnce(new Error("synthetic offline"))
          act(() => {
            void client.invalidateQueries({ queryKey: eventQuery.queryKey, exact: true })
            void client.invalidateQueries({ queryKey: notificationsKey, exact: true })
          })
        }
        await waitFor(() => expect(eventQuery.state.fetchStatus).toBe("paused"), { timeout: 1500 })
        await waitFor(
          () => expect(client.getQueryState(notificationsKey)?.fetchStatus).toBe("paused"),
          { timeout: 1500 }
        )
        const before = mode === "initial" ? 1 : 2
        expect(mocks.events).toHaveBeenCalledTimes(before)
        expect(mocks.notifications).toHaveBeenCalledTimes(before)
        await act(async () => {
          signing.resolve({ data: { signing_key: "session-key" } })
        })
        await waitFor(() => expect(ackPort).toBeDefined())
        await act(async () => {
          ackPort!.postMessage(true)
        })
        await waitFor(() => expect(pending).toBe(false))
        await act(async () => {
          onlineManager.setOnline(true)
        })
        await waitFor(() => expect(mocks.events).toHaveBeenCalledTimes(before + 1), {
          timeout: 1500,
        })
        await waitFor(() => expect(mocks.notifications).toHaveBeenCalledTimes(before + 1), {
          timeout: 1500,
        })
        await waitFor(() => expect(eventQuery.state.fetchStatus).toBe("idle"), { timeout: 1500 })
        expect(eventQuery.state.status).toBe("success")
        expect(client.getQueryState(notificationsKey)?.status).toBe("success")
      } finally {
        view.unmount()
        await act(async () => {
          signing.resolve({ data: { signing_key: "session-key" } })
        })
        client.clear()
      }
    }
  )
  it.each(["initial", "cached"])(
    "retained observer %s retry follows provider after first unmount",
    async (mode) => {
      const profile = deferred<{ data: typeof testUser }>()
      const signing = deferred<{ data: { signing_key: string } }>()
      vi.spyOn(api, "get").mockImplementation((url) => {
        if (url === "/users/me") return profile.promise
        if (url === "/auth/session/signing-key") return signing.promise
        throw new Error(`Unexpected request ${url}`)
      })
      let ackPort: MessagePort | undefined
      Object.defineProperty(navigator, "serviceWorker", {
        configurable: true,
        value: {
          controller: {
            postMessage: (_message: unknown, ports?: MessagePort[]) => {
              if (ports) ackPort = ports[0]
            },
          },
          addEventListener: vi.fn(),
          removeEventListener: vi.fn(),
        },
      })
      let auth!: ReturnType<typeof useAuth>
      let pending = true
      function Reader() {
        useNotifications()
        useEventsListQuery({ language: "en", limit: 12, is_active: true, order: "starts_at_desc" })
        return null
      }
      function RetryProbe({ first }: { first: boolean }) {
        const currentAuth = useAuth()
        const currentPending = useContext(AuthBootstrapContext)
        useEffect(() => {
          auth = currentAuth
          pending = currentPending
        }, [currentAuth, currentPending])
        return (
          <>
            {first && <Reader key="first" />}
            <Reader key="second" />
          </>
        )
      }
      const client = createQueryClient()
      client.setDefaultOptions({
        ...client.getDefaultOptions(),
        queries: { ...client.getDefaultOptions().queries, retryDelay: 0 },
      })
      if (mode === "initial") {
        mocks.events.mockRejectedValueOnce(new Error("synthetic offline"))
        mocks.notifications.mockRejectedValueOnce(new Error("synthetic offline"))
      }
      const tree = (first: boolean) => (
        <QueryClientProvider client={client}>
          <AuthProvider>
            <RetryProbe first={first} />
          </AuthProvider>
        </QueryClientProvider>
      )
      const view = render(tree(true))
      try {
        await waitFor(() => expect(api.get).toHaveBeenCalledWith("/users/me", expect.anything()))
        await act(async () => {
          profile.resolve({ data: testUser })
        })
        await waitFor(() =>
          expect(api.get).toHaveBeenCalledWith("/auth/session/signing-key", expect.anything())
        )
        await act(async () => {
          onlineManager.setOnline(false)
          auth.setUser(testUser)
        })
        await waitFor(() => expect(mocks.events).toHaveBeenCalledTimes(1))
        await waitFor(() => expect(mocks.notifications).toHaveBeenCalledTimes(1))
        const eventQuery = client
          .getQueryCache()
          .getAll()
          .find((q) => q.queryKey[0] === "events" && q.queryKey[1] === "list")!
        const notificationsKey = ["notifications", "list"] as const
        if (mode === "cached") {
          await waitFor(() => expect(eventQuery.state.status).toBe("success"))
          await waitFor(() =>
            expect(client.getQueryState(notificationsKey)?.status).toBe("success")
          )
          mocks.events.mockRejectedValueOnce(new Error("synthetic offline"))
          mocks.notifications.mockRejectedValueOnce(new Error("synthetic offline"))
          act(() => {
            void client.invalidateQueries({ queryKey: eventQuery.queryKey, exact: true })
            void client.invalidateQueries({ queryKey: notificationsKey, exact: true })
          })
        }
        await waitFor(() => expect(eventQuery.state.fetchStatus).toBe("paused"), { timeout: 1500 })
        await waitFor(
          () => expect(client.getQueryState(notificationsKey)?.fetchStatus).toBe("paused"),
          { timeout: 1500 }
        )
        expect(eventQuery.getObserversCount()).toBe(2)
        await act(async () => {
          view.rerender(tree(false))
        })
        expect(eventQuery.getObserversCount()).toBe(1)
        const before = mode === "initial" ? 1 : 2
        expect(mocks.events).toHaveBeenCalledTimes(before)
        expect(mocks.notifications).toHaveBeenCalledTimes(before)
        await act(async () => {
          signing.resolve({ data: { signing_key: "session-key" } })
        })
        await waitFor(() => expect(ackPort).toBeDefined())
        await act(async () => {
          ackPort!.postMessage(true)
        })
        await waitFor(() => expect(pending).toBe(false))
        await act(async () => {
          onlineManager.setOnline(true)
        })
        await waitFor(() => expect(mocks.events).toHaveBeenCalledTimes(before + 1), {
          timeout: 1500,
        })
        await waitFor(() => expect(mocks.notifications).toHaveBeenCalledTimes(before + 1), {
          timeout: 1500,
        })
        await waitFor(() => expect(eventQuery.state.fetchStatus).toBe("idle"), { timeout: 1500 })
        expect(eventQuery.state.status).toBe("success")
        expect(client.getQueryState(notificationsKey)?.status).toBe("success")
      } finally {
        view.unmount()
        await act(async () => {
          signing.resolve({ data: { signing_key: "session-key" } })
        })
        client.clear()
      }
    }
  )
  it("retired provider callbacks reject and release their online listener on unmount", async () => {
    const profile = deferred<{ data: typeof testUser }>()
    vi.spyOn(api, "get").mockReturnValue(profile.promise)
    const originalSubscribe = onlineManager.subscribe
    let active = 0
    vi.spyOn(onlineManager, "subscribe").mockImplementation((listener) => {
      active += 1
      const unsubscribe = originalSubscribe(listener)
      return () => {
        active -= 1
        unsubscribe()
      }
    })
    const client = createQueryClient()
    const key = ["synthetic-retired-provider"] as const
    let guard: (() => void) | undefined
    function GuardProbe() {
      const { cancelIfBlocked } = useAuthBootstrapQueryGate(client, key)
      useEffect(() => {
        guard = cancelIfBlocked
      }, [cancelIfBlocked])
      return null
    }
    const tree = (show: boolean) => (
      <QueryClientProvider client={client}>
        {show && (
          <AuthProvider>
            <GuardProbe />
          </AuthProvider>
        )}
      </QueryClientProvider>
    )
    const view = render(tree(false))
    const baseline = active
    try {
      view.rerender(tree(true))
      await waitFor(() => expect(guard).toBeDefined())
      expect(active).toBeGreaterThan(baseline)
      view.rerender(tree(false))
      expect(active).toBe(baseline)
      expect(() => guard!()).toThrow(CancelledError)
    } finally {
      view.unmount()
      await act(async () => {
        profile.resolve({ data: testUser })
      })
      client.clear()
    }
  })
  it.each([1, 2])(
    "paused prefetch stays fenced through reconnect and wakes %s event observers after ACK",
    async (count) => {
      const profile = deferred<{ data: typeof testUser }>()
      const signing = deferred<{ data: { signing_key: string } }>()
      vi.spyOn(api, "get").mockImplementation((url) => {
        if (url === "/users/me") return profile.promise
        if (url === "/auth/session/signing-key") return signing.promise
        throw new Error(`Unexpected request ${url}`)
      })
      let ackPort: MessagePort | undefined
      Object.defineProperty(navigator, "serviceWorker", {
        configurable: true,
        value: {
          controller: {
            postMessage: (_message: unknown, ports?: MessagePort[]) => {
              if (ports) ackPort = ports[0]
            },
          },
          addEventListener: vi.fn(),
          removeEventListener: vi.fn(),
        },
      })
      let auth!: ReturnType<typeof useAuth>
      let pending = true
      function Reader() {
        const result = useEventsListQuery({
          language: "en",
          limit: 12,
          is_active: true,
          order: "starts_at_desc",
        })
        return <span data-testid="event-reader">{result.events.length}</span>
      }
      function Owner({ readers }: { readers: number }) {
        const value = useAuth()
        const currentPending = useContext(AuthBootstrapContext)
        useEffect(() => {
          auth = value
          pending = currentPending
        }, [value, currentPending])
        return (
          <>
            {readers > 0 && <Reader key="a" />}
            {readers > 1 && <Reader key="b" />}
          </>
        )
      }
      const client = createQueryClient()
      client.setDefaultOptions({
        ...client.getDefaultOptions(),
        queries: { ...client.getDefaultOptions().queries, retryDelay: 0 },
      })
      const tree = (readers: number) => (
        <QueryClientProvider client={client}>
          <AuthProvider>
            <Owner readers={readers} />
          </AuthProvider>
        </QueryClientProvider>
      )
      const view = render(tree(0))
      try {
        await waitFor(() => expect(api.get).toHaveBeenCalledWith("/users/me", expect.anything()))
        await act(async () => {
          profile.resolve({ data: testUser })
        })
        await waitFor(() =>
          expect(api.get).toHaveBeenCalledWith("/auth/session/signing-key", expect.anything())
        )
        await act(async () => {
          onlineManager.setOnline(false)
          auth.setUser(testUser)
        })
        await waitFor(() => expect(useAuthStore.getState().user?.id).toBe(testUser.id))
        expect(hasActiveProfileBootstrap(client)).toBe(true)
        mocks.events.mockRejectedValueOnce(new Error("synthetic offline"))
        act(() => {
          void prefetchEventsListQuery(client, {
            language: "en",
            limit: 12,
            is_active: true,
            order: "starts_at_desc",
          })
        })
        await waitFor(() => expect(mocks.events).toHaveBeenCalledTimes(1))
        const query = client
          .getQueryCache()
          .getAll()
          .find((q) => q.queryKey[0] === "events" && q.queryKey[1] === "list")!
        await waitFor(() => expect(query.state.fetchStatus).toBe("paused"), { timeout: 1500 })
        view.rerender(tree(count))
        expect(query.getObserversCount()).toBe(count)
        await act(async () => {
          onlineManager.setOnline(true)
        })
        expect(pending).toBe(true)
        expect(mocks.events).toHaveBeenCalledTimes(1)
        await act(async () => {
          signing.resolve({ data: { signing_key: "session-key" } })
        })
        await waitFor(() => expect(ackPort).toBeDefined())
        expect(mocks.events).toHaveBeenCalledTimes(1)
        await act(async () => {
          ackPort!.postMessage(true)
        })
        await waitFor(() => expect(pending).toBe(false))
        await waitFor(() => expect(mocks.events).toHaveBeenCalledTimes(2), { timeout: 1500 })
        await waitFor(() => expect(view.getAllByTestId("event-reader")).toHaveLength(count))
        expect(query.state.status).toBe("success")
      } finally {
        view.unmount()
        await act(async () => {
          signing.resolve({ data: { signing_key: "session-key" } })
        })
        client.clear()
      }
    }
  )
  it("keeps shared offline retries alive when one standalone observer unmounts", async () => {
    useAuthStore.setState({ user: testUser, loading: false })
    onlineManager.setOnline(false)
    mocks.events.mockRejectedValueOnce(new Error("synthetic offline"))
    mocks.notifications.mockRejectedValueOnce(new Error("synthetic offline"))
    function Reader() {
      useNotifications()
      useEventsListQuery({ language: "en", limit: 12, is_active: true, order: "starts_at_desc" })
      return null
    }
    const client = createQueryClient()
    client.setDefaultOptions({
      ...client.getDefaultOptions(),
      queries: { ...client.getDefaultOptions().queries, retryDelay: 0 },
    })
    const tree = (first: boolean) => (
      <QueryClientProvider client={client}>
        {first && <Reader key="first" />}
        <Reader key="second" />
      </QueryClientProvider>
    )
    const view = render(tree(true))
    try {
      await waitFor(() => expect(mocks.events).toHaveBeenCalledTimes(1))
      await waitFor(() => expect(mocks.notifications).toHaveBeenCalledTimes(1))
      const eventQuery = client
        .getQueryCache()
        .find({ queryKey: ["events", "list"], exact: false })!
      const notificationsQuery = client
        .getQueryCache()
        .find({ queryKey: ["notifications", "list"], exact: true })!
      await waitFor(() => expect(eventQuery.state.fetchStatus).toBe("paused"))
      await waitFor(() => expect(notificationsQuery.state.fetchStatus).toBe("paused"))
      expect(eventQuery.getObserversCount()).toBe(2)
      expect(notificationsQuery.getObserversCount()).toBe(2)
      view.rerender(tree(false))
      expect(eventQuery.getObserversCount()).toBe(1)
      expect(notificationsQuery.getObserversCount()).toBe(1)
      await act(async () => {
        onlineManager.setOnline(true)
        client.getQueryCache().onOnline()
      })
      await waitFor(() => expect(mocks.events).toHaveBeenCalledTimes(2), { timeout: 1500 })
      await waitFor(() => expect(mocks.notifications).toHaveBeenCalledTimes(2), { timeout: 1500 })
      expect(eventQuery.state.status).toBe("success")
      expect(notificationsQuery.state.status).toBe("success")
    } finally {
      view.unmount()
      client.clear()
    }
  })
})
