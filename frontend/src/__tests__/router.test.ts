/**
 * Wave 126 polish — unit tests for `src/router.ts:getRouter()` factory's
 * SSR auth context flow.
 *
 * Verifies the contract introduced in W126 SW3 + SW4: per-request auth
 * state set by `src/server.ts` via `node:async_hooks` AsyncLocalStorage,
 * exposed via `globalThis.__ssrAuthGetter__` getter, consumed by
 * `getRouter()` to construct routers with real auth context for SSR.
 *
 * Tests run in jsdom — `node:async_hooks` import in `src/server.ts` is
 * NOT exercised here; we directly stub `globalThis.__ssrAuthGetter__` to
 * simulate what server.ts would set at runtime, then assert the factory
 * reads from it.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import {
  dehydrate as dehydrateQueryClient,
  QueryClient,
  type DehydratedState,
} from "@tanstack/react-query"
import { queryClient as browserQueryClient, setQueryCacheIdentity } from "@/app/queryClient"
import { dashboardEventsQueryKey } from "@/hooks/useDashboardEvents"
import { dashboardStoriesQueryKey } from "@/hooks/useDashboardStories"
import { getRouter, type RouterContext } from "../router"

type SsrAuthGetter = (() => RouterContext["auth"] | undefined) | undefined
declare global {
  // mirrors src/server.ts declaration so tests can stub the getter directly.

  var __ssrAuthGetter__: SsrAuthGetter
}

describe("router.getRouter() — Wave 126 SSR auth context", { timeout: 60000 }, () => {
  let originalGetter: SsrAuthGetter

  beforeEach(() => {
    originalGetter = globalThis.__ssrAuthGetter__
  })

  afterEach(() => {
    globalThis.__ssrAuthGetter__ = originalGetter
    vi.unstubAllEnvs()
    setQueryCacheIdentity(null)
    browserQueryClient.clear()
  })

  it("falls back to DEFAULT_AUTH (loading:false, isAuth:false) when getter is undefined", () => {
    globalThis.__ssrAuthGetter__ = undefined
    const router = getRouter()
    expect(router.options.context).toBeDefined()
    expect(router.options.context.auth).toEqual({
      isAuth: false,
      user: null,
      loading: false,
    })
  })

  it("falls back to DEFAULT_AUTH when getter returns undefined explicitly", () => {
    globalThis.__ssrAuthGetter__ = () => undefined
    const router = getRouter()
    expect(router.options.context.auth).toEqual({
      isAuth: false,
      user: null,
      loading: false,
    })
  })

  it("uses SSR auth state when getter returns authenticated user", () => {
    const ssrAuth: RouterContext["auth"] = {
      isAuth: true,
      user: { role: "student" },
      loading: false,
    }
    globalThis.__ssrAuthGetter__ = () => ssrAuth
    const router = getRouter()
    expect(router.options.context.auth).toEqual(ssrAuth)
  })

  it("uses SSR auth state with admin role when getter returns admin user", () => {
    globalThis.__ssrAuthGetter__ = () => ({
      isAuth: true,
      user: { role: "admin" },
      loading: false,
    })
    const router = getRouter()
    expect(router.options.context.auth.user?.role).toBe("admin")
    expect(router.options.context.auth.isAuth).toBe(true)
  })

  it("calls getter fresh on each invocation (per-request scope)", () => {
    let callCount = 0
    globalThis.__ssrAuthGetter__ = () => {
      callCount += 1
      return {
        isAuth: callCount % 2 === 0,
        user: null,
        loading: false,
      }
    }
    const r1 = getRouter()
    const r2 = getRouter()
    expect(callCount).toBe(2)
    expect(r1.options.context.auth.isAuth).toBe(false)
    expect(r2.options.context.auth.isAuth).toBe(true)
  })

  it("creates a fresh QueryClient for each server request", () => {
    globalThis.__ssrAuthGetter__ = undefined
    vi.stubEnv("SSR", true)
    const r1 = getRouter()
    const r2 = getRouter()
    expect(r1.options.context.queryClient).not.toBe(r2.options.context.queryClient)
  })

  it("uses the shared offline-first QueryClient policy during SSR", () => {
    globalThis.__ssrAuthGetter__ = undefined
    vi.stubEnv("SSR", true)
    const queryClient = getRouter().options.context.queryClient
    const defaults = queryClient.getDefaultOptions()

    expect(defaults.queries).toMatchObject({
      staleTime: 5 * 60_000,
      gcTime: 30 * 60_000,
      retry: 1,
      networkMode: "offlineFirst",
    })
    expect(defaults.mutations).toMatchObject({
      retry: 0,
      gcTime: 0,
      networkMode: "offlineFirst",
    })
  })

  it("transfers only projected dashboard data before confirmed ownership", async () => {
    const ssrAuthStub: RouterContext["auth"] = {
      isAuth: true,
      user: { role: "student" },
      loading: false,
    }
    globalThis.__ssrAuthGetter__ = () => ssrAuthStub
    vi.stubEnv("SSR", true)
    setQueryCacheIdentity(null)
    browserQueryClient.clear()

    const serverRouter = getRouter()
    const serverClient = serverRouter.options.context.queryClient
    expect(serverRouter.options.context.auth).toEqual(ssrAuthStub)
    serverClient.setQueryData(dashboardEventsQueryKey, {
      items: [
        {
          id: "event-1",
          title: "Public event",
          starts_at: "2026-10-08T10:00:00.000Z",
          location: null,
          is_registered: true,
          my_qr_token: "attendance-field-sentinel",
        },
      ],
    })
    serverClient.setQueryData(dashboardStoriesQueryKey, [
      {
        id: "story-1",
        created_at: "2026-10-01T00:00:00.000Z",
        expires_at: "2026-10-31T00:00:00.000Z",
        is_active: true,
        published_at: "2026-10-01T00:00:00.000Z",
        short_text: "Public preview",
        title: "Public story",
        cover_url: null,
        cover_url_optimized: "https://images.example/story.webp",
        cta_url: "https://app.example/stories/story-1",
        created_by: "creator-field-sentinel",
      },
    ])
    serverClient.setQueryData(["auth", "profile"], { id: "profile-private-sentinel" })
    serverClient.setQueryData(["session", "owner"], { id: "session-private-sentinel" })
    const serverMutation = serverClient.getMutationCache().build(serverClient, {
      mutationKey: ["auth", "refresh"],
      mutationFn: async () => undefined,
    })
    await serverMutation.execute(undefined)

    const dehydrated = await serverRouter.options.dehydrate?.()
    if (!dehydrated) throw new Error("SSR router did not produce a dehydrated state")
    expect(dehydrated.queries.map((query) => query.queryKey)).toEqual([
      dashboardEventsQueryKey,
      dashboardStoriesQueryKey,
    ])
    expect(dehydrated.mutations).toEqual([])
    expect(dehydrated.queries[0]?.state.data).toEqual({
      items: [
        {
          id: "event-1",
          title: "Public event",
          starts_at: "2026-10-08T10:00:00.000Z",
          location: null,
        },
      ],
    })
    expect(dehydrated.queries[1]?.state.data).toEqual([
      {
        id: "story-1",
        created_at: "2026-10-01T00:00:00.000Z",
        expires_at: "2026-10-31T00:00:00.000Z",
        is_active: true,
        published_at: "2026-10-01T00:00:00.000Z",
        short_text: "Public preview",
        title: "Public story",
        cover_url: null,
        cover_url_optimized: "https://images.example/story.webp",
        cta_url: "https://app.example/stories/story-1",
      },
    ])
    const serializedState = JSON.stringify(dehydrated)
    expect(serializedState).not.toContain("attendance-field-sentinel")
    expect(serializedState).not.toContain("creator-field-sentinel")
    expect(serializedState).not.toContain("profile-private-sentinel")
    expect(serializedState).not.toContain("session-private-sentinel")

    vi.stubEnv("SSR", false)
    globalThis.__ssrAuthGetter__ = undefined
    const browserRouter = getRouter()
    expect(browserRouter.options.context.queryClient).toBe(browserQueryClient)
    expect(browserRouter.options.context.auth.isAuth).toBe(false)

    const eventQuery = dehydrated.queries.find(
      (query) => JSON.stringify(query.queryKey) === JSON.stringify(dashboardEventsQueryKey)
    )
    if (!eventQuery) throw new Error("Expected sanitized event query")
    const mismatchedHashState: DehydratedState = {
      mutations: [],
      queries: [{ ...eventQuery, queryHash: "non-canonical-hash" }],
    }
    const hydrateUntrustedState = browserRouter.options.hydrate as unknown as (
      state: DehydratedState
    ) => void | Promise<void>
    await hydrateUntrustedState(mismatchedHashState)
    expect(browserQueryClient.getQueryData(dashboardEventsQueryKey)).toBeUndefined()
    await hydrateUntrustedState(null as unknown as DehydratedState)
    await hydrateUntrustedState({ mutations: [], queries: undefined } as unknown as DehydratedState)
    expect(browserQueryClient.getQueryData(dashboardEventsQueryKey)).toBeUndefined()

    const privateSource = new QueryClient()
    privateSource.setQueryData(["auth", "profile"], { id: "injected-profile" })
    const privateQuery = dehydrateQueryClient(privateSource).queries[0]
    if (!privateQuery) throw new Error("Expected private query fixture")
    const mutationSource = new QueryClient()
    const injectedMutation = mutationSource.getMutationCache().build(mutationSource, {
      mutationKey: ["auth", "refresh"],
      mutationFn: async () => undefined,
    })
    await injectedMutation.execute(undefined)
    const externalMutations = dehydrateQueryClient(mutationSource, {
      shouldDehydrateMutation: () => true,
    }).mutations
    expect(externalMutations).toHaveLength(1)
    const malformedQueries = [
      null,
      "not-a-query",
      { ...eventQuery, state: null },
      { ...eventQuery, queryKey: "dashboard/events" },
      { ...eventQuery, queryHash: 7 },
      { ...eventQuery, dehydratedAt: "invalid-time" },
      { ...eventQuery, queryKey: ["dashboard", "events", "foreign"] },
      { ...eventQuery, state: { ...eventQuery.state, status: "error" } },
      { ...eventQuery, state: { ...eventQuery.state, dataUpdateCount: "invalid-count" } },
      { ...eventQuery, state: { ...eventQuery.state, dataUpdatedAt: "invalid-time" } },
      { ...eventQuery, state: { ...eventQuery.state, isInvalidated: "invalid-flag" } },
      { ...eventQuery, state: { ...eventQuery.state, data: { items: [null] } } },
    ]
    const injectedState = {
      mutations: externalMutations,
      queries: [...malformedQueries, ...dehydrated.queries, privateQuery],
    } as unknown as DehydratedState
    await hydrateUntrustedState(injectedState)

    expect(browserQueryClient.getQueryData(dashboardEventsQueryKey)).toEqual({
      items: [
        {
          id: "event-1",
          title: "Public event",
          starts_at: "2026-10-08T10:00:00.000Z",
          location: null,
        },
      ],
    })
    expect(browserQueryClient.getQueryData(dashboardStoriesQueryKey)).toEqual([
      {
        id: "story-1",
        created_at: "2026-10-01T00:00:00.000Z",
        expires_at: "2026-10-31T00:00:00.000Z",
        is_active: true,
        published_at: "2026-10-01T00:00:00.000Z",
        short_text: "Public preview",
        title: "Public story",
        cover_url: null,
        cover_url_optimized: "https://images.example/story.webp",
        cta_url: "https://app.example/stories/story-1",
      },
    ])
    expect(browserQueryClient.getQueryData(["auth", "profile"])).toBeUndefined()
    expect(browserQueryClient.getQueryData(["session", "owner"])).toBeUndefined()
    expect(browserQueryClient.getMutationCache().getAll()).toHaveLength(0)

    setQueryCacheIdentity("confirmed-owner")
    expect(browserQueryClient.getQueryData(dashboardEventsQueryKey)).toBeUndefined()
    setQueryCacheIdentity(null)
    browserQueryClient.clear()
  })

  it("provides an accessible visible pending component for suspended routes", () => {
    globalThis.__ssrAuthGetter__ = undefined
    const pending = getRouter().options.defaultPendingComponent?.({})

    expect(pending).toMatchObject({
      type: "div",
      props: {
        role: "status",
        "aria-live": "polite",
        children: expect.objectContaining({
          type: "span",
          props: { children: "Loading…" },
        }),
      },
    })
  })

  it("uses history-entry scroll restoration while filter replacements opt out separately", () => {
    const options = getRouter().options
    expect(options.scrollRestoration).toBe(true)
    expect(options.getScrollRestorationKey).toBeUndefined()
  })

  it("disables view transitions on touch WebKit so the old snapshot cannot block links", async () => {
    vi.stubGlobal("WebKitPoint", class WebKitPoint {})
    vi.stubGlobal(
      "matchMedia",
      vi.fn((query: string) => ({ matches: query === "(hover: none) and (pointer: coarse)" }))
    )
    try {
      vi.resetModules()
      const { getRouter: getWebKitRouter } = await import("../router")
      expect(getWebKitRouter().options.defaultViewTransition).toBe(false)
      expect(window.matchMedia).toHaveBeenCalledWith("(hover: none) and (pointer: coarse)")
    } finally {
      vi.unstubAllGlobals()
    }
  })
})
