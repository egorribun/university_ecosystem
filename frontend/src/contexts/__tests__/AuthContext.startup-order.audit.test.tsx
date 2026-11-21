import { onlineManager, QueryClientProvider } from "@tanstack/react-query"
import { act, cleanup, render, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { AxiosError, AxiosHeaders } from "axios"
import { hydrateRoot } from "react-dom/client"
import { renderToString } from "react-dom/server"
import api from "@/api/client"
import { createQueryClient, setQueryCacheIdentity } from "@/app/queryClient"
import { AuthProvider, useAuth } from "@/contexts/AuthContext"
import { AuthBootstrapContext } from "@/contexts/AuthBootstrapContext"
import { useEventsListQuery } from "@/api/hooks/events"
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
})
