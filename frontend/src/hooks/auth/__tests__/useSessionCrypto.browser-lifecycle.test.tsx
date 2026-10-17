import { Activity, type PropsWithChildren } from "react"
import { act, cleanup, renderHook, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, onTestFinished, vi } from "vitest"

import api from "@/api/client"
import { SERVICE_WORKER_MESSAGE_TYPES as MESSAGES } from "@/constants/serviceWorkerMessages"
import { useSessionCrypto } from "@/hooks/auth/useSessionCrypto"
import {
  acceptBrowserSessionGeneration,
  getBrowserSessionGeneration,
  rotateBrowserSession,
} from "@/stores/sessionEpoch"
import { cryptoWorker } from "@/utils/cryptoWorker"
import { collectWindowErrors } from "@/tests/helpers/windowErrors"

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
const controller = () => ({ postMessage: vi.fn() })
type Controller = ReturnType<typeof controller>
class WorkerContainer extends EventTarget {
  controller: Controller | null = controller()
  ready = Promise.resolve({ active: this.controller } as unknown as ServiceWorkerRegistration)
}

let container: WorkerContainer
let originalWorker: PropertyDescriptor | undefined
let local: Record<string, string>
let session: Record<string, string>
let originalPbkdf2: typeof cryptoWorker.pbkdf2 | undefined
let releases: Array<() => void>
let operations: Promise<unknown>[]
let disposal: Promise<void> | undefined

const owned = <T,>(promise: Promise<T>) => {
  operations.push(promise)
  return promise
}
const deferred = <T,>(fallback: T) => {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((finish) => {
    resolve = finish
  })
  releases.push(() => resolve(fallback))
  return { promise, resolve }
}
const dispose = () => {
  disposal ??= (async () => {
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
    } finally {
      releases.forEach((release) => attempt(release))
      try {
        const outcomes = await Promise.allSettled(operations)
        for (const outcome of outcomes) {
          if (outcome.status === "rejected") failures.push(outcome.reason)
        }
      } finally {
        attempt(() => vi.restoreAllMocks())
        attempt(() => vi.mocked(cryptoWorker.pbkdf2).mockImplementation(originalPbkdf2!))
        attempt(() => {
          if (originalWorker) Object.defineProperty(navigator, "serviceWorker", originalWorker)
          else Reflect.deleteProperty(navigator, "serviceWorker")
        })
        attempt(() => restore(localStorage, local))
        attempt(() => restore(sessionStorage, session))
        attempt(acceptBrowserSessionGeneration)
      }
    }
    if (failures.length) throw new AggregateError(failures, "Session crypto cleanup failed")
  })()
  return disposal
}

const requestScope = (
  target: Controller,
  data: unknown = { type: MESSAGES.REQUEST_API_SESSION_CACHE_KEY },
  ports = [{ postMessage: vi.fn() }]
) => {
  container.dispatchEvent(
    new MessageEvent("message", {
      source: target as unknown as ServiceWorker,
      data,
      ports: ports as unknown as MessagePort[],
    })
  )
  return ports[0]?.postMessage
}
const expectedScope = (key: string) => ({
  type: MESSAGES.SET_API_SESSION_CACHE_KEY,
  sessionHash: `hash-${key}`,
  sessionScope: `hash-${key}:${getBrowserSessionGeneration()}`,
})

beforeEach(() => {
  local = snapshot(localStorage)
  session = snapshot(sessionStorage)
  originalWorker = Object.getOwnPropertyDescriptor(navigator, "serviceWorker")
  originalPbkdf2 = vi.mocked(cryptoWorker.pbkdf2).getMockImplementation()
  localStorage.clear()
  sessionStorage.clear()
  acceptBrowserSessionGeneration()
  releases = []
  operations = []
  disposal = undefined
  container = new WorkerContainer()
  Object.defineProperty(navigator, "serviceWorker", { configurable: true, value: container })
  vi.mocked(cryptoWorker.pbkdf2).mockImplementation(async ({ value }) => `hash-${value}`)
  vi.spyOn(api, "get").mockResolvedValue({ data: { signing_key: "fetched-key" } })
  onTestFinished(dispose)
})
afterEach(dispose)

