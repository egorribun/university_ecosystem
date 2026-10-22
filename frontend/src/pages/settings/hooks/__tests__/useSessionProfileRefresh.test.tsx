import { QueryCache, QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { act, renderHook, waitFor } from "@testing-library/react"
import type { PropsWithChildren } from "react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import type { User } from "@/types/User"
import { currentUserQueryKey } from "@/hooks/auth/useProfileSync"
import { useSessionProfileRefresh } from "../useSessionProfileRefresh"

const mocks = vi.hoisted(() => ({
  user: { id: "user-1", email: "user@example.test", email_verified_at: null as string | null },
  setUser: vi.fn(),
  fetchCurrentUser: vi.fn(),
}))

vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({ user: mocks.user, setUser: mocks.setUser }),
}))

vi.mock("@/hooks/auth/useProfileSync", () => ({
  currentUserQueryKey: ["users", "me"],
  fetchCurrentUser: (options: { signal?: AbortSignal }) => mocks.fetchCurrentUser(options),
}))

const account = (emailVerifiedAt: string | null) =>
  ({
    id: "user-1",
    email: "user@example.test",
    email_verified_at: emailVerifiedAt,
  }) as User

type ObservedResult<T> = { ok: true; value: T } | { ok: false; error: unknown }
const observe = <T,>(promise: Promise<T>): Promise<ObservedResult<T>> =>
  promise.then(
    (value) => ({ ok: true, value }),
    (error: unknown) => ({ ok: false, error })
  )
const deferred = <T,>() => {
  let resolve!: (value: T) => void
  let reject!: (reason: unknown) => void
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise
    reject = rejectPromise
  })
  return { promise, resolve, reject }
}

beforeEach(() => {
  vi.clearAllMocks()
  mocks.user = { id: "user-1", email: "user@example.test", email_verified_at: null }
})

