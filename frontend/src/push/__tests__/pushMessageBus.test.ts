import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import type { UserState } from "@/types/Auth"

type ServiceWorkerListener = (event: MessageEvent<unknown>) => void

type FakeServiceWorker = ServiceWorkerContainer & {
  emit: (data: unknown) => void
  listeners: Set<ServiceWorkerListener>
  addEventListener: ReturnType<typeof vi.fn>
  removeEventListener: ReturnType<typeof vi.fn>
}

const TEST_USER_A_ID = "push-bus-user-a"
const TEST_USER_B_ID = "push-bus-user-b"

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
      const stampedData =
        data &&
        typeof data === "object" &&
        (data as { type?: unknown }).type === "PUSH_NOTIFICATION" &&
        !("recipientUserId" in data)
          ? { ...data, recipientUserId: TEST_USER_A_ID }
          : data
      const event = { data: stampedData } as MessageEvent<unknown>
      for (const listener of [...listeners]) listener(event)
    },
    listeners,
  } as unknown as FakeServiceWorker
  return worker
}

describe("push message bus", () => {
  let bus: typeof import("../pushMessageBus")
  let auth: typeof import("@/stores/useAuthStore")

  beforeEach(async () => {
    vi.resetModules()
    auth = await import("@/stores/useAuthStore")
    auth.useAuthStore.setState({
      user: { id: TEST_USER_A_ID } as UserState,
      loading: false,
    })
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

  it("buffers relevant messages, bounds the buffer, and replays them once with their arrival owner", () => {
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
    expect(subscriber.mock.calls[0]?.[1]).toBe(TEST_USER_A_ID)
    expect(subscriber.mock.calls[0]?.[0]).toEqual(
      expect.objectContaining({ data: { type: "SYNC_COMPLETE", id: 1 } })
    )
    expect(subscriber.mock.calls.at(-1)?.[1]).toBe(TEST_USER_A_ID)
    expect(subscriber.mock.calls.at(-1)?.[0]).toEqual(
      expect.objectContaining({
        data: { type: "PUSH_NOTIFICATION", id: 20, recipientUserId: TEST_USER_A_ID },
      })
    )

    worker.emit({ type: "PUSH_NOTIFICATION", id: 21 })
    expect(subscriber).toHaveBeenCalledTimes(21)
    expect(subscriber.mock.calls.at(-1)?.[1]).toBe(TEST_USER_A_ID)
    unsubscribe()
    worker.emit({ type: "PUSH_NOTIFICATION", id: 22 })

    const secondSubscriber = vi.fn()
    const unsubscribeSecond = bus.subscribeToPushMessages(secondSubscriber)
    expect(secondSubscriber).toHaveBeenCalledTimes(1)
    expect(secondSubscriber.mock.calls[0]?.[1]).toBe(TEST_USER_A_ID)
    expect(secondSubscriber.mock.calls[0]?.[0]).toEqual(
      expect.objectContaining({
        data: { type: "PUSH_NOTIFICATION", id: 22, recipientUserId: TEST_USER_A_ID },
      })
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
    expect(subscriber).toHaveBeenCalledWith(
      expect.objectContaining({
        data: { type: "PUSH_NOTIFICATION", id: "fresh", recipientUserId: TEST_USER_A_ID },
      }),
      TEST_USER_A_ID
    )
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
    expect(subscriber).toHaveBeenCalledWith(
      expect.objectContaining({
        data: { type: "PUSH_NOTIFICATION", id: "direct", recipientUserId: TEST_USER_A_ID },
      }),
      TEST_USER_A_ID
    )
    unsubscribe()
  })

  it("drops account A messages received before lazy subscription after switching to account B", () => {
    const worker = createServiceWorker()
    const removeItem = vi.fn()
    vi.stubGlobal("window", {
      localStorage: { removeItem },
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })
    vi.stubGlobal("navigator", { serviceWorker: worker })
    bus.ensurePushMessageBridge()
    worker.emit({ type: "PUSH_NOTIFICATION", id: "private-a" })

    auth.useAuthStore.setState({
      user: { id: TEST_USER_B_ID } as UserState,
      loading: false,
    })
    expect(removeItem).toHaveBeenCalledWith(
      "livePushToastBuffer:" + encodeURIComponent(TEST_USER_A_ID)
    )

    const subscriber = vi.fn()
    const unsubscribe = bus.subscribeToPushMessages(subscriber)
    expect(subscriber).not.toHaveBeenCalled()

    worker.emit({
      type: "PUSH_NOTIFICATION",
      id: "private-b",
      recipientUserId: TEST_USER_B_ID,
    })
    expect(subscriber).toHaveBeenCalledOnce()
    expect(subscriber).toHaveBeenCalledWith(
      expect.objectContaining({
        data: {
          type: "PUSH_NOTIFICATION",
          id: "private-b",
          recipientUserId: TEST_USER_B_ID,
        },
      }),
      TEST_USER_B_ID
    )
    unsubscribe()
  })

  it("keeps a pending account message through a same-user transient loading state", () => {
    const worker = createServiceWorker()
    vi.stubGlobal("navigator", { serviceWorker: worker })
    bus.ensurePushMessageBridge()
    worker.emit({ type: "PUSH_NOTIFICATION", id: "same-account-refresh" })

    auth.useAuthStore.setState({
      user: { id: TEST_USER_A_ID } as UserState,
      loading: true,
    })

    const subscriber = vi.fn()
    const unsubscribe = bus.subscribeToPushMessages(subscriber)
    expect(subscriber).toHaveBeenCalledOnce()
    expect(subscriber).toHaveBeenCalledWith(
      expect.objectContaining({
        data: {
          type: "PUSH_NOTIFICATION",
          id: "same-account-refresh",
          recipientUserId: TEST_USER_A_ID,
        },
      }),
      TEST_USER_A_ID
    )
    unsubscribe()
  })

  it("fails closed for missing or mismatched server recipients and accepts the current account", () => {
    const worker = createServiceWorker()
    vi.stubGlobal("navigator", { serviceWorker: worker })
    bus.ensurePushMessageBridge()

    const subscriber = vi.fn()
    const unsubscribe = bus.subscribeToPushMessages(subscriber)
    worker.emit({ type: "PUSH_NOTIFICATION", id: "account-a", recipientUserId: TEST_USER_A_ID })
    expect(subscriber).toHaveBeenCalledOnce()
    expect(subscriber.mock.calls[0]?.[1]).toBe(TEST_USER_A_ID)

    auth.useAuthStore.setState({ user: { id: TEST_USER_B_ID } as UserState, loading: false })
    worker.emit({ type: "PUSH_NOTIFICATION", id: "missing-recipient", recipientUserId: undefined })
    worker.emit({ type: "PUSH_NOTIFICATION", id: "unknown-recipient", recipientUserId: "unknown" })
    worker.emit({
      type: "PUSH_NOTIFICATION",
      id: "late-account-a",
      recipientUserId: TEST_USER_A_ID,
    })
    expect(subscriber).toHaveBeenCalledOnce()

    worker.emit({ type: "PUSH_NOTIFICATION", id: "account-b", recipientUserId: TEST_USER_B_ID })
    expect(subscriber).toHaveBeenCalledTimes(2)
    expect(subscriber.mock.calls[1]?.[0]).toEqual({
      data: { type: "PUSH_NOTIFICATION", id: "account-b", recipientUserId: TEST_USER_B_ID },
    })
    expect(subscriber.mock.calls[1]?.[1]).toBe(TEST_USER_B_ID)
    unsubscribe()
  })

  it("discards messages while auth is unresolved or holds a render-only identity", async () => {
    vi.resetModules()
    auth = await import("@/stores/useAuthStore")
    auth.useAuthStore.setState({ user: null, loading: true })
    bus = await import("../pushMessageBus")

    const worker = createServiceWorker()
    vi.stubGlobal("navigator", { serviceWorker: worker })
    bus.ensurePushMessageBridge()
    worker.emit({ type: "PUSH_NOTIFICATION", id: "pending-before-transition" })

    auth.useAuthStore.setState({
      user: { id: TEST_USER_B_ID } as UserState,
      loading: true,
    })
    worker.emit({ type: "PUSH_NOTIFICATION", id: "unconfirmed-new-account" })
    auth.useAuthStore.setState({ user: null, loading: true })
    worker.emit({ type: "PUSH_NOTIFICATION", id: "unresolved" })
    for (const id of ["ssr-stub", "-1", "lhci-audit-user"]) {
      auth.useAuthStore.setState({ user: { id } as UserState, loading: false })
      worker.emit({ type: "PUSH_NOTIFICATION", id })
    }

    const subscriber = vi.fn()
    const unsubscribe = bus.subscribeToPushMessages(subscriber)
    expect(subscriber).not.toHaveBeenCalled()
    unsubscribe()
  })
})
