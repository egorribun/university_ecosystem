import { StrictMode, useEffect } from "react"
import { onlineManager, QueryClientProvider } from "@tanstack/react-query"
import { act, cleanup, render, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, expect, it, vi } from "vitest"
import api from "@/api/client"
import { eventsListQueryKey, prefetchEventsListQuery } from "@/api/hooks/events"
import { createQueryClient, setQueryCacheIdentity } from "@/app/queryClient"
import { AuthProvider, useAuth } from "@/contexts/AuthContext"
import { Route as EventsIndexRoute } from "@/routes/_auth/events.index"
import {
  hasActiveProfileBootstrap,
  startProfileBootstrap,
} from "@/hooks/auth/profileBootstrapActivity"
import { useAuthStore } from "@/stores/useAuthStore"
import { acceptBrowserSessionGeneration } from "@/stores/sessionEpoch"
import { testUser } from "@/tests/mocks/handlers"
import { cryptoWorker } from "@/utils/cryptoWorker"
import * as logger from "@/app/logger"

type GeneratedSdk = typeof import("@/api/generated/sdk.gen")
const mocks = vi.hoisted(() => ({ events: vi.fn() }))
vi.mock("@/api/generated/sdk.gen", async (load) => ({
  ...(await load<GeneratedSdk>()),
  allEventsApiV1EventsGet: mocks.events,
}))
vi.mock("@/pages/Events", () => ({ default: () => null }))

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((done) => {
    resolve = done
  })
  return { promise, resolve }
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
  mocks.events.mockReset().mockResolvedValue({
    status: 200,
    data: { items: [], total: 0, limit: 12, has_more: false, next_cursor: null },
  })
})
afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  vi.unstubAllEnvs()
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

it("skip same-client prefetch while signing bootstrap is pending", async () => {
  vi.stubEnv("SSR", false)
  const profile = deferred<{ data: typeof testUser }>()
  const signing = deferred<{ data: { signing_key: string } }>()
  vi.spyOn(api, "get").mockImplementation((url) => {
    if (url === "/users/me") return profile.promise
    if (url === "/auth/session/signing-key") return signing.promise
    throw new Error(`Unexpected request ${url}`)
  })
  const auth = { current: null as ReturnType<typeof useAuth> | null }
  function CaptureAuth() {
    const value = useAuth()
    useEffect(() => {
      auth.current = value
    }, [value])
    return null
  }
  const client = createQueryClient()
  const view = render(
    <QueryClientProvider client={client}>
      <AuthProvider>
        <CaptureAuth />
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
      auth.current!.setUser(testUser)
    })
    await waitFor(() => expect(useAuthStore.getState().user?.id).toBe(testUser.id))
    const loader = EventsIndexRoute.options.loader as (args: {
      context: { queryClient: typeof client }
    }) => Promise<void>
    await act(async () => {
      await loader({ context: { queryClient: client } })
    })
    expect(mocks.events).not.toHaveBeenCalled()
  } finally {
    view.unmount()
    await act(async () => {
      signing.resolve({ data: { signing_key: "session-key" } })
    })
    client.clear()
    vi.unstubAllEnvs()
  }
})

it("leases are per client, overlap-safe, resumable and final", () => {
  const one = createQueryClient()
  const two = createQueryClient()
  const a = startProfileBootstrap(one)
  const b = startProfileBootstrap(one)
  const c = startProfileBootstrap(two)
  expect(hasActiveProfileBootstrap(one)).toBe(true)
  expect(hasActiveProfileBootstrap(two)).toBe(true)
  a.suspend()
  a.suspend()
  expect(hasActiveProfileBootstrap(one)).toBe(true)
  b.finish()
  b.finish()
  expect(hasActiveProfileBootstrap(one)).toBe(false)
  expect(hasActiveProfileBootstrap(two)).toBe(true)
  a.resume()
  a.resume()
  expect(hasActiveProfileBootstrap(one)).toBe(true)
  a.finish()
  a.resume()
  expect(hasActiveProfileBootstrap(one)).toBe(false)
  c.finish()
  expect(hasActiveProfileBootstrap(two)).toBe(false)
  one.clear()
  two.clear()
})

it("StrictMode replay retains a live lease and unmount removes it", async () => {
  const profile = deferred<{ data: typeof testUser }>()
  const get = vi.spyOn(api, "get").mockReturnValue(profile.promise)
  const client = createQueryClient()
  const view = render(
    <StrictMode>
      <QueryClientProvider client={client}>
        <AuthProvider>
          <span />
        </AuthProvider>
      </QueryClientProvider>
    </StrictMode>
  )
  try {
    await waitFor(() => expect(get).toHaveBeenCalledWith("/users/me", expect.anything()))
    expect(hasActiveProfileBootstrap(client)).toBe(true)
    view.unmount()
    expect(hasActiveProfileBootstrap(client)).toBe(false)
    await act(async () => {
      profile.resolve({ data: testUser })
    })
    expect(hasActiveProfileBootstrap(client)).toBe(false)
  } finally {
    view.unmount()
    client.clear()
  }
})

