import { useCallback, type PropsWithChildren } from "react"
import { act, cleanup, renderHook, waitFor } from "@testing-library/react"
import { CancelledError, isCancelledError, QueryClientProvider } from "@tanstack/react-query"
import { HttpResponse, http } from "msw"
import { afterEach, beforeEach, describe, expect, it, onTestFinished, vi } from "vitest"

import { createQueryClient } from "@/app/queryClient"
import { resetEtagCache } from "@/api/client"
import { useAuthApi } from "@/hooks/auth/useAuthApi"
import { currentUserQueryKey, useProfileSync } from "@/hooks/auth/useProfileSync"
import { useSessionCrypto } from "@/hooks/auth/useSessionCrypto"
import { acceptBrowserSessionGeneration } from "@/stores/sessionEpoch"
import { useAuthStore } from "@/stores/useAuthStore"
import { testUser } from "@/tests/mocks/handlers"
import { server } from "@/tests/mocks/server"
import { withExpectedConsole } from "@/tests/strictConsole"

const generationKey = "ecosystem.session.generation.v1"
const snapshot = (storage: Storage): Array<[string, string]> => {
  const entries: Array<[string, string]> = []
  for (let index = 0; index < storage.length; index += 1) {
    const key = storage.key(index)
    if (key === null) continue
    const value = storage.getItem(key)
    if (value !== null) entries.push([key, value])
  }
  return entries
}
const restore = (storage: Storage, entries: Array<[string, string]>) => {
  storage.clear()
  for (const [key, value] of entries) storage.setItem(key, value)
}
const deferred = <T,>() => {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((finish) => {
    resolve = finish
  })
  return { promise, resolve }
}

const createOperationTracker = () => {
  const operations: Array<Promise<PromiseSettledResult<unknown>>> = []
  const track = <T,>(promise: Promise<T>): Promise<T> => {
    // Attach both handlers immediately. A rejection stays available to the
    // owner and to cleanup without becoming an unhandled teardown rejection.
    operations.push(
      promise.then(
        (value) => ({ status: "fulfilled" as const, value }),
        (reason: unknown) => ({ status: "rejected" as const, reason })
      )
    )
    return promise
  }
  return { operations, track }
}

const disposeOwnedWork = async ({
  unmount,
  releases,
  operations,
  cancel,
  clear,
}: {
  unmount: () => void
  releases: Array<() => void>
  operations: Array<Promise<PromiseSettledResult<unknown>>>
  cancel: () => Promise<void>
  clear: () => void
}) => {
  const failures: unknown[] = []
  const attempt = (action: () => void) => {
    try {
      action()
    } catch (error) {
      failures.push(error)
    }
  }
  attempt(unmount)
  for (const release of releases) attempt(release)
  try {
    await cancel()
  } catch (error) {
    failures.push(error)
  }
  // Settling a tracked operation may enqueue another owned continuation.
  // Drain those additions too before clearing or restoring shared state.
  let drained = 0
  while (drained < operations.length) {
    const batch = operations.slice(drained)
    drained = operations.length
    for (const outcome of await Promise.all(batch)) {
      if (outcome.status === "rejected") failures.push(outcome.reason)
    }
  }
  attempt(clear)
  if (failures.length) throw new AggregateError(failures, "Profile fixture disposal failed")
}

let savedAuth: ReturnType<typeof useAuthStore.getState>
let savedLocal: Array<[string, string]>
let savedSession: Array<[string, string]>
let disposers: Array<() => Promise<void>>

beforeEach(() => {
  savedAuth = useAuthStore.getState()
  savedLocal = snapshot(localStorage)
  savedSession = snapshot(sessionStorage)
  disposers = []
  useAuthStore.setState(useAuthStore.getInitialState(), true)
  localStorage.clear()
  sessionStorage.clear()
  acceptBrowserSessionGeneration()
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
    for (const dispose of disposers) {
      try {
        await dispose()
      } catch (error) {
        failures.push(error)
      }
    }
  } finally {
    attempt(cleanup)
    attempt(() => vi.restoreAllMocks())
    attempt(() => useAuthStore.setState(savedAuth, true))
    attempt(() => restore(localStorage, savedLocal))
    attempt(() => restore(sessionStorage, savedSession))
    attempt(acceptBrowserSessionGeneration)
  }
  if (failures.length) throw new AggregateError(failures, "Profile state test cleanup failed")
})

