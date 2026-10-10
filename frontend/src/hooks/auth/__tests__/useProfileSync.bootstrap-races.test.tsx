import { useCallback, type PropsWithChildren } from "react"
import { act, cleanup, renderHook, waitFor } from "@testing-library/react"
import { QueryClientProvider } from "@tanstack/react-query"
import { HttpResponse, http } from "msw"
import { afterEach, beforeEach, describe, expect, it, onTestFinished, vi } from "vitest"

import api from "@/api/client"
import { createQueryClient } from "@/app/queryClient"
import { currentUserQueryKey, useProfileSync } from "@/hooks/auth/useProfileSync"
import { useSessionCrypto } from "@/hooks/auth/useSessionCrypto"
import { acceptBrowserSessionGeneration } from "@/stores/sessionEpoch"
import { useAuthStore } from "@/stores/useAuthStore"
import { testUser } from "@/tests/mocks/handlers"
import { server } from "@/tests/mocks/server"
import { cryptoWorker } from "@/utils/cryptoWorker"

const olderProfile = { ...testUser, full_name: "Older cached profile" }
const newerProfile = {
  ...testUser,
  id: "550e8400-e29b-41d4-a716-446655440001",
  full_name: "Newer identity",
}
const snapshot = (storage: Storage): Record<string, string> => {
  const entries: Array<[string, string]> = []
  for (let index = 0; index < storage.length; index += 1) {
    const key = storage.key(index)
    if (key === null) continue
    const value = storage.getItem(key)
    if (value !== null) entries.push([key, value])
  }
  return Object.fromEntries(entries)
}
const restore = (storage: Storage, entries: Record<string, string>) => {
  storage.clear()
  for (const [key, value] of Object.entries(entries)) storage.setItem(key, value)
}
const gate = () => {
  let release!: () => void
  const promise = new Promise<void>((resolve) => {
    release = resolve
  })
  return { promise, release }
}

let savedAuth: ReturnType<typeof useAuthStore.getState>
let savedLocal: Record<string, string>
let savedSession: Record<string, string>
let originalPbkdf2: typeof cryptoWorker.pbkdf2 | undefined
let disposers: Array<() => Promise<void>>

beforeEach(() => {
  // Capture both stores before any reset can trigger real identity invalidation.
  savedAuth = useAuthStore.getState()
  savedLocal = snapshot(localStorage)
  savedSession = snapshot(sessionStorage)
  originalPbkdf2 = vi.mocked(cryptoWorker.pbkdf2).getMockImplementation()
  disposers = []
  useAuthStore.setState(useAuthStore.getInitialState(), true)
  localStorage.clear()
  sessionStorage.clear()
  acceptBrowserSessionGeneration()
  vi.mocked(cryptoWorker.pbkdf2).mockImplementation(async ({ value }) => `hash-${value}`)
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
    attempt(() => vi.mocked(cryptoWorker.pbkdf2).mockImplementation(originalPbkdf2!))
    attempt(() => useAuthStore.setState(savedAuth, true))
    attempt(() => restore(localStorage, savedLocal))
    attempt(() => restore(sessionStorage, savedSession))
    attempt(acceptBrowserSessionGeneration)
  }
  if (failures.length) throw new AggregateError(failures, "Profile test cleanup failed")
})

