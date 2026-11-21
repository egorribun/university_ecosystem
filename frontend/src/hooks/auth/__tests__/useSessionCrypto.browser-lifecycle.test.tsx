import { Activity, type PropsWithChildren } from "react"
import { act, cleanup, renderHook, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, onTestFinished, vi } from "vitest"

import api from "@/api/client"
import { SERVICE_WORKER_MESSAGE_TYPES as MESSAGES } from "@/constants/serviceWorkerMessages"
import { useSessionCrypto } from "@/hooks/auth/useSessionCrypto"
import {
  acceptBrowserSessionGeneration,
  getBrowserSessionGeneration,
  invalidateSessionEpoch,
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
const controller = () => ({
  postMessage: vi.fn((_message: unknown, ports?: MessagePort[]) => {
    ports?.[0]?.postMessage(true)
  }),
})
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
  it("waits for an already-running same-session key fetch before answering readiness", async () => {
    const previous = renderHook(useSessionCrypto)
    await act(() => owned(previous.result.current.updateSessionSigningKey("fetched-key")))
    const generation = getBrowserSessionGeneration()
    previous.unmount()
    const response = deferred({ data: { signing_key: "fetched-key" } })
    vi.mocked(api.get).mockReturnValue(response.promise)
    const page = renderHook(useSessionCrypto)
    let pending!: Promise<string | null>
    act(() => {
      pending = owned(page.result.current.ensureSessionSigningKey())
    })
    const reply = requestScope(container.controller!)
    expect(reply).not.toHaveBeenCalled()
    await act(async () => {
      response.resolve({ data: { signing_key: "fetched-key" } })
      expect(await pending).toBe("fetched-key")
    })
    expect(getBrowserSessionGeneration()).toBe(generation)
    await waitFor(() =>
      expect(reply).toHaveBeenCalledExactlyOnceWith({
        sessionHash: "hash-fetched-key",
        sessionScope: `hash-fetched-key:${generation}`,
      })
    )
  })

  it("waits when the server key is already installed but hashing is still running", async () => {
    const previous = renderHook(useSessionCrypto)
    await act(() => owned(previous.result.current.updateSessionSigningKey("fetched-key")))
    const generation = getBrowserSessionGeneration()
    previous.unmount()
    const hashing = deferred("hash-fetched-key")
    vi.mocked(cryptoWorker.pbkdf2).mockReturnValue(hashing.promise)
    const page = renderHook(useSessionCrypto)
    let pending!: Promise<string | null>
    await act(async () => {
      pending = owned(page.result.current.ensureSessionSigningKey())
      await Promise.resolve()
    })
    expect(page.result.current.sessionSigningKeyRef.current).toBe("fetched-key")
    const reply = requestScope(container.controller!)
    expect(reply).not.toHaveBeenCalled()
    await act(async () => {
      hashing.resolve("hash-fetched-key")
      expect(await pending).toBe("fetched-key")
    })
    await waitFor(() =>
      expect(reply).toHaveBeenCalledExactlyOnceWith({
        sessionHash: "hash-fetched-key",
        sessionScope: `hash-fetched-key:${generation}`,
      })
    )
  })

  it("reports not ready when logout overtakes the in-flight hash", async () => {
    const previous = renderHook(useSessionCrypto)
    await act(() => owned(previous.result.current.updateSessionSigningKey("fetched-key")))
    previous.unmount()
    const hashing = deferred("hash-fetched-key")
    vi.mocked(cryptoWorker.pbkdf2).mockReturnValue(hashing.promise)
    const page = renderHook(useSessionCrypto)
    let pending!: Promise<string | null>
    await act(async () => {
      pending = owned(page.result.current.ensureSessionSigningKey())
      await Promise.resolve()
    })
    const reply = requestScope(container.controller!)
    expect(reply).not.toHaveBeenCalled()
    await act(() => owned(page.result.current.updateSessionSigningKey(null)))
    await act(async () => {
      hashing.resolve("hash-fetched-key")
      expect(await pending).toBeNull()
    })
    expect(reply).toHaveBeenCalledExactlyOnceWith({ sessionHash: null, sessionScope: null })
  })

  it("shares the acknowledgement with another query while SET is awaiting delivery", async () => {
    const previous = renderHook(useSessionCrypto)
    await act(() => owned(previous.result.current.updateSessionSigningKey("fetched-key")))
    previous.unmount()
    let ackPort: MessagePort | undefined
    container.controller!.postMessage.mockImplementation((_message, ports) => {
      if (ports) ackPort = ports[0]
    })
    const response = deferred({ data: { signing_key: "fetched-key" } })
    vi.mocked(api.get).mockReturnValue(response.promise)
    const page = renderHook(useSessionCrypto)
    let pending!: Promise<string | null>
    act(() => {
      pending = owned(page.result.current.ensureSessionSigningKey())
    })
    const first = requestScope(container.controller!)
    await act(async () => {
      response.resolve({ data: { signing_key: "fetched-key" } })
      await pending
    })
    const second = requestScope(container.controller!)
    expect(first).not.toHaveBeenCalled()
    expect(second).not.toHaveBeenCalled()
    await act(async () => {
      ackPort!.postMessage(true)
    })
    const expected = {
      sessionHash: "hash-fetched-key",
      sessionScope: `hash-fetched-key:${getBrowserSessionGeneration()}`,
    }
    await waitFor(() => {
      expect(first).toHaveBeenCalledExactlyOnceWith(expected)
      expect(second).toHaveBeenCalledExactlyOnceWith(expected)
    })
  })

  it("does not transfer an acknowledgement port without a waiting readiness query", async () => {
    const previous = renderHook(useSessionCrypto)
    await act(() => owned(previous.result.current.updateSessionSigningKey("fetched-key")))
    previous.unmount()
    const page = renderHook(useSessionCrypto)
    container.controller!.postMessage.mockClear()
    await act(() => owned(page.result.current.ensureSessionSigningKey()))
    expect(container.controller!.postMessage.mock.calls.map((call) => call.length)).toEqual([1, 1])
  })

  it.each([false, "true", null])(
    "does not authorize readiness on malformed acknowledgement %s",
    async (ack) => {
      const previous = renderHook(useSessionCrypto)
      await act(() => owned(previous.result.current.updateSessionSigningKey("fetched-key")))
      previous.unmount()
      container.controller!.postMessage.mockImplementation((_message, ports) =>
        ports?.[0]?.postMessage(ack)
      )
      const response = deferred({ data: { signing_key: "fetched-key" } })
      vi.mocked(api.get).mockReturnValue(response.promise)
      const page = renderHook(useSessionCrypto)
      let pending!: Promise<string | null>
      act(() => {
        pending = owned(page.result.current.ensureSessionSigningKey())
      })
      const reply = requestScope(container.controller!)
      await act(async () => {
        response.resolve({ data: { signing_key: "fetched-key" } })
        await pending
      })
      await waitFor(() =>
        expect(reply).toHaveBeenCalledExactlyOnceWith({ sessionHash: null, sessionScope: null })
      )
    }
  )

  it("falls back to not ready after the worker deadline when an older worker never acknowledges", async () => {
    vi.useFakeTimers()
    try {
      const previous = renderHook(useSessionCrypto)
      await act(() => owned(previous.result.current.updateSessionSigningKey("fetched-key")))
      previous.unmount()
      container.controller!.postMessage.mockImplementation(() => undefined)
      const response = deferred({ data: { signing_key: "fetched-key" } })
      vi.mocked(api.get).mockReturnValue(response.promise)
      const page = renderHook(useSessionCrypto)
      let pending!: Promise<string | null>
      act(() => {
        pending = owned(page.result.current.ensureSessionSigningKey())
      })
      const reply = requestScope(container.controller!)
      await act(async () => {
        response.resolve({ data: { signing_key: "fetched-key" } })
        await pending
      })
      expect(reply).not.toHaveBeenCalled()
      await act(() => vi.advanceTimersByTimeAsync(1000))
      expect(reply).toHaveBeenCalledExactlyOnceWith({ sessionHash: null, sessionScope: null })
    } finally {
      vi.useRealTimers()
    }
  })

  it.each(["logout", "new generation", "controller change", "unmount"])(
    "rejects a delayed acknowledgement after %s",
    async (transition) => {
      const previous = renderHook(useSessionCrypto)
      await act(() => owned(previous.result.current.updateSessionSigningKey("fetched-key")))
      previous.unmount()
      let ackPort: MessagePort | undefined
      container.controller!.postMessage.mockImplementation((_message, ports) => {
        if (ports) ackPort = ports[0]
      })
      const response = deferred({ data: { signing_key: "fetched-key" } })
      vi.mocked(api.get).mockReturnValue(response.promise)
      const page = renderHook(useSessionCrypto)
      let pending!: Promise<string | null>
      act(() => {
        pending = owned(page.result.current.ensureSessionSigningKey())
      })
      const reply = requestScope(container.controller!)
      await act(async () => {
        response.resolve({ data: { signing_key: "fetched-key" } })
        await pending
      })
      expect(ackPort).toBeDefined()
      expect(reply).not.toHaveBeenCalled()
      if (transition === "logout")
        await act(() => owned(page.result.current.updateSessionSigningKey(null)))
      if (transition === "new generation") act(rotateBrowserSession)
      if (transition === "controller change") container.controller = controller()
      if (transition === "unmount") page.unmount()
      await act(async () => {
        ackPort!.postMessage(true)
      })
      await waitFor(() =>
        expect(reply).toHaveBeenCalledExactlyOnceWith({ sessionHash: null, sessionScope: null })
      )
    }
  )

  it("ignores a closed worker reply port without an unhandled rejection", async () => {
    const previous = renderHook(useSessionCrypto)
    await act(() => owned(previous.result.current.updateSessionSigningKey("fetched-key")))
    previous.unmount()
    const response = deferred({ data: { signing_key: "fetched-key" } })
    vi.mocked(api.get).mockReturnValue(response.promise)
    const page = renderHook(useSessionCrypto)
    let pending!: Promise<string | null>
    act(() => {
      pending = owned(page.result.current.ensureSessionSigningKey())
    })
    const reply = vi.fn(() => {
      throw new DOMException("closed", "InvalidStateError")
    })
    requestScope(container.controller!, { type: MESSAGES.REQUEST_API_SESSION_CACHE_KEY }, [
      { postMessage: reply },
    ])
    await act(async () => {
      response.resolve({ data: { signing_key: "fetched-key" } })
      await pending
    })
    await waitFor(() => expect(reply).toHaveBeenCalledOnce())
  })

  it("reports not ready if the acknowledgement channel cannot be created", async () => {
    const previous = renderHook(useSessionCrypto)
    await act(() => owned(previous.result.current.updateSessionSigningKey("fetched-key")))
    previous.unmount()
    const response = deferred({ data: { signing_key: "fetched-key" } })
    vi.mocked(api.get).mockReturnValue(response.promise)
    const page = renderHook(useSessionCrypto)
    let pending!: Promise<string | null>
    act(() => {
      pending = owned(page.result.current.ensureSessionSigningKey())
    })
    vi.stubGlobal(
      "MessageChannel",
      class {
        constructor() {
          throw new Error("unavailable")
        }
      }
    )
    try {
      expect(requestScope(container.controller!)).toHaveBeenCalledExactlyOnceWith({
        sessionHash: null,
        sessionScope: null,
      })
    } finally {
      vi.unstubAllGlobals()
    }
    await act(async () => {
      response.resolve({ data: { signing_key: "fetched-key" } })
      await pending
    })
  })

  it("settles readiness even if closing transferred ports throws", async () => {
    const previous = renderHook(useSessionCrypto)
    await act(() => owned(previous.result.current.updateSessionSigningKey("fetched-key")))
    previous.unmount()
    const originalClose = MessagePort.prototype.close
    vi.spyOn(MessagePort.prototype, "close").mockImplementation(function (this: MessagePort) {
      originalClose.call(this)
      throw new DOMException("detached", "InvalidStateError")
    })
    const response = deferred({ data: { signing_key: "fetched-key" } })
    vi.mocked(api.get).mockReturnValue(response.promise)
    const page = renderHook(useSessionCrypto)
    let pending!: Promise<string | null>
    act(() => {
      pending = owned(page.result.current.ensureSessionSigningKey())
    })
    const reply = requestScope(container.controller!)
    await act(async () => {
      response.resolve({ data: { signing_key: "fetched-key" } })
      await pending
    })
    await waitFor(() =>
      expect(reply).toHaveBeenCalledExactlyOnceWith({
        sessionHash: "hash-fetched-key",
        sessionScope: `hash-fetched-key:${getBrowserSessionGeneration()}`,
      })
    )
  })

  it("reports not ready if posting the acknowledgement port fails", async () => {
    vi.stubEnv("DEV", false)
    try {
      const previous = renderHook(useSessionCrypto)
      await act(() => owned(previous.result.current.updateSessionSigningKey("fetched-key")))
      previous.unmount()
      container.controller!.postMessage.mockImplementation((_message, ports) => {
        if (ports) throw new DOMException("closed", "InvalidStateError")
      })
      const response = deferred({ data: { signing_key: "fetched-key" } })
      vi.mocked(api.get).mockReturnValue(response.promise)
      const page = renderHook(useSessionCrypto)
      let pending!: Promise<string | null>
      act(() => {
        pending = owned(page.result.current.ensureSessionSigningKey())
      })
      const reply = requestScope(container.controller!)
      await act(async () => {
        response.resolve({ data: { signing_key: "fetched-key" } })
        await pending
      })
      await waitFor(() =>
        expect(reply).toHaveBeenCalledExactlyOnceWith({ sessionHash: null, sessionScope: null })
      )
    } finally {
      vi.unstubAllEnvs()
    }
  })

  it("immediately reports not ready when no key initialization is running", () => {
    renderHook(useSessionCrypto)
    expect(requestScope(container.controller!)).toHaveBeenCalledExactlyOnceWith({
      sessionHash: null,
      sessionScope: null,
    })
  })

  it("does not wait when the browser generation is unknown", async () => {
    const response = deferred({ data: { signing_key: "fetched-key" } })
    vi.mocked(api.get).mockReturnValue(response.promise)
    const page = renderHook(useSessionCrypto)
    let pending!: Promise<string | null>
    act(() => {
      pending = owned(page.result.current.ensureSessionSigningKey())
    })
    expect(requestScope(container.controller!)).toHaveBeenCalledExactlyOnceWith({
      sessionHash: null,
      sessionScope: null,
    })
    await act(async () => {
      response.resolve({ data: { signing_key: "fetched-key" } })
      await pending
    })
  })

  it("does not wait when the browser binding was already replaced", async () => {
    const previous = renderHook(useSessionCrypto)
    await act(() => owned(previous.result.current.updateSessionSigningKey("fetched-key")))
    previous.unmount()
    localStorage.setItem(
      "ecosystem.session.generation.v1",
      JSON.stringify({ nonce: "foreign", hash: "foreign" })
    )
    const response = deferred({ data: { signing_key: "fetched-key" } })
    vi.mocked(api.get).mockReturnValue(response.promise)
    const page = renderHook(useSessionCrypto)
    let pending!: Promise<string | null>
    act(() => {
      pending = owned(page.result.current.ensureSessionSigningKey())
    })
    expect(requestScope(container.controller!)).toHaveBeenCalledExactlyOnceWith({
      sessionHash: null,
      sessionScope: null,
    })
    await act(async () => {
      response.resolve({ data: { signing_key: "fetched-key" } })
      await pending
    })
  })

  it("does not adopt a different server key into a prior generation", async () => {
    const previous = renderHook(useSessionCrypto)
    await act(() => owned(previous.result.current.updateSessionSigningKey("fetched-key")))
    previous.unmount()
    const response = deferred({ data: { signing_key: "another-key" } })
    vi.mocked(api.get).mockReturnValue(response.promise)
    const page = renderHook(useSessionCrypto)
    let pending!: Promise<string | null>
    act(() => {
      pending = owned(page.result.current.ensureSessionSigningKey())
    })
    const reply = requestScope(container.controller!)
    expect(reply).not.toHaveBeenCalled()
    await act(async () => {
      response.resolve({ data: { signing_key: "another-key" } })
      await pending
    })
    expect(reply).toHaveBeenCalledExactlyOnceWith({ sessionHash: null, sessionScope: null })
  })

  it("reports not ready if the in-flight initialization itself rejects", async () => {
    const previous = renderHook(useSessionCrypto)
    await act(() => owned(previous.result.current.updateSessionSigningKey("fetched-key")))
    previous.unmount()
    vi.mocked(api.get).mockRejectedValue(new Error("key fetch failed"))
    const page = renderHook(useSessionCrypto)
    await act(async () => {
      expect(await page.result.current.ensureSessionSigningKey()).toBeNull()
      expect(await page.result.current.ensureSessionSigningKey()).toBeNull()
    })
    const response = deferred({ data: { signing_key: "unused" } })
    vi.mocked(api.get).mockImplementationOnce(() =>
      response.promise.then(() => {
        throw new Error("key fetch failed")
      })
    )
    vi.spyOn(window, "dispatchEvent").mockImplementationOnce(() => {
      throw new Error("notification failed")
    })
    let pending!: Promise<string | null>
    act(() => {
      pending = owned(page.result.current.ensureSessionSigningKey().catch(() => null))
    })
    let deliverAck!: () => void
    vi.stubGlobal(
      "MessageChannel",
      class {
        port1: { onmessage: ((event: { data: unknown }) => void) | null; close: () => void } = {
          onmessage: null,
          close: () => undefined,
        }
        port2 = { close: () => undefined }
        constructor() {
          deliverAck = () => this.port1.onmessage?.({ data: true })
        }
      }
    )
    try {
      const reply = requestScope(container.controller!)
      expect(reply).not.toHaveBeenCalled()
      await act(async () => {
        deliverAck()
        await Promise.resolve()
        response.resolve({ data: { signing_key: "unused" } })
        expect(await pending).toBeNull()
      })
      expect(reply).toHaveBeenCalledExactlyOnceWith({ sessionHash: null, sessionScope: null })
    } finally {
      vi.unstubAllGlobals()
    }
  })

  it("reports not ready when the pending server-key fetch fails", async () => {
    const previous = renderHook(useSessionCrypto)
    await act(() => owned(previous.result.current.updateSessionSigningKey("fetched-key")))
    previous.unmount()
    vi.mocked(api.get).mockRejectedValueOnce(new Error("key fetch failed"))
    const page = renderHook(useSessionCrypto)
    let pending!: Promise<string | null>
    act(() => {
      pending = owned(page.result.current.ensureSessionSigningKey())
    })
    const reply = requestScope(container.controller!)
    expect(reply).not.toHaveBeenCalled()
    await act(async () => {
      expect(await pending).toBeNull()
    })
    expect(reply).toHaveBeenCalledExactlyOnceWith({ sessionHash: null, sessionScope: null })
  })

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
  it.each([
    "logout",
    "new generation",
    "epoch change",
    "key replacement",
    "controller change",
    "unmount",
    "failed rotation",
  ])("reports not ready if %s overtakes an in-flight key fetch", async (transition) => {
    const previous = renderHook(useSessionCrypto)
    await act(() => owned(previous.result.current.updateSessionSigningKey("fetched-key")))
    previous.unmount()
    const response = deferred({ data: { signing_key: "fetched-key" } })
    vi.mocked(api.get).mockReturnValue(response.promise)
    const page = renderHook(useSessionCrypto)
    let pending!: Promise<string | null>
    act(() => {
      pending = owned(page.result.current.ensureSessionSigningKey())
    })
    const reply = requestScope(container.controller!)
    expect(reply).not.toHaveBeenCalled()
    if (transition === "logout")
      await act(() => owned(page.result.current.updateSessionSigningKey(null)))
    if (transition === "new generation") act(rotateBrowserSession)
    if (transition === "failed rotation") {
      const write = vi.spyOn(Storage.prototype, "setItem").mockImplementationOnce(() => {
        throw new DOMException("storage write denied", "SecurityError")
      })
      act(rotateBrowserSession)
      write.mockRestore()
    }
    if (transition === "epoch change") act(invalidateSessionEpoch)
    if (transition === "key replacement")
      await act(() => owned(page.result.current.updateSessionSigningKey("other")))
    if (transition === "controller change") container.controller = controller()
    if (transition === "unmount") page.unmount()
    await act(async () => {
      response.resolve({ data: { signing_key: "fetched-key" } })
      await pending
    })
    expect(reply).toHaveBeenCalledExactlyOnceWith({ sessionHash: null, sessionScope: null })
  })
})