const withCacheClearDiagnostic = <T,>(action: () => T | Promise<T>) =>
  withExpectedConsole(
    "warn",
    (args) =>
      args[0] === "profile_cache.cleared" &&
      (args[1] as { reason?: string } | undefined)?.reason === "parse_error",
    action
  )

const withoutDiagnostic = async <T,>(action: () => T | Promise<T>) => action()

const renderProfile = async (authenticated = true, holdKey = false) =>
  (holdKey ? withoutDiagnostic : withCacheClearDiagnostic)(async () => {
    const queryClient = createQueryClient()
    if (authenticated) queryClient.setQueryData(currentUserQueryKey, testUser)
    server.use(http.get("*/users/me", () => new HttpResponse(null, { status: 401 })))
    const { operations, track } = createOperationTracker()
    const releases: Array<() => void> = []
    // Signing-key backoff can leave an online profile without a cache key.
    // Keep that supported state here so profile persistence adds no crypto work.
    const keyResult = deferred<null>()
    let acquiringKey = false
    if (!holdKey) keyResult.resolve(null)
    releases.push(() => keyResult.resolve(null))
    const ensureKey = () => {
      acquiringKey = true
      return track(keyResult.promise)
    }
    const wrapper = ({ children }: PropsWithChildren) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    )
    const view = renderHook(
      () => {
        const crypto = useSessionCrypto()
        const updateSessionSigningKey = crypto.updateSessionSigningKey
        const updateKey = useCallback(
          (key: string | null) => {
            void track(updateSessionSigningKey(key))
          },
          [updateSessionSigningKey]
        )
        const profile = useProfileSync(
          updateKey,
          crypto.sessionSigningKeyRef,
          crypto.sessionSigningKeyPromiseRef,
          ensureKey,
          undefined,
          crypto.isCurrentSigningSession
        )
        const auth = useAuthApi(
          profile.user,
          profile.setUser,
          profile.updatePendingMfa,
          profile.handleUnauthorized,
          updateKey,
          profile.authOperation,
          profile.setAuthOperation,
          resetEtagCache,
          profile.pendingMfa
        )
        return { ...profile, refresh: auth.refresh }
      },
      { wrapper }
    )
    let disposal: Promise<void> | undefined
    const dispose = (cancel = () => queryClient.cancelQueries()) => {
      disposal ??= disposeOwnedWork({
        unmount: view.unmount,
        releases,
        operations,
        cancel,
        clear: () => queryClient.clear(),
      })
      return disposal
    }
    disposers.push(() => dispose())
    onTestFinished(() => dispose())
    if (holdKey) {
      await waitFor(() => expect(acquiringKey).toBe(true), { timeout: 2_000 })
      expect(view.result.current.user).toBeNull()
    } else {
      await waitFor(() => expect(view.result.current.loading).toBe(false), { timeout: 2_000 })
      expect(view.result.current.user).toEqual(authenticated ? testUser : null)
    }
    return {
      ...view,
      queryClient,
      track,
      releases,
      dispose,
      releaseKey: () => keyResult.resolve(null),
    }
  })

const changeBrowserGeneration = () => {
  localStorage.setItem(
    generationKey,
    JSON.stringify({ nonce: "another-tab-generation", hash: null })
  )
}

const runCachedMutation = (queryClient: ReturnType<typeof createQueryClient>) => {
  const mutation = queryClient.getMutationCache().build(queryClient, {
    mutationFn: async () => "updated",
    onSuccess: (value) => queryClient.setQueryData(["settings", "saved"], value),
  })
  return mutation.execute(undefined)
}

