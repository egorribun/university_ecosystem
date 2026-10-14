import { useEffect, type MutableRefObject, type PropsWithChildren } from "react"
import { act, cleanup, render, renderHook, waitFor } from "@testing-library/react"
import { QueryClientProvider, useQuery, type QueryClient } from "@tanstack/react-query"
import { HttpResponse, http } from "msw"
import { hydrateRoot, type Root } from "react-dom/client"
import { renderToString } from "react-dom/server"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { hmac } from "@noble/hashes/hmac.js"
import { sha256 } from "@noble/hashes/sha2.js"
import { utf8ToBytes } from "@noble/hashes/utils.js"

import api from "@/api/client"
import { createQueryClient, getQueryCacheIdentity, setQueryCacheIdentity } from "@/app/queryClient"
import { AuthProvider, useAuth } from "@/contexts/AuthContext"
import { currentUserQueryKey, currentUserQueryOptions } from "@/api/hooks/users"
import { renderWithRouter } from "@/tests/helpers/renderWithRouter"
import { testUser } from "@/tests/mocks/handlers"
import { server } from "@/tests/mocks/server"
import { useAuthStore } from "@/stores/useAuthStore"
import { acceptBrowserSessionGeneration } from "@/stores/sessionEpoch"
import {
  PROFILE_CACHE_SCHEMA_VERSION,
  PROFILE_CACHE_STORAGE_KEY,
  useProfileSync,
  type CacheSignaturePayload,
} from "@/hooks/auth/useProfileSync"
import { getRouter, type RouterContext } from "@/router"

type SsrAuthGetter = (() => RouterContext["auth"] | undefined) | undefined

declare global {
  var __ssrAuthGetter__: SsrAuthGetter
}

const deferred = <T,>() => {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((finish) => {
    resolve = finish
  })
  return { promise, resolve }
}

const snapshotStorage = (storage: Storage): Array<[string, string]> => {
  const entries: Array<[string, string]> = []
  for (let index = 0; index < storage.length; index += 1) {
    const key = storage.key(index)
    if (key !== null) entries.push([key, storage.getItem(key)!])
  }
  return entries
}
const restoreStorage = (storage: Storage, entries: Array<[string, string]>) => {
  storage.clear()
  for (const [key, value] of entries) storage.setItem(key, value)
}

/**
 * Wave 134 SW1 — Bridge mechanism integration tests.
 *
 * Asserts the cache-identity invariant introduced by the bridge:
 *
 *   useProfileSync's auto-fetch effect now calls
 *     queryClient.fetchQuery(currentUserQueryOptions())
 *   instead of fetchCurrentUser({signal}) directly.
 *
 * When an SSR loader pre-populates the cache via
 *   context.queryClient.ensureQueryData(currentUserQueryOptions())
 * the bridged effect must consume that cache (within staleTime) — NOT fire
 * a duplicate /users/me network call.
 *
 * Closes W133 §Honesty probe #3 + #4 (disjoint-cache risk between SSR
 * loaders and useProfileSync's auto-fetch effect — duplicated network
 * calls hitting the backend twice on cold-load of /dashboard, /profile,
 * /settings, /schedule).
 *
 * The factory's queryFn delegates to the SAME `fetchCurrentUser` function
 * used pre-W134, so retry-on-500-with-cleared-cache + cache-envelope
 * header logic is preserved (covered by AuthContext.requests.test.tsx).
 */

