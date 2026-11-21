import { act, cleanup, renderHook, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import api from "@/api/client"
import { useSessionCrypto } from "@/hooks/auth/useSessionCrypto"
import { SERVICE_WORKER_MESSAGE_TYPES as MESSAGES } from "@/constants/serviceWorkerMessages"
import {
  acceptBrowserSessionGeneration,
  getBrowserSessionGeneration,
  rotateBrowserSession,
} from "@/stores/sessionEpoch"
import { cryptoWorker } from "@/utils/cryptoWorker"

let resolveKey!: (value: { data: { signing_key: string } }) => void
let originalWorker: PropertyDescriptor | undefined
let port: MessagePort | undefined
let listeners: Map<string, (event: MessageEvent) => void>
let controller: { postMessage: ReturnType<typeof vi.fn> }
let container: {
  controller: typeof controller | null
  addEventListener: ReturnType<typeof vi.fn>
  removeEventListener: ReturnType<typeof vi.fn>
}

beforeEach(() => {
  localStorage.clear()
  acceptBrowserSessionGeneration()
  originalWorker = Object.getOwnPropertyDescriptor(navigator, "serviceWorker")
  port = undefined
  controller = {
    postMessage: vi.fn((message: { type: string }, ports?: MessagePort[]) => {
      if (message.type === MESSAGES.SET_API_SESSION_CACHE_KEY) port = ports?.[0]
    }),
  }
  listeners = new Map()
  container = {
    controller,
    addEventListener: vi.fn((type: string, listener: (event: MessageEvent) => void) =>
      listeners.set(type, listener)
    ),
    removeEventListener: vi.fn((type: string) => listeners.delete(type)),
  }
  Object.defineProperty(navigator, "serviceWorker", { configurable: true, value: container })
  vi.spyOn(api, "get").mockResolvedValue({ data: { signing_key: "fetched-key" } })
  vi.spyOn(cryptoWorker, "pbkdf2").mockResolvedValue("hash-fetched-key")
})
afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  vi.useRealTimers()
  if (originalWorker) Object.defineProperty(navigator, "serviceWorker", originalWorker)
  else Reflect.deleteProperty(navigator, "serviceWorker")
  localStorage.clear()
  acceptBrowserSessionGeneration()
})