describe("profile state transitions", () => {
  it("keeps a cleared profile after an older bootstrap key attempt completes without a key", async () => {
    const view = await renderProfile(true, true)
    await withCacheClearDiagnostic(() => act(() => view.result.current.setUser(testUser)))
    expect(view.result.current.user?.id).toBe(testUser.id)
    await withCacheClearDiagnostic(() => act(() => view.track(view.result.current.refresh())))
    expect(view.result.current.user).toBeNull()

    await act(async () => {
      view.releaseKey()
    })
    await waitFor(() => expect(view.result.current.loading).toBe(false), { timeout: 2_000 })

    expect(view.result.current.user).toBeNull()
    expect(view.queryClient.getQueryData(currentUserQueryKey)).toBeNull()
  })

  it("preserves unrelated cached data when the same account refreshes its profile", async () => {
    const view = await renderProfile()
    const events = [{ id: "saved-event", title: "Saved event" }]
    view.queryClient.setQueryData(["events", "saved"], events)

    await withCacheClearDiagnostic(() =>
      act(() => view.result.current.setUser({ ...testUser, full_name: "Refreshed profile" }))
    )

    expect(view.result.current.user?.full_name).toBe("Refreshed profile")
    expect(view.queryClient.getQueryData(currentUserQueryKey)).toEqual(view.result.current.user)
    expect(view.queryClient.getQueryData(["events", "saved"])).toEqual(events)
  })

  it("clears cached data when unauthorized handling repeats with no profile or signing key", async () => {
    const view = await renderProfile(false)
    view.queryClient.setQueryData(["events", "saved"], [{ id: "saved-event" }])

    await withCacheClearDiagnostic(() => act(() => view.track(view.result.current.refresh())))

    expect(view.result.current.user).toBeNull()
    expect(view.queryClient.getQueryData(["events", "saved"])).toBeUndefined()
  })

  it("discards a pending mutation completion when unauthorized handling repeats while anonymous", async () => {
    const view = await renderProfile(false)
    const request = deferred<string>()
    view.releases.push(() => request.resolve("updated"))
    let started = false
    const mutation = view.queryClient.getMutationCache().build(view.queryClient, {
      mutationFn: () => {
        started = true
        return request.promise
      },
      onSuccess: (value) => view.queryClient.setQueryData(["settings", "saved"], value),
    })
    const pending = view.track(mutation.execute(undefined))
    await waitFor(() => expect(started).toBe(true), { timeout: 2_000 })

    await withCacheClearDiagnostic(() => act(() => view.track(view.result.current.refresh())))
    await act(async () => {
      request.resolve("updated")
      await pending
    })

    expect(view.result.current.user).toBeNull()
    expect(view.queryClient.getQueryData(["settings", "saved"])).toBeUndefined()
  })

  it("allows new mutation work after an authoritative profile accepts the browser generation", async () => {
    const view = await renderProfile()
    changeBrowserGeneration()

    await withCacheClearDiagnostic(() =>
      act(() => view.result.current.setUser({ ...testUser, full_name: "Confirmed profile" }))
    )
    await act(async () => {
      await view.track(runCachedMutation(view.queryClient))
    })

    expect(view.result.current.user?.full_name).toBe("Confirmed profile")
    expect(view.queryClient.getQueryData(["settings", "saved"])).toBe("updated")
  })

  it("does not enable mutation work by clearing a profile from an unaccepted browser generation", async () => {
    const view = await renderProfile()
    changeBrowserGeneration()

    await withCacheClearDiagnostic(() => act(() => view.result.current.setUser(null)))
    const outcome = await view.track(
      runCachedMutation(view.queryClient).catch((error: unknown) => {
        if (!isCancelledError(error)) throw error
        return error
      })
    )

    expect(view.result.current.user).toBeNull()
    expect(isCancelledError(outcome)).toBe(true)
    expect(view.queryClient.getQueryData(["settings", "saved"])).toBeUndefined()
    // This test intentionally leaves its browser generation unaccepted. The
    // real client's cancellation fence must reject in that exact state too.
    await view.dispose(async () => {
      await expect(view.queryClient.cancelQueries()).rejects.toBeInstanceOf(CancelledError)
    })
  })
})

describe("profile fixture lifecycle", () => {
  it("drains released work and retains every cleanup failure", async () => {
    const unmountError = new Error("unmount failed")
    const releaseError = new Error("release failed")
    const cancelError = new Error("cancellation failed")
    const operationError = new Error("owned continuation failed")
    const clearError = new Error("clear failed")
    const request = deferred<string>()
    const { operations, track } = createOperationTracker()
    const completed = track(
      request.promise.then((value) => {
        track(Promise.reject(operationError))
        return value
      })
    )
    let cleared = false
    const disposal = disposeOwnedWork({
      unmount: () => {
        throw unmountError
      },
      releases: [
        () => {
          throw releaseError
        },
        () => request.resolve("released"),
      ],
      operations,
      cancel: async () => {
        throw cancelError
      },
      clear: () => {
        cleared = true
        throw clearError
      },
    })

    await expect(disposal).rejects.toMatchObject({
      errors: [unmountError, releaseError, cancelError, operationError, clearError],
    })
    await expect(completed).resolves.toBe("released")
    expect(cleared).toBe(true)
  })
})
