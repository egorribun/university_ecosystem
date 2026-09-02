import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

type ServiceWorkerListener = (event: MessageEvent<unknown>) => void

type FakeServiceWorker = ServiceWorkerContainer & {
  emit: (data: unknown) => void
  listeners: Set<ServiceWorkerListener>
  addEventListener: ReturnType<typeof vi.fn>
  removeEventListener: ReturnType<typeof vi.fn>
}

const createServiceWorker = (): FakeServiceWorker => {
  const listeners = new Set<ServiceWorkerListener>()
  const addEventListener = vi.fn((type: string, listener: EventListenerOrEventListenerObject) => {
    if (type === "message" && typeof listener === "function") {
      listeners.add(listener as ServiceWorkerListener)
    }
  })
  const removeEventListener = vi.fn(
    (type: string, listener: EventListenerOrEventListenerObject) => {
      if (type === "message" && typeof listener === "function") {
        listeners.delete(listener as ServiceWorkerListener)
      }
    }
  )
  const worker = {
    addEventListener,
    removeEventListener,
    emit(data: unknown) {
      const event = { data } as MessageEvent<unknown>
      for (const listener of [...listeners]) listener(event)
    },
    listeners,
  } as unknown as FakeServiceWorker
  return worker
}

describe("push message bus", () => {
  let bus: typeof import("../pushMessageBus")

  beforeEach(async () => {
    vi.resetModules()
    bus = await import("../pushMessageBus")
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it("is a no-op when navigator or service-worker messaging is unavailable", () => {
    vi.stubGlobal("navigator", undefined)
    expect(() => bus.ensurePushMessageBridge()).not.toThrow()
    const unsubscribe = bus.subscribeToPushMessages(vi.fn())
    expect(() => unsubscribe()).not.toThrow()

    const worker = { serviceWorker: {} }
    vi.stubGlobal("navigator", worker)
    expect(() => bus.ensurePushMessageBridge()).not.toThrow()
    expect(() => bus.subscribeToPushMessages(vi.fn())).not.toThrow()
  })

  it("buffers relevant messages, bounds the buffer, and replays them once", () => {
    const worker = createServiceWorker()
    vi.stubGlobal("navigator", { serviceWorker: worker })
    bus.ensurePushMessageBridge()
    bus.ensurePushMessageBridge()
    expect(worker.addEventListener).toHaveBeenCalledOnce()

    worker.emit(null)
    worker.emit({ type: "OTHER" })
    worker.emit({ type: "PUSH_NOTIFICATION", id: 0 })
    for (let index = 1; index <= 20; index += 1) {
      worker.emit({ type: index % 2 ? "SYNC_COMPLETE" : "PUSH_NOTIFICATION", id: index })
    }

    const subscriber = vi.fn()
    const unsubscribe = bus.subscribeToPushMessages(subscriber)
    expect(subscriber).toHaveBeenCalledTimes(20)
    expect(subscriber.mock.calls[0]?.[0]).toEqual(
      expect.objectContaining({ data: { type: "SYNC_COMPLETE", id: 1 } })
    )
    expect(subscriber.mock.calls.at(-1)?.[0]).toEqual(
      expect.objectContaining({ data: { type: "PUSH_NOTIFICATION", id: 20 } })
    )

    worker.emit({ type: "PUSH_NOTIFICATION", id: 21 })
    expect(subscriber).toHaveBeenCalledTimes(21)
    unsubscribe()
    worker.emit({ type: "PUSH_NOTIFICATION", id: 22 })

    const secondSubscriber = vi.fn()
    const unsubscribeSecond = bus.subscribeToPushMessages(secondSubscriber)
    expect(secondSubscriber).toHaveBeenCalledTimes(1)
    expect(secondSubscriber.mock.calls[0]?.[0]).toEqual(
      expect.objectContaining({ data: { type: "PUSH_NOTIFICATION", id: 22 } })
    )
    unsubscribeSecond()
  })

  it("replaces a changed service-worker container and drops stale messages", () => {
    const firstWorker = createServiceWorker()
    const secondWorker = createServiceWorker()
    vi.stubGlobal("navigator", { serviceWorker: firstWorker })
    bus.ensurePushMessageBridge()
    firstWorker.emit({ type: "PUSH_NOTIFICATION", id: "stale" })

    vi.stubGlobal("navigator", { serviceWorker: secondWorker })
    bus.ensurePushMessageBridge()
    expect(firstWorker.removeEventListener).toHaveBeenCalledOnce()
    expect(secondWorker.addEventListener).toHaveBeenCalledOnce()

    const subscriber = vi.fn()
    const unsubscribe = bus.subscribeToPushMessages(subscriber)
    expect(subscriber).not.toHaveBeenCalled()
    secondWorker.emit({ type: "PUSH_NOTIFICATION", id: "fresh" })
    expect(subscriber).toHaveBeenCalledOnce()
    unsubscribe()

    vi.stubGlobal("navigator", { serviceWorker: undefined })
    bus.ensurePushMessageBridge()
    expect(secondWorker.removeEventListener).toHaveBeenCalledOnce()
  })

  it("allows subscribing before the bridge is explicitly started", () => {
    const worker = createServiceWorker()
    vi.stubGlobal("navigator", { serviceWorker: worker })
    const subscriber = vi.fn()
    const unsubscribe = bus.subscribeToPushMessages(subscriber)
    expect(worker.addEventListener).toHaveBeenCalledOnce()
    worker.emit({ type: "PUSH_NOTIFICATION", id: "direct" })
    expect(subscriber).toHaveBeenCalledOnce()
    unsubscribe()
  })
})