describe("proactive SET completion for authenticated bootstrap", () => {
  it("waits for the actual SET acknowledgment, including concurrent callers", async () => {
    const page = renderHook(useSessionCrypto)
    let first!: Promise<string | null>
    act(() => {
      first = page.result.current.ensureSessionSigningKey()
    })
    await waitFor(() => expect(port).toBeDefined(), { timeout: 1000 })
    expect(getBrowserSessionGeneration()).not.toBeNull()
    let firstSettled = false
    let secondSettled = false
    void first.then(() => {
      firstSettled = true
    })
    const second = page.result.current.ensureSessionSigningKey()
    void second.then(() => {
      secondSettled = true
    })
    await Promise.resolve()
    expect(firstSettled).toBe(false)
    expect(secondSettled).toBe(false)
    await act(async () => {
      port!.postMessage(true)
      expect(await first).toBe("fetched-key")
      expect(await second).toBe("fetched-key")
    })
    expect(api.get).toHaveBeenCalledOnce()
  })

  it("uses the ordinary SET path when a completion channel cannot be created", async () => {
    vi.stubGlobal(
      "MessageChannel",
      class {
        constructor() {
          throw new Error("unavailable")
        }
      }
    )
    try {
      const page = renderHook(useSessionCrypto)
      await act(async () => {
        expect(await page.result.current.ensureSessionSigningKey()).toBe("fetched-key")
      })
      expect(port).toBeUndefined()
      expect(controller.postMessage.mock.calls.map((call) => call.length)).toEqual([1, 1])
    } finally {
      vi.unstubAllGlobals()
    }
  })

  it("does not wait for an absent controller", async () => {
    container.controller = null
    const page = renderHook(useSessionCrypto)
    await act(async () => {
      expect(await page.result.current.ensureSessionSigningKey()).toBe("fetched-key")
    })
    expect(port).toBeUndefined()
  })

  it("falls back after the existing one-second deadline when an old worker does not acknowledge", async () => {
    vi.useFakeTimers()
    const page = renderHook(useSessionCrypto)
    let pending!: Promise<string | null>
    await act(async () => {
      pending = page.result.current.ensureSessionSigningKey()
      await Promise.resolve()
      await Promise.resolve()
    })
    expect(port).toBeDefined()
    let settled = false
    void pending.then(() => {
      settled = true
    })
    await act(() => vi.advanceTimersByTimeAsync(999))
    expect(settled).toBe(false)
    await act(() => vi.advanceTimersByTimeAsync(1))
    expect(await pending).toBe("fetched-key")
  })

  it("replaces a timed-out readiness reply with a fresh bounded SET acknowledgment", async () => {
    vi.useFakeTimers()
    const response = new Promise<{ data: { signing_key: string } }>((resolve) => {
      resolveKey = resolve
    })
    vi.mocked(api.get).mockReturnValue(response)
    localStorage.setItem(
      "ecosystem.session.generation.v1",
      JSON.stringify({ nonce: "old", hash: "hash-fetched-key" })
    )
    acceptBrowserSessionGeneration()
    const page = renderHook(useSessionCrypto)
    let pending!: Promise<string | null>
    act(() => {
      pending = page.result.current.ensureSessionSigningKey()
    })
    const reply = vi.fn()
    act(() =>
      listeners.get("message")!({
        source: controller,
        data: { type: MESSAGES.REQUEST_API_SESSION_CACHE_KEY },
        ports: [{ postMessage: reply }],
      } as unknown as MessageEvent)
    )
    await act(() => vi.advanceTimersByTimeAsync(1000))
    expect(reply).toHaveBeenCalledExactlyOnceWith({ sessionHash: null, sessionScope: null })
    await act(async () => {
      resolveKey({ data: { signing_key: "fetched-key" } })
      await Promise.resolve()
      await Promise.resolve()
    })
    expect(port).toBeDefined()
    let settled = false
    void pending.then(() => {
      settled = true
    })
    await Promise.resolve()
    expect(settled).toBe(false)
    await act(async () => {
      port!.postMessage(true)
      expect(await pending).toBe("fetched-key")
    })
  })

  it("keeps an earlier readiness wait bounded when a controller sync overtakes the key hash", async () => {
    vi.useFakeTimers()
    localStorage.setItem(
      "ecosystem.session.generation.v1",
      JSON.stringify({ nonce: "old", hash: "hash-fetched-key" })
    )
    acceptBrowserSessionGeneration()
    let finishInitial!: (value: string) => void
    let finishSync!: (value: string) => void
    const initialHash = new Promise<string>((resolve) => {
      finishInitial = resolve
    })
    const syncHash = new Promise<string>((resolve) => {
      finishSync = resolve
    })
    vi.mocked(cryptoWorker.pbkdf2).mockReturnValueOnce(initialHash).mockReturnValueOnce(syncHash)
    const page = renderHook(useSessionCrypto)
    let pending!: Promise<string | null>
    await act(async () => {
      pending = page.result.current.ensureSessionSigningKey()
      await Promise.resolve()
    })
    expect(cryptoWorker.pbkdf2).toHaveBeenCalledTimes(1)
    const firstReply = vi.fn()
    act(() =>
      listeners.get("message")!({
        source: controller,
        data: { type: MESSAGES.REQUEST_API_SESSION_CACHE_KEY },
        ports: [{ postMessage: firstReply }],
      } as unknown as MessageEvent)
    )
    // Two controller changes can be queued before the first event is delivered.
    // The handler sees the restored controller and starts its regular force sync.
    container.controller = { postMessage: vi.fn() }
    container.controller = controller
    act(() => listeners.get("controllerchange")!(new MessageEvent("controllerchange")))
    expect(cryptoWorker.pbkdf2).toHaveBeenCalledTimes(2)
    await act(async () => {
      finishSync("hash-fetched-key")
      await syncHash
    })
    await act(async () => {
      finishInitial("hash-fetched-key")
      expect(await pending).toBe("fetched-key")
    })
    const secondReply = vi.fn()
    act(() =>
      listeners.get("message")!({
        source: controller,
        data: { type: MESSAGES.REQUEST_API_SESSION_CACHE_KEY },
        ports: [{ postMessage: secondReply }],
      } as unknown as MessageEvent)
    )
    expect(firstReply).not.toHaveBeenCalled()
    expect(secondReply).not.toHaveBeenCalled()
    await act(() => vi.advanceTimersByTimeAsync(1000))
    expect(firstReply).toHaveBeenCalledExactlyOnceWith({ sessionHash: null, sessionScope: null })
    expect(secondReply).toHaveBeenCalledExactlyOnceWith({ sessionHash: null, sessionScope: null })
  })

  it("falls back promptly after a controller change without discarding its owned key", async () => {
    const page = renderHook(useSessionCrypto)
    let pending!: Promise<string | null>
    act(() => {
      pending = page.result.current.ensureSessionSigningKey()
    })
    await waitFor(() => expect(port).toBeDefined(), { timeout: 1000 })
    container.controller = null
    await act(async () => {
      listeners.get("controllerchange")!(new MessageEvent("controllerchange"))
      expect(await pending).toBe("fetched-key")
    })
  })

  it("does not return an old key if the browser session rotates while awaiting acknowledgment", async () => {
    localStorage.setItem(
      "ecosystem.session.generation.v1",
      JSON.stringify({ nonce: "old", hash: "hash-fetched-key" })
    )
    acceptBrowserSessionGeneration()
    const page = renderHook(useSessionCrypto)
    let pending!: Promise<string | null>
    act(() => {
      pending = page.result.current.ensureSessionSigningKey()
    })
    await waitFor(() => expect(port).toBeDefined(), { timeout: 1000 })
    act(rotateBrowserSession)
    await act(async () => {
      port!.postMessage(true)
      expect(await pending).toBeNull()
    })
  })
})