describe("Wave 134 SW1 — useProfileSync bridge", () => {
  let savedAuth: ReturnType<typeof useAuthStore.getState>
  let savedLocal: Array<[string, string]>
  let savedSession: Array<[string, string]>
  let savedSsrAuthGetter: SsrAuthGetter
  let clients: QueryClient[]
  let operations: Array<Promise<PromiseSettledResult<unknown>>>
  const track = <T,>(promise: Promise<T>): Promise<T> => {
    operations.push(
      promise.then(
        (value) => ({ status: "fulfilled" as const, value }),
        (reason: unknown) => ({ status: "rejected" as const, reason })
      )
    )
    return promise
  }
  const createOwnedClient = () => {
    const client = createQueryClient()
    clients.push(client)
    return client
  }

  beforeEach(() => {
    savedAuth = useAuthStore.getState()
    savedLocal = snapshotStorage(localStorage)
    savedSession = snapshotStorage(sessionStorage)
    savedSsrAuthGetter = globalThis.__ssrAuthGetter__
    clients = []
    operations = []
    // A previous authenticated fixture must not invalidate a newly prefetched
    // client when the next AuthProvider starts its independent cold bootstrap.
    useAuthStore.setState(useAuthStore.getInitialState(), true)
    localStorage.clear()
    sessionStorage.clear()
    acceptBrowserSessionGeneration()

    // Preserve native crypto while owning every pending persistence primitive.
    const subtle = window.crypto.subtle
    const importKey = subtle.importKey.bind(subtle)
    const deriveKey = subtle.deriveKey.bind(subtle)
    const encrypt = subtle.encrypt.bind(subtle)
    const decrypt = subtle.decrypt.bind(subtle)
    const verify = subtle.verify.bind(subtle)
    vi.spyOn(subtle, "importKey").mockImplementation((...args) =>
      track(Reflect.apply(importKey, subtle, args) as Promise<CryptoKey>)
    )
    vi.spyOn(subtle, "deriveKey").mockImplementation((...args) => track(deriveKey(...args)))
    vi.spyOn(subtle, "encrypt").mockImplementation((...args) => track(encrypt(...args)))
    vi.spyOn(subtle, "decrypt").mockImplementation((...args) => track(decrypt(...args)))
    vi.spyOn(subtle, "verify").mockImplementation((...args) => track(verify(...args)))
  })

  afterEach(async () => {
    const failures: unknown[] = []
    const attempt = (action: () => void) => {
      try {
        action()
      } catch (error) {
        failures.push(error)
      }
    }
    try {
      attempt(cleanup)
      for (const client of clients) {
        try {
          await client.cancelQueries()
        } catch (error) {
          failures.push(error)
        }
      }
      await act(async () => {
        let drained = 0
        while (drained < operations.length) {
          const batch = operations.slice(drained)
          drained = operations.length
          for (const outcome of await Promise.all(batch)) {
            if (outcome.status === "rejected") failures.push(outcome.reason)
          }
        }
      })
    } finally {
      for (const client of clients) attempt(() => client.clear())
      attempt(() => vi.restoreAllMocks())
      attempt(() => useAuthStore.setState(savedAuth, true))
      attempt(() => restoreStorage(localStorage, savedLocal))
      attempt(() => restoreStorage(sessionStorage, savedSession))
      attempt(() => {
        globalThis.__ssrAuthGetter__ = savedSsrAuthGetter
      })
      attempt(acceptBrowserSessionGeneration)
    }
    if (failures.length) throw new AggregateError(failures, "Auth bridge cleanup failed")
  })

  it("queryKey shape matches across both definition sites", () => {
    // useProfileSync.ts:58 + api/hooks/users.ts:52 both export the same
    // tuple — cache identity is unified at the queryKey level. If either
    // site drifts, the bridge breaks silently (different cache slots).
    expect(currentUserQueryKey).toEqual(["users", "me"])
    expect(currentUserQueryOptions().queryKey).toEqual(currentUserQueryKey)
  })

  it("rejects a current-user cache without a matching committed owner", async () => {
    // A query value alone does not establish which authenticated session owns
    // it. The browser must fetch the current profile instead of trusting this
    // orphaned cache row.
    const queryClient = createOwnedClient()
    const unownedProfile = { ...testUser, id: "unowned-cache-profile" }
    setQueryCacheIdentity(null)
    queryClient.setQueryData(currentUserQueryKey, unownedProfile)

    const getSpy = vi.spyOn(api, "get").mockImplementation((url) => {
      if (url === "/auth/session/signing-key") {
        return Promise.resolve({ data: { signing_key: "session-key" } } as any)
      }
      if (url === "/users/me") {
        return Promise.resolve({ data: testUser } as any)
      }
      throw new Error(`Unexpected url: ${url}`)
    })

    const wrapper = ({ children }: PropsWithChildren) => (
      <QueryClientProvider client={queryClient}>
        <AuthProvider>{children}</AuthProvider>
      </QueryClientProvider>
    )

    const { result } = renderHook(() => useAuth(), { wrapper })
    expect(result.current.user?.id).not.toBe(unownedProfile.id)
    await waitFor(() => {
      expect(result.current.user?.id).toBe(testUser.id)
      expect(queryClient.getQueryData<{ id: string }>(currentUserQueryKey)?.id).toBe(testUser.id)
    })

    const userMeCalls = getSpy.mock.calls.filter(([url]) => url === "/users/me")
    expect(userMeCalls).toHaveLength(1)
  })

  it.each([
    ["a primitive", 42],
    ["an object without an id", { email: "orphan@example.invalid" }],
    ["an unsupported boolean id", { id: true, email: "orphan@example.invalid" }],
    ["a numeric id from another owner", { id: 42, email: "orphan@example.invalid" }],
  ])("does not expose %s from the current-user cache", async (_shape, cachedValue) => {
    setQueryCacheIdentity(null)
    const queryClient = createOwnedClient()
    queryClient.setQueryData(currentUserQueryKey, cachedValue, {
      updatedAt: 0,
    })
    const profileObservations: unknown[] = []
    const getSpy = vi.spyOn(api, "get").mockImplementation((url) => {
      if (url === "/users/me") return Promise.resolve({ data: testUser } as any)
      if (url === "/auth/session/signing-key") {
        return Promise.resolve({
          data: { signing_key: "session-key" },
        } as any)
      }
      throw new Error(`Unexpected url: ${url}`)
    })
    const wrapper = ({ children }: PropsWithChildren) => (
      <QueryClientProvider client={queryClient}>
        <AuthProvider>{children}</AuthProvider>
      </QueryClientProvider>
    )

    const { result } = renderHook(
      () => {
        const { user } = useAuth()
        const profile = useQuery({
          ...currentUserQueryOptions(),
          enabled: false,
        })
        useEffect(() => {
          profileObservations.push(profile.data)
        }, [profile.data])
        return { user }
      },
      { wrapper }
    )

    await waitFor(() => expect(result.current.user?.id).toBe(testUser.id))
    expect(queryClient.getQueryData(currentUserQueryKey)).toEqual(testUser)
    expect(profileObservations.some((profile) => profile === cachedValue)).toBe(false)
    expect(getSpy.mock.calls.filter(([url]) => url === "/users/me")).toHaveLength(1)
  })

  it("refetches a stale known-owner canonical profile through the guarded query function", async () => {
    const owner = testUser.id
    const key = "known-owner-canonical-query-key"
    const cachedSnapshot = {
      id: owner,
      full_name: "Cached route owner",
      group_id: null,
      avatar_url: null,
      cover_url: null,
      is_active: true,
      spotify_connected: false,
    }
    const payload: CacheSignaturePayload = {
      version: PROFILE_CACHE_SCHEMA_VERSION,
      expiresAt: Date.now() + 5 * 60_000,
      data: cachedSnapshot,
    }
    const signature = btoa(
      Array.from(hmac(sha256, utf8ToBytes(key), utf8ToBytes(JSON.stringify(payload))))
        .map((byte) => String.fromCharCode(byte))
        .join("")
    )
    localStorage.setItem(PROFILE_CACHE_STORAGE_KEY, JSON.stringify({ ...payload, signature }))
    localStorage.setItem("ecosystem.profile.cache.version", String(PROFILE_CACHE_SCHEMA_VERSION))

    setQueryCacheIdentity(owner)
    const queryClient = createOwnedClient()
    queryClient.setQueryData(currentUserQueryKey, { ...testUser, id: owner }, { updatedAt: 0 })
    const canonicalQueryHash = queryClient.getQueryCache().find({
      queryKey: currentUserQueryKey,
      exact: true,
    })?.queryHash
    expect(canonicalQueryHash).toBeDefined()

    const authoritativeProfile = {
      ...testUser,
      full_name: "Confirmed route owner",
    }
    // The HTTP JSON response omits the fixture's undefined optional fields.
    // Assert the meaningful server-confirmed profile contract instead of
    // requiring object properties that JSON cannot carry.
    const expectedAuthoritativeFields = {
      id: authoritativeProfile.id,
      full_name: authoritativeProfile.full_name,
      role: authoritativeProfile.role,
      group_id: authoritativeProfile.group_id,
      is_active: authoritativeProfile.is_active,
    }
    let userMeRequests = 0
    let canonicalFetches = 0
    server.use(
      http.get("*/users/me", () => {
        userMeRequests += 1
        return HttpResponse.json(authoritativeProfile)
      })
    )

    // The hook republishes its verified snapshot during initialization. Keep
    // that canonical row stale until the network fetch starts, modeling an
    // owner-matched route cache whose freshness window has elapsed.
    const stopWatching = queryClient.getQueryCache().subscribe((event) => {
      if (
        event.type !== "updated" ||
        event.query.queryHash !== canonicalQueryHash ||
        event.action.type !== "success"
      ) {
        return
      }
      if (userMeRequests === 0) {
        void queryClient.invalidateQueries({
          queryKey: currentUserQueryKey,
          exact: true,
          refetchType: "none",
        })
      }
    })
    const signingKeyRef = { current: key } as MutableRefObject<string | null>
    const signingKeyPromiseRef = {
      current: null,
    } as MutableRefObject<Promise<string | null> | null>
    const wrapper = ({ children }: PropsWithChildren) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    )
    let unmount: (() => void) | undefined

    const countCanonicalFetches = queryClient.getQueryCache().subscribe((event) => {
      if (
        event.type === "updated" &&
        event.query.queryHash === canonicalQueryHash &&
        event.action.type === "fetch"
      ) {
        canonicalFetches += 1
      }
    })

    try {
      const view = renderHook(
        () =>
          useProfileSync(
            () => undefined,
            signingKeyRef,
            signingKeyPromiseRef,
            async () => key,
            undefined,
            () => true
          ),
        { wrapper }
      )
      unmount = view.unmount

      await waitFor(() => {
        expect(userMeRequests).toBe(1)
        expect(canonicalFetches).toBe(1)
        const hookProfile = view.result.current.user
        const cachedProfile = queryClient.getQueryData(currentUserQueryKey)
        expect(hookProfile).toMatchObject(expectedAuthoritativeFields)
        expect(cachedProfile).toMatchObject(expectedAuthoritativeFields)
        expect(cachedProfile).toEqual(hookProfile)
      })

      expect(getQueryCacheIdentity()).toBe(owner)
      expect(
        queryClient
          .getQueryCache()
          .getAll()
          .map((query) => query.queryKey)
      ).toEqual([currentUserQueryKey])
      expect(
        queryClient
          .getQueryCache()
          .getAll()
          .some((query) => query.meta?.persist === false)
      ).toBe(false)
    } finally {
      unmount?.()
      countCanonicalFetches()
      stopWatching()
    }
  })

  it("falls through to network fetch when cache is empty (factory queryFn invoked)", async () => {
    // No pre-populated cache — bridged effect should invoke factory's
    // queryFn → fetchCurrentUser → api.get("/users/me", ...). Behavior
    // matches pre-W134 useProfileSync auto-fetch path (single network
    // call, not two; factory dedups concurrent calls).
    const queryClient = createOwnedClient()

    const getSpy = vi.spyOn(api, "get").mockImplementation((url) => {
      if (url === "/users/me") {
        return Promise.resolve({ data: testUser } as any)
      }
      if (url === "/auth/session/signing-key") {
        return Promise.resolve({ data: { signing_key: "session-key" } } as any)
      }
      throw new Error(`Unexpected url: ${url}`)
    })

    const wrapper = ({ children }: PropsWithChildren) => (
      <QueryClientProvider client={queryClient}>
        <AuthProvider>{children}</AuthProvider>
      </QueryClientProvider>
    )

    const { result } = renderHook(() => useAuth(), { wrapper })

    await waitFor(() => {
      expect(result.current.user?.id).toBe(testUser.id)
    })

    // /users/me called exactly once via the factory's queryFn delegation
    // path — preserves pre-W134 single-fetch behaviour.
    const userMeCalls = getSpy.mock.calls.filter(([url]) => url === "/users/me")
    expect(userMeCalls).toHaveLength(1)
  })

  it("populates queryClient cache after a network fetch (cache-write side effect)", async () => {
    // Wave 134 SW1 closing-the-loop assertion: after the bridged auto-fetch
    // fires (cache empty → network → user state), the SAME queryClient
    // cache slot is populated for any future consumer (e.g. a sibling
    // useQuery(currentUserQueryOptions()) mounted later) — no separate
    // re-fetch needed.
    const queryClient = createOwnedClient()

    vi.spyOn(api, "get").mockImplementation((url) => {
      if (url === "/users/me") {
        return Promise.resolve({ data: testUser } as any)
      }
      if (url === "/auth/session/signing-key") {
        return Promise.resolve({ data: { signing_key: "session-key" } } as any)
      }
      throw new Error(`Unexpected url: ${url}`)
    })

    const wrapper = ({ children }: PropsWithChildren) => (
      <QueryClientProvider client={queryClient}>
        <AuthProvider>{children}</AuthProvider>
      </QueryClientProvider>
    )

    renderHook(() => useAuth(), { wrapper })

    await waitFor(() => {
      const cached = queryClient.getQueryData(currentUserQueryKey)
      expect(cached).toBeDefined()
      expect((cached as any)?.id).toBe(testUser.id)
    })
  })

  it("keeps the routed subtree mounted until the fetched profile owner commits", async () => {
    const queryClient = createOwnedClient()
    const profileRequestStarted = deferred<void>()
    const profileResponse = deferred<Response>()
    const signingKeyRequestStarted = deferred<void>()
    const signingKeyResponse = deferred<Response>()
    const lifecycle: string[] = []
    let profileRequestCount = 0

    function RouteProbe() {
      const { user } = useAuth()
      useEffect(() => {
        lifecycle.push("mounted")
        return () => {
          lifecycle.push("unmounted")
        }
      }, [])
      return (
        <main data-testid="owner-barrier-route" data-user={user?.id ?? "anonymous"}>
          Authenticated route body
        </main>
      )
    }

    server.use(
      http.get("*/users/me", () => {
        profileRequestCount += 1
        profileRequestStarted.resolve()
        return profileResponse.promise
      }),
      http.get("*/auth/session/signing-key", () => {
        signingKeyRequestStarted.resolve()
        return signingKeyResponse.promise
      })
    )

    try {
      const view = await renderWithRouter({
        ui: RouteProbe,
        path: "/",
        queryClient,
      })
      expect(view.getByTestId("owner-barrier-route")).toBeInTheDocument()
      await profileRequestStarted.promise

      // Let the real MSW-backed profile response finish while the signing-key
      // request remains deferred. The profile is not yet a committed auth
      // owner, so it must not enter the public users/me cache or close routes.
      await act(async () => {
        profileResponse.resolve(HttpResponse.json(testUser))
        await signingKeyRequestStarted.promise
      })
      // Flush the cache notification while the signing-key gate still holds
      // the commit path closed.
      await act(async () => {
        await new Promise<void>((resolve) => setTimeout(resolve, 0))
      })

      const stagedProfiles = queryClient
        .getQueryCache()
        .findAll({ predicate: (query) => query.meta?.persist === false })
      expect(stagedProfiles).toHaveLength(1)
      expect(stagedProfiles[0]?.state.data).toEqual(testUser)
      expect({
        publicProfileVisibleBeforeCommit:
          queryClient.getQueryData<{ id: string }>(currentUserQueryKey)?.id === testUser.id,
        routeVisibleBeforeCommit: view.queryByTestId("owner-barrier-route") !== null,
        routeUserBeforeCommit: view.getByTestId("owner-barrier-route").getAttribute("data-user"),
        committedUserBeforeKey: useAuthStore.getState().user?.id === testUser.id,
        routeUnmountedBeforeCommit: lifecycle.includes("unmounted"),
      }).toEqual({
        publicProfileVisibleBeforeCommit: false,
        routeVisibleBeforeCommit: true,
        routeUserBeforeCommit: "anonymous",
        committedUserBeforeKey: false,
        routeUnmountedBeforeCommit: false,
      })

      await act(async () => {
        signingKeyResponse.resolve(HttpResponse.json({ signing_key: "test-session-signing-key" }))
      })
      await waitFor(() => {
        expect(useAuthStore.getState().user?.id).toBe(testUser.id)
        expect(queryClient.getQueryData<{ id: string }>(currentUserQueryKey)?.id).toBe(testUser.id)
        expect(view.getByTestId("owner-barrier-route")).toHaveAttribute("data-user", testUser.id)
        expect(view.getByTestId("owner-barrier-route")).toBeInTheDocument()
      })
      expect(lifecycle).toEqual(["mounted"])
      expect(
        queryClient.getQueryCache().findAll({ predicate: (query) => query.meta?.persist === false })
      ).toHaveLength(0)
      expect(profileRequestCount).toBe(1)
    } finally {
      await act(async () => {
        profileResponse.resolve(HttpResponse.json(testUser))
        signingKeyResponse.resolve(HttpResponse.json({ signing_key: "test-session-signing-key" }))
      })
    }
  })

  it("keeps a newer bootstrap request when an older cancelled provider finishes cleanup", async () => {
    const queryClient = createOwnedClient()
    const removeQueriesSpy = vi.spyOn(queryClient, "removeQueries")
    const oldProfile = { ...testUser, id: "old-bootstrap-profile" }
    const newProfile = { ...testUser, id: "new-bootstrap-profile" }
    const oldProfileStarted = deferred<void>()
    const newProfileStarted = deferred<void>()
    const oldProfileResponse = deferred<Response>()
    const newProfileResponse = deferred<Response>()
    const oldSigningKeyStarted = deferred<void>()
    const newSigningKeyStarted = deferred<void>()
    const oldSigningKeyResponse = deferred<Response>()
    const newSigningKeyResponse = deferred<Response>()
    let profileRequestCount = 0
    let signingKeyRequestCount = 0
    let logoutCurrent: ReturnType<typeof useAuth>["logout"] | undefined

    function RouteProbe() {
      const auth = useAuth()
      useEffect(() => {
        logoutCurrent = auth.logout
      }, [auth.logout])
      return <main data-testid="bootstrap-owner">{auth.user?.id ?? "anonymous"}</main>
    }

    server.use(
      http.get("*/users/me", () => {
        profileRequestCount += 1
        if (profileRequestCount === 1) {
          oldProfileStarted.resolve()
          return oldProfileResponse.promise
        }
        if (profileRequestCount === 2) {
          newProfileStarted.resolve()
          return newProfileResponse.promise
        }
        throw new Error("Unexpected extra /users/me request")
      }),
      http.get("*/auth/session/signing-key", () => {
        signingKeyRequestCount += 1
        if (signingKeyRequestCount === 1) {
          oldSigningKeyStarted.resolve()
          return oldSigningKeyResponse.promise
        }
        if (signingKeyRequestCount === 2) {
          newSigningKeyStarted.resolve()
          return newSigningKeyResponse.promise
        }
        throw new Error("Unexpected extra signing-key request")
      })
    )

    const tree = (providerKey: string) => (
      <QueryClientProvider client={queryClient}>
        <AuthProvider key={providerKey}>
          <RouteProbe />
        </AuthProvider>
      </QueryClientProvider>
    )
    const view = render(tree("old-provider"))

    try {
      await oldProfileStarted.promise
      await act(async () => {
        oldProfileResponse.resolve(HttpResponse.json(oldProfile))
        await oldSigningKeyStarted.promise
      })
      const oldStage = queryClient
        .getQueryCache()
        .findAll({ predicate: (query) => query.meta?.persist === false })
        .find((query) => (query.state.data as { id?: string } | undefined)?.id === oldProfile.id)
      expect(oldStage).toBeDefined()
      const oldStageKey = oldStage!.queryKey

      // Logout retires the old cold-start request. Its signing-key continuation
      // remains held so its exact-key finally can run after the replacement
      // provider has started a distinct bootstrap request.
      await act(async () => {
        await logoutCurrent?.()
      })
      expect(
        queryClient.getQueryCache().find({ queryKey: oldStageKey, exact: true })
      ).toBeUndefined()
      view.rerender(tree("new-provider"))
      await newProfileStarted.promise
      await act(async () => {
        newProfileResponse.resolve(HttpResponse.json(newProfile))
        await newSigningKeyStarted.promise
      })

      const newStage = queryClient
        .getQueryCache()
        .findAll({ predicate: (query) => query.meta?.persist === false })
        .find((query) => (query.state.data as { id?: string } | undefined)?.id === newProfile.id)
      expect(newStage).toBeDefined()
      expect(newStage!.queryKey).not.toEqual(oldStageKey)

      await act(async () => {
        oldSigningKeyResponse.resolve(
          HttpResponse.json({ signing_key: "old-provider-signing-key" })
        )
      })
      await waitFor(() => {
        expect(removeQueriesSpy).toHaveBeenCalledWith({
          queryKey: oldStageKey,
          exact: true,
        })
      })
      expect(
        queryClient.getQueryCache().find({ queryKey: newStage!.queryKey, exact: true })?.state.data
      ).toEqual(newProfile)
      expect(queryClient.getQueryData(currentUserQueryKey)).toBeNull()
      expect(useAuthStore.getState().user?.id).not.toBe(oldProfile.id)

      await act(async () => {
        newSigningKeyResponse.resolve(
          HttpResponse.json({ signing_key: "new-provider-signing-key" })
        )
      })
      await waitFor(() => {
        expect(useAuthStore.getState().user?.id).toBe(newProfile.id)
        expect(queryClient.getQueryData(currentUserQueryKey)).toEqual(newProfile)
      })
      expect(
        queryClient.getQueryCache().findAll({ predicate: (query) => query.meta?.persist === false })
      ).toHaveLength(0)
      expect(profileRequestCount).toBe(2)
      expect(signingKeyRequestCount).toBe(2)
    } finally {
      await act(async () => {
        oldProfileResponse.resolve(HttpResponse.json(oldProfile))
        newProfileResponse.resolve(HttpResponse.json(newProfile))
        oldSigningKeyResponse.resolve(
          HttpResponse.json({ signing_key: "old-provider-signing-key" })
        )
        newSigningKeyResponse.resolve(
          HttpResponse.json({ signing_key: "new-provider-signing-key" })
        )
      })
      view.unmount()
    }
  })

  it("keeps request-only profile data out of transfer and hydrates behind the owner barrier", async () => {
    const requestProfile = {
      ...testUser,
      id: "request-only-profile-id",
      email: "request-only-profile@example.invalid",
    }
    const browserProfile = {
      ...testUser,
      id: "browser-confirmed-profile-id",
      email: "browser-confirmed-profile@example.invalid",
    }
    let browserRequestStarted = false
    let resolveBrowserResponse: ((value: { data: typeof browserProfile }) => void) | undefined
    const browserResponse = new Promise<{ data: typeof browserProfile }>((resolve) => {
      resolveBrowserResponse = resolve
    })
    let usersMeCallCount = 0
    const profileReads: Array<{
      authUserId: string | null
      cacheProfileId: string | null
    }> = []
    const getSpy = vi.spyOn(api, "get").mockImplementation((url) => {
      if (url === "/users/me") {
        usersMeCallCount += 1
        if (usersMeCallCount === 1) return Promise.resolve({ data: requestProfile } as any)
        browserRequestStarted = true
        return browserResponse as any
      }
      if (url === "/auth/session/signing-key") {
        return Promise.resolve({ data: { signing_key: "session-key" } } as any)
      }
      throw new Error(`Unexpected url: ${url}`)
    })

    vi.stubEnv("SSR", true)
    const requestAuth: RouterContext["auth"] = {
      isAuth: true,
      user: { role: "student" },
      loading: false,
    }
    globalThis.__ssrAuthGetter__ = () => requestAuth
    const serverRouter = getRouter()
    const serverClient = serverRouter.options.context.queryClient
    clients.push(serverClient)
    const secondRequestClient = getRouter().options.context.queryClient
    clients.push(secondRequestClient)
    expect(serverClient).not.toBe(secondRequestClient)
    await serverClient.ensureQueryData(currentUserQueryOptions())
    expect(serverClient.getQueryData(currentUserQueryKey)).toEqual(requestProfile)
    const stagedRequestKey = [
      "auth",
      "bootstrap",
      "current-user",
      "ssr-request-scope",
      1,
      1,
    ] as const
    serverClient.setQueryDefaults(stagedRequestKey, {
      meta: { persist: false },
    })
    const stagedRequestProfile = {
      ...requestProfile,
      id: "staged-request-profile-id",
      email: "staged-request-profile@example.invalid",
    }
    serverClient.setQueryData(stagedRequestKey, stagedRequestProfile)

    const ProfileRouteShell = ({
      assertRequestCache = false,
    }: {
      assertRequestCache?: boolean
    }) => {
      const { user } = useAuth()
      const currentProfile = useQuery({
        ...currentUserQueryOptions(),
        enabled: false,
      })
      if (assertRequestCache && currentProfile.data?.id !== requestProfile.id) {
        throw new Error("The server profile route did not read its request-scoped profile cache")
      }
      useEffect(() => {
        profileReads.push({
          authUserId: user?.id ?? null,
          cacheProfileId: currentProfile.data?.id ?? null,
        })
      }, [currentProfile.data?.id, user?.id])
      return <main data-testid="profile-route-shell">Authenticated profile route</main>
    }
    const routeTree = (
      <QueryClientProvider client={serverClient}>
        <AuthProvider>
          <ProfileRouteShell assertRequestCache />
        </AuthProvider>
      </QueryClientProvider>
    )
    const serverMarkup = renderToString(routeTree)
    expect(getSpy.mock.calls.filter(([url]) => url === "/users/me")).toHaveLength(1)
    expect(serverMarkup).toContain("profile-route-shell")
    expect(serverMarkup).not.toContain(requestProfile.id)
    expect(serverMarkup).not.toContain(requestProfile.email)

    const transferred = await serverRouter.options.dehydrate?.()
    if (!transferred) throw new Error("Expected the request router's dehydration result")
    expect(
      transferred.queries.some(
        (query) => JSON.stringify(query.queryKey) === JSON.stringify(currentUserQueryKey)
      )
    ).toBe(false)
    expect(
      transferred.queries.some(
        (query) => JSON.stringify(query.queryKey) === JSON.stringify(stagedRequestKey)
      )
    ).toBe(false)
    const transferJson = JSON.stringify(transferred)
    expect(transferJson).not.toContain(requestProfile.id)
    expect(transferJson).not.toContain(requestProfile.email)
    expect(transferJson).not.toContain(stagedRequestProfile.id)
    expect(transferJson).not.toContain(stagedRequestProfile.email)

    vi.stubEnv("SSR", false)
    globalThis.__ssrAuthGetter__ = undefined
    setQueryCacheIdentity(null)
    const browserClient = createOwnedClient()
    expect(browserClient.getQueryData(currentUserQueryKey)).toBeUndefined()

    const container = document.createElement("div")
    container.id = "root"
    container.setAttribute("data-ssr-auth", "authenticated:student")
    container.innerHTML = serverMarkup
    document.body.appendChild(container)
    const hydrationErrors: unknown[] = []
    let root: Root | undefined
    const browserTree = (
      <QueryClientProvider client={browserClient}>
        <AuthProvider>
          <ProfileRouteShell />
        </AuthProvider>
      </QueryClientProvider>
    )

    try {
      await act(async () => {
        root = hydrateRoot(container, browserTree, {
          onRecoverableError: (error) => hydrationErrors.push(error),
        })
      })
      await waitFor(() => expect(browserRequestStarted).toBe(true))
      expect(
        hydrationErrors.map((error) => (error instanceof Error ? error.message : String(error)))
      ).toEqual([])
      expect(profileReads.some(({ cacheProfileId }) => cacheProfileId === requestProfile.id)).toBe(
        false
      )

      // Keep the browser request pending through hydration so the test can
      // distinguish an actual markup mismatch from a deliberately immediate
      // auth response racing React's hydration commit.
      await act(async () => {
        resolveBrowserResponse?.({ data: browserProfile })
        await browserResponse
      })
      await waitFor(() => {
        expect(browserClient.getQueryData<{ id: string }>(currentUserQueryKey)?.id).toBe(
          browserProfile.id
        )
        expect(profileReads.some(({ authUserId }) => authUserId === browserProfile.id)).toBe(true)
        expect(container.querySelector('[data-testid="profile-route-shell"]')).not.toBeNull()
      })
      expect(
        hydrationErrors.map((error) => (error instanceof Error ? error.message : String(error)))
      ).toEqual([])

      // A stale server-owned profile introduced into the active browser cache
      // after owner B is confirmed must close the subtree before a committed
      // consumer can observe it.
      await act(async () => {
        browserClient.setQueryData(currentUserQueryKey, requestProfile)
      })
      await waitFor(() => {
        expect(container.querySelector('[data-testid="profile-route-shell"]')).toBeNull()
      })
      expect(
        profileReads.some(
          ({ authUserId, cacheProfileId }) =>
            authUserId === browserProfile.id && cacheProfileId === requestProfile.id
        )
      ).toBe(false)
      expect(profileReads.some(({ cacheProfileId }) => cacheProfileId === requestProfile.id)).toBe(
        false
      )
      expect(getSpy.mock.calls.filter(([url]) => url === "/users/me")).toHaveLength(2)
    } finally {
      if (root) {
        await act(async () => {
          resolveBrowserResponse?.({ data: browserProfile })
          await browserResponse
          root?.unmount()
        })
      } else {
        resolveBrowserResponse?.({ data: browserProfile })
        await browserResponse
      }
      container.remove()
    }
  })
})