describe("session crypto browser lifecycle", () => {
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

  it("resends the installed namespace when the controlling worker changes", async () => {
    const view = renderHook(useSessionCrypto)
    await act(() => owned(view.result.current.updateSessionSigningKey("installed")))
    const replacement = controller()
    container.controller = replacement
    await act(async () => {
      container.dispatchEvent(new Event("controllerchange"))
    })
    expect(replacement.postMessage).toHaveBeenCalledExactlyOnceWith(expectedScope("installed"))
  })

  it("resynchronizes the retained key when Activity reconnects effects", async () => {
    let mode: "visible" | "hidden" = "visible"
    const wrapper = ({ children }: PropsWithChildren) => <Activity mode={mode}>{children}</Activity>
    const view = renderHook(useSessionCrypto, { wrapper })
    await act(() => owned(view.result.current.updateSessionSigningKey("retained")))
    mode = "hidden"
    view.rerender()
    const replacement = controller()
    container.controller = replacement
    mode = "visible"
    view.rerender()
    await waitFor(() =>
      expect(replacement.postMessage).toHaveBeenCalledWith(expectedScope("retained"))
    )
    expect(view.result.current.sessionSigningKey).toBe("retained")
  })

  it("removes worker event handlers on unmount", async () => {
    const view = renderHook(useSessionCrypto)
    await act(() => owned(view.result.current.updateSessionSigningKey("removed")))
    const target = container.controller!
    target.postMessage.mockClear()
    view.unmount()
    await act(async () => {
      container.dispatchEvent(new Event("controllerchange"))
    })
    const reply = requestScope(target)
    expect(target.postMessage).not.toHaveBeenCalled()
    expect(reply).not.toHaveBeenCalled()
  })

  it("delivers only the current namespace after delayed worker readiness", async () => {
    const target = container.controller!
    const ready = deferred({ active: target } as unknown as ServiceWorkerRegistration)
    container.controller = null
    container.ready = ready.promise
    const view = renderHook(useSessionCrypto)
    await act(() => owned(view.result.current.updateSessionSigningKey("old")))
    await act(() => owned(view.result.current.updateSessionSigningKey("current")))
    await act(async () => {
      ready.resolve({ active: target } as unknown as ServiceWorkerRegistration)
    })
    expect(target.postMessage.mock.calls).toEqual([
      [{ type: MESSAGES.CLEAR_API_CACHE }],
      [expectedScope("current")],
    ])
  })

  it("does not publish overlapping key derivations after unmount", async () => {
    const old = deferred("hash-old")
    const current = deferred("hash-current")
    vi.mocked(cryptoWorker.pbkdf2).mockImplementation(({ value }) =>
      value === "old" ? old.promise : current.promise
    )
    const view = renderHook(useSessionCrypto)
    let first!: Promise<void>
    let second!: Promise<void>
    act(() => {
      first = owned(view.result.current.updateSessionSigningKey("old"))
      second = owned(view.result.current.updateSessionSigningKey("current"))
    })
    view.unmount()
    container.controller!.postMessage.mockClear()
    await act(async () => {
      old.resolve("hash-old")
      current.resolve("hash-current")
      await Promise.all([first, second])
    })
    expect(container.controller!.postMessage).not.toHaveBeenCalled()
  })

  it("ignores a fetched key after explicit clear and unmount", async () => {
    const fetched = deferred({ data: { signing_key: "late" } })
    vi.mocked(api.get).mockReturnValue(fetched.promise)
    const view = renderHook(useSessionCrypto)
    let ensure!: Promise<string | null>
    act(() => {
      ensure = owned(view.result.current.ensureSessionSigningKey())
    })
    await act(() => owned(view.result.current.updateSessionSigningKey(null)))
    view.unmount()
    container.controller!.postMessage.mockClear()
    await act(async () => {
      fetched.resolve({ data: { signing_key: "late" } })
      expect(await ensure).toBeNull()
    })
    expect(container.controller!.postMessage).not.toHaveBeenCalled()
    expect(view.result.current.sessionSigningKeyRef.current).toBeNull()
  })

  it("does not treat a cache-only namespace as an installed signing session", async () => {
    const view = renderHook(useSessionCrypto)
    await act(() => owned(view.result.current.sendSessionCacheUpdate("cache-only")))
    expect(container.controller!.postMessage).toHaveBeenCalledWith(expectedScope("cache-only"))
    expect(view.result.current.isCurrentSigningSession()).toBe(false)
    expect(requestScope(container.controller!)).toHaveBeenCalledExactlyOnceWith({
      sessionHash: null,
      sessionScope: null,
    })
  })

  it("rejects a forced differing hash when the current namespace is already bound", async () => {
    const view = renderHook(useSessionCrypto)
    await act(() => owned(view.result.current.updateSessionSigningKey("installed")))
    container.controller!.postMessage.mockClear()
    await act(() => owned(view.result.current.sendSessionCacheUpdate("different", { force: true })))
    expect(container.controller!.postMessage).not.toHaveBeenCalled()
    expect(view.result.current.isCurrentSigningSession()).toBe(true)
  })

  it("answers with an empty scope after browser generation rotation", async () => {
    const view = renderHook(useSessionCrypto)
    await act(() => owned(view.result.current.updateSessionSigningKey("old-generation")))
    rotateBrowserSession()
    expect(requestScope(container.controller!)).toHaveBeenCalledExactlyOnceWith({
      sessionHash: null,
      sessionScope: null,
    })
  })

  it.each(["null data", "missing reply port"])(
    "ignores %s and handles the next valid request",
    async (malformed) => {
      const view = renderHook(useSessionCrypto)
      await act(() => owned(view.result.current.updateSessionSigningKey("valid")))
      let reply: ReturnType<typeof requestScope>
      const errors = collectWindowErrors(() => {
        if (malformed === "null data") requestScope(container.controller!, null)
        else
          requestScope(container.controller!, { type: MESSAGES.REQUEST_API_SESSION_CACHE_KEY }, [])
        reply = requestScope(container.controller!)
      })
      expect(errors).toEqual([])
      expect(reply).toHaveBeenCalledExactlyOnceWith({
        sessionHash: "hash-valid",
        sessionScope: `hash-valid:${getBrowserSessionGeneration()}`,
      })
    }
  )
})