const renderBootstrap = ({ holdRequest = false, holdResult = false } = {}) => {
  const requestGate = gate()
  const resultGate = gate()
  if (!holdRequest) requestGate.release()
  if (!holdResult) resultGate.release()
  let started = false
  let acquired = false
  const operations: Promise<unknown>[] = []
  const track = <T,>(promise: Promise<T>) => {
    operations.push(promise)
    return promise
  }
  server.use(
    http.get("*/auth/session/signing-key", async () => {
      started = true
      await requestGate.promise
      return HttpResponse.json({ signing_key: "fetched-old-key" })
    })
  )
  const getSpy = vi.spyOn(api, "get")
  const queryClient = createQueryClient()
  queryClient.setQueryData(currentUserQueryKey, olderProfile)
  const wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )
  const view = renderHook(
    () => {
      const crypto = useSessionCrypto()
      const ensure = crypto.ensureSessionSigningKey
      const acquireHeldKey = useCallback(
        () =>
          track(
            (async () => {
              const key = await ensure()
              acquired = true
              await resultGate.promise
              return key
            })()
          ),
        [ensure]
      )
      const profile = useProfileSync(
        crypto.updateSessionSigningKey,
        crypto.sessionSigningKeyRef,
        crypto.sessionSigningKeyPromiseRef,
        acquireHeldKey,
        undefined,
        crypto.isCurrentSigningSession
      )
      return { crypto, profile }
    },
    { wrapper }
  )
  let disposal: Promise<void> | undefined
  const dispose = () => {
    disposal ??= (async () => {
      const failures: unknown[] = []
      try {
        view.unmount()
      } catch (error) {
        failures.push(error)
      } finally {
        requestGate.release()
        resultGate.release()
        try {
          const outcomes = await Promise.allSettled(operations)
          for (const outcome of outcomes) {
            if (outcome.status === "rejected") failures.push(outcome.reason)
          }
        } finally {
          try {
            queryClient.clear()
          } catch (error) {
            failures.push(error)
          }
        }
      }
      if (failures.length) throw new AggregateError(failures, "Profile bootstrap cleanup failed")
    })()
    return disposal
  }

  disposers.push(dispose)
  onTestFinished(dispose)
  return {
    ...view,
    queryClient,
    getSpy,
    track,
    started: () => started,
    acquired: () => acquired,
    releaseRequest: requestGate.release,
    releaseResult: resultGate.release,
  }
}

describe("profile bootstrap ownership races", () => {
  it("restores seeded storage entries through the actual Storage interface", () => {
    for (const storage of [localStorage, sessionStorage]) {
      storage.setItem("fixture-preserved", "seeded-value")
      storage.setItem("fixture-empty", "")
      const captured = snapshot(storage)
      storage.clear()
      restore(storage, captured)
      expect(storage.getItem("fixture-preserved")).toBe("seeded-value")
      expect(storage.getItem("fixture-empty")).toBe("")
    }
  })

  it("does not request a key after a newer identity overtakes cached query continuation", async () => {
    const view = renderBootstrap()
    act(() => view.result.current.profile.setUser(newerProfile))
    await waitFor(() => expect(view.result.current.profile.loading).toBe(false))
    expect(view.result.current.profile.user?.id).toBe(newerProfile.id)
    expect(view.getSpy).not.toHaveBeenCalled()
    expect(view.queryClient.getQueryData(currentUserQueryKey)).toEqual(newerProfile)
  })

  it("preserves a newer profile committed while the signing request is pending", async () => {
    const view = renderBootstrap({ holdRequest: true })
    await waitFor(() => expect(view.started()).toBe(true))
    act(() => view.result.current.profile.setUser(newerProfile))
    await act(async () => {
      view.releaseRequest()
    })
    await waitFor(() => expect(view.result.current.profile.loading).toBe(false))
    expect(view.result.current.profile.user?.id).toBe(newerProfile.id)
    expect(view.queryClient.getQueryData(currentUserQueryKey)).toEqual(newerProfile)
  })

  it("does not install an older cached profile after a manual key replaces its pending key", async () => {
    const view = renderBootstrap({ holdRequest: true })
    await waitFor(() => expect(view.started()).toBe(true))
    await act(() =>
      view.track(view.result.current.crypto.updateSessionSigningKey("manual-new-key"))
    )
    await act(async () => {
      view.releaseRequest()
    })
    await waitFor(() => expect(view.result.current.profile.loading).toBe(false))
    expect(view.result.current.crypto.sessionSigningKey).toBe("manual-new-key")
    expect(view.result.current.profile.user).toBeNull()
  })

  it("rejects a completed key result replaced before profile bootstrap consumes it", async () => {
    const view = renderBootstrap({ holdResult: true })
    await waitFor(() => expect(view.acquired()).toBe(true))
    expect(view.result.current.crypto.sessionSigningKey).toBe("fetched-old-key")
    await act(() =>
      view.track(view.result.current.crypto.updateSessionSigningKey("manual-new-key"))
    )
    await act(async () => {
      view.releaseResult()
    })
    await waitFor(() => expect(view.result.current.profile.loading).toBe(false))
    expect(view.result.current.crypto.sessionSigningKey).toBe("manual-new-key")
    expect(view.result.current.profile.user).toBeNull()
  })
})
