import { afterEach, describe, expect, it, vi } from "vitest"
import {
  clearPendingServiceWorkerUpdate,
  consumePendingPushEducation,
  dispatchServiceWorkerBootstrap,
  dispatchServiceWorkerUpdate,
  getPendingServiceWorkerUpdate,
  PUSH_EDUCATION_REQUEST_EVENT,
  PWA_REFRESH_EVENT,
  requestPushEducation,
  SERVICE_WORKER_BOOTSTRAP_EVENT,
  type ServiceWorkerBootstrapEventDetail,
  type ServiceWorkerUpdateEventDetail,
} from "../pwaEvents"

describe("requestPushEducation", () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.useRealTimers()
  })

  it("keeps an education request pending during SSR without dispatching a browser event", () => {
    vi.stubGlobal("window", undefined)

    requestPushEducation("student-1")

    expect(consumePendingPushEducation("student-1")).toBe(true)
    expect(consumePendingPushEducation("student-1")).toBe(false)
  })

  it("announces the request in the browser and honours it only for the same user", () => {
    const listener = vi.fn()
    window.addEventListener(PUSH_EDUCATION_REQUEST_EVENT, listener)

    try {
      requestPushEducation("student-1")
      expect(listener).toHaveBeenCalledTimes(1)
      expect(consumePendingPushEducation("student-2")).toBe(false)

      requestPushEducation("student-1")
      expect(consumePendingPushEducation("student-1")).toBe(true)
    } finally {
      window.removeEventListener(PUSH_EDUCATION_REQUEST_EVENT, listener)
    }
  })

  it("honours a pending request for exactly thirty seconds", () => {
    vi.useFakeTimers({ now: 1_000_000 })

    requestPushEducation("student-1")
    vi.setSystemTime(1_030_000)
    expect(consumePendingPushEducation("student-1")).toBe(true)

    requestPushEducation("student-1")
    vi.setSystemTime(1_060_001)
    expect(consumePendingPushEducation("student-1")).toBe(false)
  })
})

describe("dispatchServiceWorkerUpdate", () => {
  afterEach(() => {
    const pending = getPendingServiceWorkerUpdate()
    if (pending) clearPendingServiceWorkerUpdate(pending)
    vi.unstubAllGlobals()
  })

  it("retains the latest update and only clears the matching worker detail", () => {
    const first: ServiceWorkerUpdateEventDetail = {
      update: vi.fn().mockResolvedValue(undefined),
    }
    const second: ServiceWorkerUpdateEventDetail = {
      update: vi.fn().mockResolvedValue(undefined),
    }
    const received: Event[] = []
    const listener = (event: Event) => received.push(event)
    window.addEventListener(PWA_REFRESH_EVENT, listener)

    try {
      dispatchServiceWorkerUpdate(first)
      dispatchServiceWorkerUpdate(second)

      expect(received).toHaveLength(2)
      expect((received[0] as CustomEvent<ServiceWorkerUpdateEventDetail>).detail).toBe(first)
      expect(getPendingServiceWorkerUpdate()).toBe(second)

      clearPendingServiceWorkerUpdate(first)
      expect(getPendingServiceWorkerUpdate()).toBe(second)

      clearPendingServiceWorkerUpdate(null)
      expect(getPendingServiceWorkerUpdate()).toBe(second)
      expect(second.update).not.toHaveBeenCalled()

      clearPendingServiceWorkerUpdate(second)
      expect(getPendingServiceWorkerUpdate()).toBeNull()
    } finally {
      window.removeEventListener(PWA_REFRESH_EVENT, listener)
    }
  })

  it("does not retain an update callback when the browser window is unavailable", () => {
    const previous = getPendingServiceWorkerUpdate()
    if (previous) clearPendingServiceWorkerUpdate(previous)
    const update = vi.fn().mockResolvedValue(undefined)
    const detail: ServiceWorkerUpdateEventDetail = { update }
    vi.stubGlobal("window", undefined)

    dispatchServiceWorkerUpdate(detail)

    expect(getPendingServiceWorkerUpdate()).toBeNull()
    expect(update).not.toHaveBeenCalled()
  })
})

describe("dispatchServiceWorkerBootstrap", () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it("is safe when no browser window exists", () => {
    vi.stubGlobal("window", undefined)

    expect(() => dispatchServiceWorkerBootstrap("ready")).not.toThrow()
  })

  it("dispatches only bootstrap status to the current window", () => {
    const events: Event[] = []
    const listener = (event: Event) => events.push(event)
    window.addEventListener(SERVICE_WORKER_BOOTSTRAP_EVENT, listener)
    const dispatchSpy = vi.spyOn(window, "dispatchEvent")

    try {
      dispatchServiceWorkerBootstrap("ready")

      expect(events).toHaveLength(1)
      const [event] = events
      if (event === undefined) throw new Error("Bootstrap event was not dispatched")
      expect(event).toBeInstanceOf(CustomEvent)
      expect(event.type).toBe(SERVICE_WORKER_BOOTSTRAP_EVENT)
      expect(dispatchSpy).toHaveBeenCalledTimes(1)
      expect(dispatchSpy).toHaveBeenCalledWith(event)
      expect((event as CustomEvent<ServiceWorkerBootstrapEventDetail>).detail).toStrictEqual({
        status: "ready",
      })
    } finally {
      try {
        window.removeEventListener(SERVICE_WORKER_BOOTSTRAP_EVENT, listener)
      } finally {
        dispatchSpy.mockRestore()
      }
    }
  })
})