it("only same-client in-flight bootstrap blocks, then settled loader fetches", async () => {
  vi.stubEnv("SSR", false)
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
  const auth = { current: null as ReturnType<typeof useAuth> | null }
  function CaptureAuth() {
    const value = useAuth()
    useEffect(() => {
      auth.current = value
    }, [value])
    return null
  }
  const client = createQueryClient()
  const other = createQueryClient()
  const view = render(
    <QueryClientProvider client={client}>
      <AuthProvider>
        <CaptureAuth />
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
      auth.current!.setUser(testUser)
    })
    await waitFor(() => expect(useAuthStore.getState().user?.id).toBe(testUser.id))
    expect(hasActiveProfileBootstrap(client)).toBe(true)
    expect(hasActiveProfileBootstrap(other)).toBe(false)
    const loader = EventsIndexRoute.options.loader as (args: {
      context: { queryClient: typeof client }
    }) => Promise<void>
    await act(async () => {
      await loader({ context: { queryClient: client } })
    })
    expect(mocks.events).not.toHaveBeenCalled()
    await act(async () => {
      await loader({ context: { queryClient: other } })
    })
    expect(mocks.events).toHaveBeenCalledTimes(1)
    await act(async () => {
      signing.resolve({ data: { signing_key: "session-key" } })
    })
    await waitFor(() => expect(ackPort).toBeDefined())
    expect(hasActiveProfileBootstrap(client)).toBe(true)
    await act(async () => {
      ackPort!.postMessage(true)
    })
    await waitFor(() => expect(hasActiveProfileBootstrap(client)).toBe(false))
    await act(async () => {
      await loader({ context: { queryClient: client } })
    })
    expect(mocks.events).toHaveBeenCalledTimes(2)
  } finally {
    view.unmount()
    client.clear()
    other.clear()
    vi.unstubAllEnvs()
  }
})

it("overlapping real providers keep the other lease after unmount and late completion", async () => {
  const first = deferred<{ data: { signing_key: string } }>()
  const second = deferred<{ data: { signing_key: string } }>()
  let keyRequests = 0
  vi.spyOn(api, "get").mockImplementation((url) => {
    if (url === "/users/me") return Promise.resolve({ data: testUser })
    if (url === "/auth/session/signing-key")
      return keyRequests++ === 0 ? first.promise : second.promise
    throw new Error(`Unexpected request ${url}`)
  })
  const client = createQueryClient()
  const tree = (showFirst: boolean) => (
    <QueryClientProvider client={client}>
      {showFirst && (
        <AuthProvider key="a">
          <span>first</span>
        </AuthProvider>
      )}
      <AuthProvider key="b">
        <span>second</span>
      </AuthProvider>
    </QueryClientProvider>
  )
  const view = render(tree(true))
  try {
    await waitFor(() => expect(keyRequests).toBe(2))
    expect(hasActiveProfileBootstrap(client)).toBe(true)
    view.rerender(tree(false))
    expect(hasActiveProfileBootstrap(client)).toBe(true)
    await act(async () => {
      first.resolve({ data: { signing_key: "session-key" } })
    })
    expect(hasActiveProfileBootstrap(client)).toBe(true)
    await act(async () => {
      second.resolve({ data: { signing_key: "session-key" } })
    })
    await waitFor(() => expect(hasActiveProfileBootstrap(client)).toBe(false))
  } finally {
    view.unmount()
    client.clear()
  }
})

it("bootstrap network failure releases the lease", async () => {
  vi.spyOn(logger, "logError").mockImplementation(() => undefined)
  let rejectProfile!: (error: Error) => void
  const get = vi.spyOn(api, "get").mockReturnValue(
    new Promise((_resolve, reject) => {
      rejectProfile = reject
    })
  )
  const client = createQueryClient()
  const view = render(
    <QueryClientProvider client={client}>
      <AuthProvider>
        <span />
      </AuthProvider>
    </QueryClientProvider>
  )
  try {
    await waitFor(() => expect(get).toHaveBeenCalledWith("/users/me", expect.anything()))
    expect(hasActiveProfileBootstrap(client)).toBe(true)
    await act(async () => {
      rejectProfile(new Error("controlled offline backend"))
    })
    await waitFor(() => expect(hasActiveProfileBootstrap(client)).toBe(false))
  } finally {
    view.unmount()
    client.clear()
  }
})

it("SSR skips prefetch even without a lease", async () => {
  vi.stubEnv("SSR", true)
  useAuthStore.setState({ user: testUser, loading: false })
  const client = createQueryClient()
  try {
    expect(hasActiveProfileBootstrap(client)).toBe(false)
    const loader = EventsIndexRoute.options.loader as (args: {
      context: { queryClient: typeof client }
    }) => Promise<void>
    await loader({ context: { queryClient: client } })
    expect(mocks.events).not.toHaveBeenCalled()
  } finally {
    client.clear()
    vi.unstubAllEnvs()
  }
})