describe("useSessionProfileRefresh", () => {
  it("cancels a pre-commit profile request and adopts the post-commit response", async () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false, gcTime: Infinity } },
    })
    queryClient.setQueryData(["notifications", "inbox"], { unread: 2 })
    const cancelQueries = vi.spyOn(queryClient, "cancelQueries")
    const staleResponse = deferred<User>()
    const oldQueryFnSettled = deferred<void>()
    const committedMutation = deferred<void>()
    let oldSignal: AbortSignal | undefined
    let mutationCommitted = false

    mocks.fetchCurrentUser
      .mockImplementationOnce((options: { signal?: AbortSignal }) => {
        oldSignal = options.signal
        return staleResponse.promise
      })
      .mockImplementationOnce(() => {
        expect(mutationCommitted).toBe(true)
        return Promise.resolve(account("2026-10-11T12:00:00Z"))
      })

    const oldRequest = queryClient.fetchQuery<User>({
      queryKey: currentUserQueryKey,
      queryFn: async ({ signal }) => {
        const profile = (await mocks.fetchCurrentUser({ signal })) as User
        oldQueryFnSettled.resolve()
        return profile
      },
      staleTime: 0,
    })
    const oldRequestSettled = oldRequest.then(
      () => undefined,
      () => undefined
    )
    await waitFor(() => expect(mocks.fetchCurrentUser).toHaveBeenCalledTimes(1))
    expect(queryClient.getQueryState(currentUserQueryKey)?.fetchStatus).toBe("fetching")

    const wrapper = ({ children }: PropsWithChildren) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    )
    const { result, unmount } = renderHook(() => useSessionProfileRefresh(), { wrapper })

    try {
      let beforeCommit: User | null = null
      await act(async () => {
        beforeCommit = await result.current(() => false)
      })
      expect(beforeCommit).toBeNull()
      expect(mocks.fetchCurrentUser).toHaveBeenCalledTimes(1)
      expect(oldSignal?.aborted).toBe(false)

      let refreshed: User | null = null
      await act(async () => {
        committedMutation.resolve()
        await committedMutation.promise
        mutationCommitted = true
        refreshed = await result.current(() => mutationCommitted)
      })

      const verifiedProfile = account("2026-10-11T12:00:00Z")
      expect(refreshed).toEqual(verifiedProfile)
      expect(mocks.fetchCurrentUser).toHaveBeenCalledTimes(2)
      expect(oldSignal?.aborted).toBe(true)
      expect(cancelQueries).toHaveBeenCalledWith({ queryKey: currentUserQueryKey, exact: true })
      expect(mocks.setUser).toHaveBeenCalledTimes(1)
      expect(mocks.setUser).toHaveBeenCalledWith(verifiedProfile)
      expect(queryClient.getQueryData(currentUserQueryKey)).toEqual(verifiedProfile)
      expect(queryClient.getQueryData(["notifications", "inbox"])).toEqual({ unread: 2 })

      // Simulate a transport that completes after its AbortSignal was fired.
      // TanStack must ignore this canceled query's late stale result.
      await act(async () => {
        staleResponse.resolve(account(null))
        await oldQueryFnSettled.promise
        await Promise.resolve()
        await Promise.resolve()
        await oldRequestSettled
      })
      expect(queryClient.getQueryData(currentUserQueryKey)).toEqual(verifiedProfile)
      expect(mocks.setUser).toHaveBeenCalledTimes(1)
    } finally {
      unmount()
      queryClient.clear()
    }
  })

  it("stops before fetching if the session guard expires during cancellation", async () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false, gcTime: Infinity } },
    })
    const cancellation = deferred<void>()
    const cancelQueries = vi.spyOn(queryClient, "cancelQueries").mockImplementation(async () => {
      await cancellation.promise
    })
    const wrapper = ({ children }: PropsWithChildren) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    )
    const { result, unmount } = renderHook(() => useSessionProfileRefresh(), { wrapper })

    try {
      let guardCalls = 0
      let refresh!: Promise<User | null>
      await act(async () => {
        refresh = result.current(() => ++guardCalls < 3)
      })
      await waitFor(() =>
        expect(cancelQueries).toHaveBeenCalledWith({ queryKey: currentUserQueryKey, exact: true })
      )
      expect(guardCalls).toBe(2)

      cancellation.resolve()
      let refreshed: User | null = null
      await act(async () => {
        refreshed = await refresh
      })
      expect(refreshed).toBeNull()
      expect(guardCalls).toBe(3)
      expect(mocks.fetchCurrentUser).not.toHaveBeenCalled()
      expect(mocks.setUser).not.toHaveBeenCalled()
    } finally {
      unmount()
      queryClient.clear()
    }
  })

  it("serializes concurrent committed refreshes so each caller gets its own fresh profile", async () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false, gcTime: Infinity } },
    })
    const cancelQueries = vi.spyOn(queryClient, "cancelQueries")
    const firstResponse = deferred<User>()
    const secondResponse = deferred<User>()
    const firstProfile = account("2026-10-11T12:01:00Z")
    const secondProfile = account("2026-10-11T12:02:00Z")
    let firstSignal: AbortSignal | undefined
    let secondSignal: AbortSignal | undefined
    let firstCommitted = false
    let secondCommitted = false

    mocks.fetchCurrentUser
      .mockImplementationOnce((options: { signal?: AbortSignal }) => {
        expect(firstCommitted).toBe(true)
        firstSignal = options.signal
        return firstResponse.promise
      })
      .mockImplementationOnce((options: { signal?: AbortSignal }) => {
        expect(secondCommitted).toBe(true)
        secondSignal = options.signal
        return secondResponse.promise
      })

    const wrapper = ({ children }: PropsWithChildren) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    )
    const { result, unmount } = renderHook(
      () => [useSessionProfileRefresh(), useSessionProfileRefresh()] as const,
      { wrapper }
    )

    try {
      let firstOutcome!: Promise<ObservedResult<User | null>>
      await act(async () => {
        firstCommitted = true
        firstOutcome = observe(result.current[0](() => firstCommitted))
        await Promise.resolve()
      })
      await waitFor(() => expect(mocks.fetchCurrentUser).toHaveBeenCalledTimes(1))
      expect(cancelQueries).toHaveBeenCalledTimes(1)

      let secondOutcome!: Promise<ObservedResult<User | null>>
      await act(async () => {
        secondCommitted = true
        secondOutcome = observe(result.current[1](() => secondCommitted))
        await Promise.resolve()
      })
      expect(mocks.fetchCurrentUser).toHaveBeenCalledTimes(1)
      expect(cancelQueries).toHaveBeenCalledTimes(1)
      expect(firstSignal?.aborted).toBe(false)

      let firstSettled!: ObservedResult<User | null>
      await act(async () => {
        firstResponse.resolve(firstProfile)
        firstSettled = await firstOutcome
      })
      if (!firstSettled.ok) throw firstSettled.error
      expect(firstSettled.value).toEqual(firstProfile)
      await waitFor(() => expect(mocks.fetchCurrentUser).toHaveBeenCalledTimes(2))
      expect(cancelQueries).toHaveBeenCalledTimes(2)
      expect(firstSignal?.aborted).toBe(false)

      let secondSettled!: ObservedResult<User | null>
      await act(async () => {
        secondResponse.resolve(secondProfile)
        secondSettled = await secondOutcome
      })
      if (!secondSettled.ok) throw secondSettled.error
      expect(secondSettled.value).toEqual(secondProfile)
      expect(secondSignal?.aborted).toBe(false)
      expect(mocks.setUser).toHaveBeenCalledTimes(2)
      expect(mocks.setUser).toHaveBeenNthCalledWith(1, firstProfile)
      expect(mocks.setUser).toHaveBeenNthCalledWith(2, secondProfile)
      expect(queryClient.getQueryData(currentUserQueryKey)).toEqual(secondProfile)
    } finally {
      firstResponse.resolve(firstProfile)
      secondResponse.resolve(secondProfile)
      unmount()
      queryClient.clear()
    }
  })

  it("drops a queued refresh whose session guard expires before its turn", async () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false, gcTime: Infinity } },
    })
    const cancelQueries = vi.spyOn(queryClient, "cancelQueries")
    const firstResponse = deferred<User>()
    const firstProfile = account("2026-10-11T12:03:00Z")
    let firstSignal: AbortSignal | undefined
    let firstCommitted = false
    let queuedSessionCurrent = true

    mocks.fetchCurrentUser.mockImplementationOnce((options: { signal?: AbortSignal }) => {
      expect(firstCommitted).toBe(true)
      firstSignal = options.signal
      return firstResponse.promise
    })

    const wrapper = ({ children }: PropsWithChildren) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    )
    const { result, unmount } = renderHook(
      () => [useSessionProfileRefresh(), useSessionProfileRefresh()] as const,
      { wrapper }
    )

    try {
      let firstOutcome!: Promise<ObservedResult<User | null>>
      await act(async () => {
        firstCommitted = true
        firstOutcome = observe(result.current[0](() => firstCommitted))
        await Promise.resolve()
      })
      await waitFor(() => expect(mocks.fetchCurrentUser).toHaveBeenCalledTimes(1))

      let queuedGuardCalls = 0
      let queuedOutcome!: Promise<ObservedResult<User | null>>
      await act(async () => {
        queuedOutcome = observe(
          result.current[1](() => {
            queuedGuardCalls += 1
            return queuedSessionCurrent
          })
        )
        await Promise.resolve()
      })
      expect(queuedGuardCalls).toBe(1)
      expect(cancelQueries).toHaveBeenCalledTimes(1)
      queuedSessionCurrent = false

      let firstSettled!: ObservedResult<User | null>
      await act(async () => {
        firstResponse.resolve(firstProfile)
        firstSettled = await firstOutcome
      })
      if (!firstSettled.ok) throw firstSettled.error
      const queuedSettled = await queuedOutcome
      expect(queuedSettled).toEqual({ ok: true, value: null })
      expect(queuedGuardCalls).toBe(2)
      expect(cancelQueries).toHaveBeenCalledTimes(1)
      expect(mocks.fetchCurrentUser).toHaveBeenCalledTimes(1)
      expect(firstSignal?.aborted).toBe(false)
      expect(mocks.setUser).toHaveBeenCalledOnce()
      expect(mocks.setUser).toHaveBeenCalledWith(firstProfile)
    } finally {
      firstResponse.resolve(firstProfile)
      unmount()
      queryClient.clear()
    }
  })

  it("does not request a profile when the current-user query starts after session expiry", async () => {
    const queryCache = new QueryCache()
    let sessionCurrent = true
    const unsubscribe = queryCache.subscribe((event) => {
      if (
        event.type === "updated" &&
        event.action.type === "fetch" &&
        event.query.queryKey[0] === "users" &&
        event.query.queryKey[1] === "me"
      ) {
        sessionCurrent = false
      }
    })
    const queryClient = new QueryClient({
      queryCache,
      defaultOptions: { queries: { retry: false, gcTime: Infinity } },
    })
    const wrapper = ({ children }: PropsWithChildren) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    )
    const { result, unmount } = renderHook(() => useSessionProfileRefresh(), { wrapper })

    try {
      let outcome!: ObservedResult<User | null>
      await act(async () => {
        outcome = await observe(result.current(() => sessionCurrent))
      })

      expect(outcome.ok).toBe(false)
      if (!outcome.ok) expect(outcome.error).toMatchObject({ name: "AbortError" })
      expect(mocks.fetchCurrentUser).not.toHaveBeenCalled()
      expect(mocks.setUser).not.toHaveBeenCalled()
      expect(queryClient.getQueryData(currentUserQueryKey)).toBeUndefined()
    } finally {
      unsubscribe()
      unmount()
      queryClient.clear()
    }
  })

  it("does not cache a deferred response after the session expires in flight", async () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false, gcTime: Infinity } },
    })
    const response = deferred<User>()
    const profile = account("2026-10-11T12:05:00Z")
    let sessionCurrent = true
    mocks.fetchCurrentUser.mockImplementationOnce(() => response.promise)
    const wrapper = ({ children }: PropsWithChildren) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    )
    const { result, unmount } = renderHook(() => useSessionProfileRefresh(), { wrapper })

    try {
      let pending!: Promise<ObservedResult<User | null>>
      await act(async () => {
        pending = observe(result.current(() => sessionCurrent))
        await Promise.resolve()
      })
      await waitFor(() => expect(mocks.fetchCurrentUser).toHaveBeenCalledOnce())

      sessionCurrent = false
      let outcome!: ObservedResult<User | null>
      await act(async () => {
        response.resolve(profile)
        outcome = await pending
      })

      expect(outcome.ok).toBe(false)
      if (!outcome.ok) expect(outcome.error).toMatchObject({ name: "AbortError" })
      expect(mocks.setUser).not.toHaveBeenCalled()
      expect(queryClient.getQueryData(currentUserQueryKey)).toBeUndefined()
    } finally {
      response.resolve(profile)
      unmount()
      queryClient.clear()
    }
  })

  it("rejects a foreign-session profile before caching or auth-state adoption", async () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false, gcTime: Infinity } },
    })
    const foreignProfile = { ...account("2026-10-11T12:06:00Z"), id: "user-2" } as User
    mocks.fetchCurrentUser.mockResolvedValueOnce(foreignProfile)
    const wrapper = ({ children }: PropsWithChildren) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    )
    const { result, unmount } = renderHook(() => useSessionProfileRefresh(), { wrapper })

    try {
      let outcome!: ObservedResult<User | null>
      await act(async () => {
        outcome = await observe(result.current(() => true))
      })

      expect(outcome.ok).toBe(false)
      if (!outcome.ok) expect(outcome.error).toMatchObject({ name: "AbortError" })
      expect(mocks.fetchCurrentUser).toHaveBeenCalledOnce()
      expect(mocks.setUser).not.toHaveBeenCalled()
      expect(queryClient.getQueryData(currentUserQueryKey)).toBeUndefined()
    } finally {
      unmount()
      queryClient.clear()
    }
  })

  it("skips auth-state adoption when QueryCache observes the response after session expiry", async () => {
    const queryCache = new QueryCache()
    let sessionCurrent = true
    const unsubscribe = queryCache.subscribe((event) => {
      if (
        event.type === "updated" &&
        event.action.type === "success" &&
        event.query.queryKey[0] === "users" &&
        event.query.queryKey[1] === "me"
      ) {
        sessionCurrent = false
      }
    })
    const queryClient = new QueryClient({
      queryCache,
      defaultOptions: { queries: { retry: false, gcTime: Infinity } },
    })
    const response = deferred<User>()
    const profile = account("2026-10-11T12:07:00Z")
    mocks.fetchCurrentUser.mockImplementationOnce(() => response.promise)
    const wrapper = ({ children }: PropsWithChildren) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    )
    const { result, unmount } = renderHook(() => useSessionProfileRefresh(), { wrapper })

    try {
      let pending!: Promise<ObservedResult<User | null>>
      await act(async () => {
        pending = observe(result.current(() => sessionCurrent))
        await Promise.resolve()
      })
      await waitFor(() => expect(mocks.fetchCurrentUser).toHaveBeenCalledOnce())

      let outcome!: ObservedResult<User | null>
      await act(async () => {
        response.resolve(profile)
        outcome = await pending
      })

      expect(outcome).toEqual({ ok: true, value: null })
      expect(mocks.setUser).not.toHaveBeenCalled()
      expect(queryClient.getQueryData(currentUserQueryKey)).toEqual(profile)
    } finally {
      unsubscribe()
      response.resolve(profile)
      unmount()
      queryClient.clear()
    }
  })

  it("releases queued refreshes when a preceding profile request fails", async () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false, gcTime: Infinity } },
    })
    const cancelQueries = vi.spyOn(queryClient, "cancelQueries")
    const firstResponse = deferred<User>()
    const secondProfile = account("2026-10-11T12:04:00Z")
    let firstCommitted = false
    let secondCommitted = false

    mocks.fetchCurrentUser
      .mockImplementationOnce(() => {
        expect(firstCommitted).toBe(true)
        return firstResponse.promise
      })
      .mockImplementationOnce(() => {
        expect(secondCommitted).toBe(true)
        return Promise.resolve(secondProfile)
      })

    const wrapper = ({ children }: PropsWithChildren) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    )
    const { result, unmount } = renderHook(
      () => [useSessionProfileRefresh(), useSessionProfileRefresh()] as const,
      { wrapper }
    )

    try {
      let firstOutcome!: Promise<ObservedResult<User | null>>
      await act(async () => {
        firstCommitted = true
        firstOutcome = observe(result.current[0](() => firstCommitted))
        await Promise.resolve()
      })
      await waitFor(() => expect(mocks.fetchCurrentUser).toHaveBeenCalledTimes(1))

      let secondOutcome!: Promise<ObservedResult<User | null>>
      await act(async () => {
        secondCommitted = true
        secondOutcome = observe(result.current[1](() => secondCommitted))
        await Promise.resolve()
      })
      expect(mocks.fetchCurrentUser).toHaveBeenCalledTimes(1)
      expect(cancelQueries).toHaveBeenCalledTimes(1)

      let failedFirst!: ObservedResult<User | null>
      await act(async () => {
        firstResponse.reject(new Error("first profile refresh failed"))
        failedFirst = await firstOutcome
      })
      expect(failedFirst.ok).toBe(false)
      await waitFor(() => expect(mocks.fetchCurrentUser).toHaveBeenCalledTimes(2))
      const refreshedSecond = await secondOutcome
      expect(refreshedSecond).toEqual({ ok: true, value: secondProfile })
      expect(cancelQueries).toHaveBeenCalledTimes(2)
      expect(mocks.setUser).toHaveBeenCalledOnce()
      expect(mocks.setUser).toHaveBeenCalledWith(secondProfile)
      expect(queryClient.getQueryData(currentUserQueryKey)).toEqual(secondProfile)
    } finally {
      firstResponse.resolve(secondProfile)
      unmount()
      queryClient.clear()
    }
  })
})