it("keeps an in-flight bootstrap attached to its original client across provider replacement", async () => {
  const profile = deferred<{ data: typeof testUser }>()
  const get = vi.spyOn(api, "get").mockReturnValue(profile.promise)
  const first = createQueryClient()
  const second = createQueryClient()
  const tree = (client: typeof first) => (
    <QueryClientProvider client={client}>
      <AuthProvider>
        <span />
      </AuthProvider>
    </QueryClientProvider>
  )
  const view = render(tree(first))
  try {
    await waitFor(() => expect(get).toHaveBeenCalledWith("/users/me", expect.anything()))
    expect(hasActiveProfileBootstrap(first)).toBe(true)
    view.rerender(tree(second))
    expect(hasActiveProfileBootstrap(first)).toBe(true)
    expect(hasActiveProfileBootstrap(second)).toBe(false)
    view.unmount()
    expect(hasActiveProfileBootstrap(first)).toBe(false)
    await act(async () => {
      profile.resolve({ data: testUser })
    })
    expect(hasActiveProfileBootstrap(first)).toBe(false)
  } finally {
    view.unmount()
    first.clear()
    second.clear()
  }
})

it("allows confirmed-owner offline prefetch while its bootstrap remains pending", async () => {
  vi.stubEnv("SSR", false)
  const profile = deferred<{ data: typeof testUser }>()
  const signing = deferred<{ data: { signing_key: string } }>()
  vi.spyOn(api, "get").mockImplementation((url) => {
    if (url === "/users/me") return profile.promise
    if (url === "/auth/session/signing-key") return signing.promise
    throw new Error(`Unexpected request ${url}`)
  })
  const auth = { current: null as ReturnType<typeof useAuth> | null }
  function CaptureAuth() {
    const value = useAuth()
    useEffect(() => {
      auth.current = value
    }, [value])
    return null
  }
  const client = createQueryClient()
  const view = render(
    <QueryClientProvider client={client}>
      <AuthProvider>
        <CaptureAuth />
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
      auth.current!.setUser(testUser)
    })
    await waitFor(() => expect(useAuthStore.getState().user?.id).toBe(testUser.id))
    await act(async () => {
      onlineManager.setOnline(false)
    })
    expect(hasActiveProfileBootstrap(client)).toBe(true)
    const loader = EventsIndexRoute.options.loader as (args: {
      context: { queryClient: typeof client }
    }) => Promise<void>
    await act(async () => {
      await loader({ context: { queryClient: client } })
    })
    expect(mocks.events).toHaveBeenCalledTimes(1)
  } finally {
    view.unmount()
    await act(async () => {
      signing.resolve({ data: { signing_key: "session-key" } })
    })
    client.clear()
  }
})

it("does not retry an offline failed prefetch online before bootstrap finishes", async () => {
  onlineManager.setOnline(false)
  useAuthStore.setState({ user: testUser, loading: false })
  mocks.events.mockRejectedValueOnce(new Error("offline transport"))
  const client = createQueryClient()
  const defaults = client.getDefaultOptions()
  client.setDefaultOptions({
    ...defaults,
    queries: { ...defaults.queries, retry: 1, retryDelay: 0, staleTime: 0 },
  })
  const activity = startProfileBootstrap(client)
  const filters = { language: "en", limit: 12, is_active: true, order: "starts_at_desc" as const }
  const previous = {
    pages: [{ items: [], total: 0, limit: 12, has_more: false, next_cursor: null }],
    pageParams: [null],
  }
  client.setQueryData(eventsListQueryKey(filters), previous)
  try {
    const pending = prefetchEventsListQuery(client, filters)
    await waitFor(() => expect(mocks.events).toHaveBeenCalledTimes(1))
    await waitFor(() => {
      const query = client.getQueryCache().find({ queryKey: ["events", "list"], exact: false })
      expect(query?.state.fetchStatus).toBe("paused")
    })
    onlineManager.setOnline(true)
    client.getQueryCache().onOnline()
    await pending
    expect(mocks.events).toHaveBeenCalledTimes(1)
    const query = client
      .getQueryCache()
      .find({ queryKey: eventsListQueryKey(filters), exact: true })
    expect(query?.state.fetchStatus).toBe("idle")
    expect(query?.state.data).toEqual(previous)
    expect(query?.state.isInvalidated).toBe(true)
    activity.finish()
    await prefetchEventsListQuery(client, filters)
    expect(mocks.events).toHaveBeenCalledTimes(2)
  } finally {
    activity.finish()
    client.clear()
  }
})

it("returns promptly for direct online prefetch during the same bootstrap", async () => {
  onlineManager.setOnline(true)
  useAuthStore.setState({ user: testUser, loading: false })
  const client = createQueryClient()
  const activity = startProfileBootstrap(client)
  try {
    await prefetchEventsListQuery(client, { language: "en", is_active: true })
    expect(mocks.events).not.toHaveBeenCalled()
    expect(
      client.getQueryCache().find({ queryKey: ["events", "list"], exact: false })
    ).toBeUndefined()
  } finally {
    activity.finish()
    client.clear()
  }
})
