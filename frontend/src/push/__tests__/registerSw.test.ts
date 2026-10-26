import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { registerServiceWorker } from "../register-sw"
import {
  PWA_REFRESH_EVENT,
  SERVICE_WORKER_BOOTSTRAP_EVENT,
  type ServiceWorkerBootstrapEventDetail,
} from "@/app/pwaEvents"
import { SERVICE_WORKER_MESSAGE_TYPES } from "@/constants/serviceWorkerMessages"
import { withExpectedConsole } from "@/tests/strictConsole"

describe("registerServiceWorker", () => {
  let addEventListenerSpy: any
  let documentAddEventListenerSpy: any
  let dispatchEventSpy: any
  let originalLocation: any

  beforeEach(() => {
    addEventListenerSpy = vi.spyOn(window, "addEventListener")
    documentAddEventListenerSpy = vi.spyOn(document, "addEventListener")
    dispatchEventSpy = vi.spyOn(window, "dispatchEvent")

    originalLocation = window.location
    const mockLocation = Object.create(originalLocation)
    Object.defineProperty(mockLocation, "reload", {
      value: vi.fn(),
      writable: true,
      configurable: true,
      enumerable: true,
    })
    Object.defineProperty(window, "location", {
      value: mockLocation,
      writable: true,
      configurable: true,
    })

    vi.clearAllMocks()
  })

  afterEach(() => {
    if (addEventListenerSpy && typeof addEventListenerSpy.mockRestore === "function") {
      addEventListenerSpy.mockRestore()
    }
    if (
      documentAddEventListenerSpy &&
      typeof documentAddEventListenerSpy.mockRestore === "function"
    ) {
      documentAddEventListenerSpy.mockRestore()
    }
    if (dispatchEventSpy && typeof dispatchEventSpy.mockRestore === "function") {
      dispatchEventSpy.mockRestore()
    }
    Object.defineProperty(window, "location", {
      value: originalLocation,
      writable: true,
      configurable: true,
    })
    vi.restoreAllMocks()
    if (typeof window !== "undefined") {
      window.name = ""
    }
  })

  it("returns null and reports unsupported when serviceWorker is not available", async () => {
    vi.stubGlobal("navigator", {})
    let bootstrapStatus: ServiceWorkerBootstrapEventDetail["status"] | undefined
    window.addEventListener(
      SERVICE_WORKER_BOOTSTRAP_EVENT,
      (event) => {
        bootstrapStatus = (event as CustomEvent<ServiceWorkerBootstrapEventDetail>).detail.status
      },
      { once: true }
    )
    const reg = await registerServiceWorker()
    expect(reg).toBeNull()
    expect(bootstrapStatus).toBe("unsupported")
  })

  it("registers service worker successfully and sets up listeners", async () => {
    const mockController = {
      postMessage: vi.fn(),
    }
    const mockActive = {
      postMessage: vi.fn(),
    }
    const mockWaiting = {
      state: "installing",
      postMessage: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }
    const mockInstalling = {
      state: "installing",
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }

    const mockRegistration: any = {
      active: mockActive,
      waiting: null,
      installing: mockInstalling,
      addEventListener: vi.fn(),
      ready: Promise.resolve(),
    }

    const swListeners: Record<string, any> = {}
    const mockServiceWorkerContainer = {
      controller: mockController,
      ready: Promise.resolve(mockRegistration),
      register: vi.fn().mockResolvedValue(mockRegistration),
      addEventListener: vi.fn().mockImplementation((event, listener) => {
        swListeners[event] = listener
      }),
    }

    vi.stubGlobal("navigator", {
      serviceWorker: mockServiceWorkerContainer,
      onLine: true,
    })

    let bootstrapDetail: ServiceWorkerBootstrapEventDetail | undefined
    let queueListenersReadyAtSignal = false
    window.addEventListener(
      SERVICE_WORKER_BOOTSTRAP_EVENT,
      (event) => {
        bootstrapDetail = (event as CustomEvent<ServiceWorkerBootstrapEventDetail>).detail
        queueListenersReadyAtSignal =
          addEventListenerSpy.mock.calls.some((call: unknown[]) => call[0] === "online") &&
          documentAddEventListenerSpy.mock.calls.some(
            (call: unknown[]) => call[0] === "visibilitychange"
          )
      },
      { once: true }
    )
    const reg = await registerServiceWorker("/custom-sw.js")
    expect(reg).toBe(mockRegistration)
    expect(bootstrapDetail).toEqual({ status: "ready" })
    expect(queueListenersReadyAtSignal).toBe(true)
    expect(mockServiceWorkerContainer.register).toHaveBeenCalledWith("/custom-sw.js", {
      scope: "/",
      updateViaCache: "none",
    })

    // Verify queue processing requested on controller
    expect(mockController.postMessage).toHaveBeenCalledWith({
      type: SERVICE_WORKER_MESSAGE_TYPES.PROCESS_NOTIFICATION_CLICK_QUEUE,
    })

    // Verify online event setup
    expect(window.addEventListener).toHaveBeenCalledWith("online", expect.any(Function))

    // Trigger online event listener
    const onlineHandler = (window.addEventListener as any).mock.calls.find(
      (c: any) => c[0] === "online"
    )[1]
    mockController.postMessage.mockClear()
    onlineHandler()
    expect(mockController.postMessage).toHaveBeenCalledTimes(1)

    const visibilityHandler = documentAddEventListenerSpy.mock.calls.find(
      (call: any[]) => call[0] === "visibilitychange"
    )?.[1]
    expect(visibilityHandler).toEqual(expect.any(Function))
    mockController.postMessage.mockClear()
    visibilityHandler()
    expect(mockController.postMessage).toHaveBeenCalledTimes(1)
    const visibilitySpy = vi.spyOn(document, "visibilityState", "get").mockReturnValue("hidden")
    visibilityHandler()
    expect(mockController.postMessage).toHaveBeenCalledTimes(1)
    visibilitySpy.mockRestore()

    // Trigger update found listener setup check
    expect(mockRegistration.addEventListener).toHaveBeenCalledWith(
      "updatefound",
      expect.any(Function)
    )
    const updateFoundHandler = mockRegistration.addEventListener.mock.calls[0][1]

    // Browsers may emit updatefound before exposing an installing worker.
    mockRegistration.installing = null
    updateFoundHandler()

    // Simulate updatefound with a new installing sw
    let stateChangeHandler: any = null
    const installingSw = mockWaiting
    installingSw.addEventListener = vi.fn().mockImplementation((event, cb) => {
      if (event === "statechange") stateChangeHandler = cb
    })
    mockRegistration.installing = installingSw
    updateFoundHandler()

    expect(installingSw.addEventListener).toHaveBeenCalledWith("statechange", expect.any(Function))

    // Ignore intermediate states until the worker is fully installed.
    stateChangeHandler()
    expect(installingSw.removeEventListener).not.toHaveBeenCalled()

    // Simulate installing SW state transitioning to "installed". The same
    // worker object becomes the registration's waiting worker.
    installingSw.state = "installed"
    mockRegistration.waiting = installingSw
    stateChangeHandler()

    // Verifies window.dispatchEvent was called with update details
    expect(window.dispatchEvent).toHaveBeenCalledWith(expect.any(CustomEvent))
    const customEventCall = (window.dispatchEvent as any).mock.calls.find(
      (c: any) => c[0].type === PWA_REFRESH_EVENT
    )[0]
    expect(customEventCall.detail).toBeDefined()

    // Test calling the update detail callback triggers postMessage to waiting sw
    await customEventCall.detail.update()
    expect(mockWaiting.postMessage).toHaveBeenCalledWith({
      type: SERVICE_WORKER_MESSAGE_TYPES.SKIP_WAITING,
    })
    mockRegistration.waiting = null
    await customEventCall.detail.update()
    expect(mockWaiting.postMessage).toHaveBeenCalledTimes(1)

    // A choice in this tab authorizes only the prompted worker's activation.
    expect(swListeners["controllerchange"]).toBeDefined()
    expect(window.location.reload).not.toHaveBeenCalled()
    mockServiceWorkerContainer.controller = mockWaiting
    swListeners["controllerchange"]()
    expect(window.location.reload).toHaveBeenCalledTimes(1)
    swListeners["controllerchange"]()
    expect(window.location.reload).toHaveBeenCalledTimes(1)
  })

  it("retries registration after an initialization failure", async () => {
    const mockRegistration: any = {
      active: { postMessage: vi.fn() },
      addEventListener: vi.fn(),
      ready: Promise.resolve(),
    }
    const swListeners: Record<string, any> = {}
    const mockServiceWorkerContainer = {
      controller: null,
      ready: Promise.resolve(mockRegistration),
      register: vi
        .fn()
        .mockRejectedValueOnce(new Error("Network Error"))
        .mockResolvedValueOnce(mockRegistration),
      addEventListener: vi.fn().mockImplementation((event, listener) => {
        swListeners[event] = listener
      }),
    }
    vi.stubGlobal("navigator", {
      serviceWorker: mockServiceWorkerContainer,
      onLine: true,
    })

    let failedAttempt!: Promise<ServiceWorkerRegistration | null>
    const firstResult = await withExpectedConsole(
      "error",
      "Service worker registration failed",
      () => {
        failedAttempt = registerServiceWorker("/retry-sw.js")
        return failedAttempt
      }
    )
    expect(firstResult).toBeNull()

    const retryAttempt = registerServiceWorker("/retry-sw.js")
    expect(retryAttempt).not.toBe(failedAttempt)
    await expect(retryAttempt).resolves.toBe(mockRegistration)
    expect(mockServiceWorkerContainer.register).toHaveBeenCalledTimes(2)
    expect(mockServiceWorkerContainer.addEventListener).toHaveBeenCalledOnce()
    expect(mockRegistration.addEventListener).toHaveBeenCalledOnce()
    expect(swListeners["controllerchange"]).toEqual(expect.any(Function))
  })

  it("keeps other path tasks cached when one registration path fails", async () => {
    const defaultRegistration: any = {
      active: { postMessage: vi.fn() },
      waiting: null,
      addEventListener: vi.fn(),
    }
    const retriedCustomRegistration: any = {
      active: { postMessage: vi.fn() },
      waiting: null,
      addEventListener: vi.fn(),
    }
    const swListeners: Record<string, any> = {}
    const mockServiceWorkerContainer = {
      controller: null,
      ready: Promise.resolve(defaultRegistration),
      register: vi
        .fn()
        .mockRejectedValueOnce(new Error("Network Error"))
        .mockResolvedValueOnce(defaultRegistration)
        .mockResolvedValueOnce(retriedCustomRegistration),
      addEventListener: vi.fn().mockImplementation((event, listener) => {
        swListeners[event] = listener
      }),
    }
    vi.stubGlobal("navigator", {
      serviceWorker: mockServiceWorkerContainer,
      onLine: true,
    })

    let failedCustomPathTask!: Promise<ServiceWorkerRegistration | null>
    let defaultPathTask!: Promise<ServiceWorkerRegistration | null>
    const failureResult = await withExpectedConsole(
      "error",
      "Service worker registration failed",
      () => {
        failedCustomPathTask = registerServiceWorker("/custom-sw.js")
        defaultPathTask = registerServiceWorker()
        return failedCustomPathTask
      }
    )
    expect(failureResult).toBeNull()
    expect(failedCustomPathTask).not.toBe(defaultPathTask)
    await expect(defaultPathTask).resolves.toBe(defaultRegistration)

    const retainedDefaultPathTask = registerServiceWorker()
    expect(retainedDefaultPathTask).toBe(defaultPathTask)
    await expect(retainedDefaultPathTask).resolves.toBe(defaultRegistration)
    expect(mockServiceWorkerContainer.register).toHaveBeenCalledTimes(2)
    expect(mockServiceWorkerContainer.addEventListener).toHaveBeenCalledOnce()
    expect(defaultRegistration.addEventListener).toHaveBeenCalledOnce()

    const retriedCustomPathTask = registerServiceWorker("/custom-sw.js")
    expect(retriedCustomPathTask).not.toBe(failedCustomPathTask)
    await expect(retriedCustomPathTask).resolves.toBe(retriedCustomRegistration)
    expect(mockServiceWorkerContainer.register).toHaveBeenCalledTimes(3)
    expect(mockServiceWorkerContainer.register).toHaveBeenNthCalledWith(1, "/custom-sw.js", {
      scope: "/",
      updateViaCache: "none",
    })
    expect(mockServiceWorkerContainer.register).toHaveBeenNthCalledWith(2, "/sw.js", {
      scope: "/",
      updateViaCache: "none",
    })
    expect(mockServiceWorkerContainer.register).toHaveBeenNthCalledWith(3, "/custom-sw.js", {
      scope: "/",
      updateViaCache: "none",
    })
    expect(mockServiceWorkerContainer.addEventListener).toHaveBeenCalledTimes(2)
    expect(defaultRegistration.addEventListener).toHaveBeenCalledOnce()
    expect(retriedCustomRegistration.addEventListener).toHaveBeenCalledOnce()
  })

  it("registers the default path separately from an in-flight custom path", async () => {
    const customRegistration: any = {
      active: { postMessage: vi.fn() },
      waiting: null,
      addEventListener: vi.fn(),
    }
    const defaultRegistration: any = {
      active: { postMessage: vi.fn() },
      waiting: null,
      addEventListener: vi.fn(),
    }
    const mockServiceWorkerContainer = {
      controller: null,
      ready: Promise.resolve(customRegistration),
      register: vi
        .fn()
        .mockResolvedValueOnce(customRegistration)
        .mockResolvedValueOnce(defaultRegistration),
      addEventListener: vi.fn(),
    }
    vi.stubGlobal("navigator", {
      serviceWorker: mockServiceWorkerContainer,
      onLine: true,
    })

    const customPathTask = registerServiceWorker("/custom-sw.js")
    const duplicateCustomPathTask = registerServiceWorker("/custom-sw.js")
    const defaultPathTask = registerServiceWorker()

    expect(duplicateCustomPathTask).toBe(customPathTask)
    expect(defaultPathTask).not.toBe(customPathTask)
    await expect(customPathTask).resolves.toBe(customRegistration)
    await expect(defaultPathTask).resolves.toBe(defaultRegistration)
    expect(mockServiceWorkerContainer.register).toHaveBeenCalledTimes(2)
    expect(mockServiceWorkerContainer.register).toHaveBeenNthCalledWith(1, "/custom-sw.js", {
      scope: "/",
      updateViaCache: "none",
    })
    expect(mockServiceWorkerContainer.register).toHaveBeenNthCalledWith(2, "/sw.js", {
      scope: "/",
      updateViaCache: "none",
    })
  })

  it("shares service-worker setup across duplicate registration calls in one document", async () => {
    const controller = { postMessage: vi.fn() }
    const waitingWorker = {
      state: "installed",
      postMessage: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }
    const mockRegistration: any = {
      active: { postMessage: vi.fn() },
      waiting: waitingWorker,
      addEventListener: vi.fn(),
      ready: Promise.resolve(),
    }
    const swListeners: Record<string, any> = {}
    const mockServiceWorkerContainer = {
      controller,
      ready: Promise.resolve(mockRegistration),
      register: vi.fn().mockResolvedValue(mockRegistration),
      addEventListener: vi.fn().mockImplementation((event, listener) => {
        swListeners[event] = listener
      }),
    }
    vi.stubGlobal("navigator", {
      serviceWorker: mockServiceWorkerContainer,
      onLine: true,
    })

    const firstCall = registerServiceWorker("/custom-sw.js")
    const secondCall = registerServiceWorker("/custom-sw.js")
    expect(secondCall).toBe(firstCall)
    await expect(Promise.all([firstCall, secondCall])).resolves.toEqual([
      mockRegistration,
      mockRegistration,
    ])
    expect(mockServiceWorkerContainer.register).toHaveBeenCalledOnce()
    expect(mockRegistration.addEventListener).toHaveBeenCalledOnce()
    expect(mockServiceWorkerContainer.addEventListener).toHaveBeenCalledOnce()

    const updateEvent = dispatchEventSpy.mock.calls
      .map((call: unknown[]) => call[0] as Event)
      .find((event: Event) => event.type === PWA_REFRESH_EVENT) as
      CustomEvent<{ update: () => Promise<void> }> | undefined
    expect(updateEvent).toBeInstanceOf(CustomEvent)

    // Deliver the same transition more than once after both callers shared setup.
    mockRegistration.waiting = null
    mockServiceWorkerContainer.controller = waitingWorker
    swListeners["controllerchange"]()
    await updateEvent!.detail.update()
    swListeners["controllerchange"]()
    await updateEvent!.detail.update()
    expect(window.location.reload).toHaveBeenCalledOnce()
  })

  it("handles online status when controller is absent but active SW exists", async () => {
    const mockActive = {
      postMessage: vi.fn(),
    }
    const mockRegistration: any = {
      active: mockActive,
      addEventListener: vi.fn(),
      ready: Promise.resolve(),
    }
    const mockServiceWorkerContainer = {
      controller: null,
      ready: Promise.resolve(mockRegistration),
      register: vi.fn().mockResolvedValue(mockRegistration),
      addEventListener: vi.fn(),
    }
    vi.stubGlobal("navigator", {
      serviceWorker: mockServiceWorkerContainer,
      onLine: true,
    })

    await registerServiceWorker()
    expect(mockActive.postMessage).toHaveBeenCalledWith({
      type: SERVICE_WORKER_MESSAGE_TYPES.PROCESS_NOTIFICATION_CLICK_QUEUE,
    })
  })

  it("tolerates a controller that cannot receive queue messages", async () => {
    const mockRegistration: any = {
      active: null,
      addEventListener: vi.fn(),
    }
    const mockServiceWorkerContainer = {
      controller: {},
      ready: Promise.resolve(mockRegistration),
      register: vi.fn().mockResolvedValue(mockRegistration),
      addEventListener: vi.fn(),
    }
    vi.stubGlobal("navigator", {
      serviceWorker: mockServiceWorkerContainer,
      onLine: true,
    })

    await expect(registerServiceWorker()).resolves.toBe(mockRegistration)
  })

  it.each([null, {}])(
    "waits safely when no controller or message-capable active worker exists (%s)",
    async (active) => {
      const registration = { active, addEventListener: vi.fn() }
      vi.stubGlobal("navigator", {
        serviceWorker: {
          controller: null,
          ready: Promise.resolve(registration),
          register: vi.fn().mockResolvedValue(registration),
          addEventListener: vi.fn(),
        },
        onLine: true,
      })
      await expect(registerServiceWorker()).resolves.toBe(registration)
    }
  )

  it("does not request queue processing when offline", async () => {
    const mockActive = {
      postMessage: vi.fn(),
    }
    const mockRegistration: any = {
      active: mockActive,
      addEventListener: vi.fn(),
      ready: Promise.resolve(),
    }
    const mockServiceWorkerContainer = {
      controller: null,
      ready: Promise.resolve(mockRegistration),
      register: vi.fn().mockResolvedValue(mockRegistration),
      addEventListener: vi.fn(),
    }
    vi.stubGlobal("navigator", {
      serviceWorker: mockServiceWorkerContainer,
      onLine: false,
    })

    await registerServiceWorker()
    expect(mockActive.postMessage).not.toHaveBeenCalled()
  })

  it("swallows background-sync registration failures", async () => {
    const registerSync = vi.fn().mockRejectedValue(new Error("sync unavailable"))
    const mockRegistration: any = {
      active: { postMessage: vi.fn() },
      sync: { register: registerSync },
      addEventListener: vi.fn(),
      ready: Promise.resolve(),
    }
    const mockServiceWorkerContainer = {
      controller: null,
      ready: Promise.resolve(mockRegistration),
      register: vi.fn().mockResolvedValue(mockRegistration),
      addEventListener: vi.fn(),
    }
    vi.stubGlobal("navigator", {
      serviceWorker: mockServiceWorkerContainer,
      onLine: true,
    })

    await registerServiceWorker()

    const onlineHandler = addEventListenerSpy.mock.calls.find(
      (call: unknown[]) => call[0] === "online"
    )?.[1] as (() => Promise<void>) | undefined
    expect(onlineHandler).toEqual(expect.any(Function))
    await onlineHandler?.()
    expect(registerSync).toHaveBeenCalledWith("sync-offline-mutations")
  })

  it("does not reload a tab that did not accept the update, regardless of window.name", async () => {
    const swListeners: Record<string, any> = {}
    const mockRegistration: any = {
      ready: Promise.resolve(),
    }
    const mockServiceWorkerContainer = {
      controller: { postMessage: vi.fn() },
      ready: Promise.resolve(mockRegistration),
      register: vi.fn().mockResolvedValue(mockRegistration),
      addEventListener: vi.fn().mockImplementation((event, listener) => {
        swListeners[event] = listener
      }),
    }
    vi.stubGlobal("navigator", {
      serviceWorker: mockServiceWorkerContainer,
    })

    window.name = "__mock_api_initialized__"
    await registerServiceWorker()

    mockServiceWorkerContainer.controller = { postMessage: vi.fn() }
    swListeners["controllerchange"]()
    expect(window.location.reload).not.toHaveBeenCalled()
  })

  it("ignores the first controller claim and waits for local update approval", async () => {
    const swListeners: Record<string, any> = {}
    const mockRegistration: any = {
      active: { postMessage: vi.fn() },
      ready: Promise.resolve(),
    }
    const mockServiceWorkerContainer = {
      controller: null as ServiceWorker | null,
      ready: Promise.resolve(mockRegistration),
      register: vi.fn().mockResolvedValue(mockRegistration),
      addEventListener: vi.fn().mockImplementation((event, listener) => {
        swListeners[event] = listener
      }),
    }
    vi.stubGlobal("navigator", {
      serviceWorker: mockServiceWorkerContainer,
      onLine: true,
    })

    await registerServiceWorker()
    mockServiceWorkerContainer.controller = { postMessage: vi.fn() } as unknown as ServiceWorker
    swListeners["controllerchange"]()

    expect(window.location.reload).not.toHaveBeenCalled()

    mockServiceWorkerContainer.controller = { postMessage: vi.fn() } as unknown as ServiceWorker
    swListeners["controllerchange"]()

    expect(window.location.reload).not.toHaveBeenCalled()
  })

  it("keeps an already-open tab until it accepts after another tab activates the update", async () => {
    const waitingWorker = { postMessage: vi.fn() }
    const mockRegistration: any = {
      active: { postMessage: vi.fn() },
      waiting: waitingWorker,
      addEventListener: vi.fn(),
      ready: Promise.resolve(),
    }
    const swListeners: Record<string, any> = {}
    const mockServiceWorkerContainer = {
      controller: { postMessage: vi.fn() },
      ready: Promise.resolve(mockRegistration),
      register: vi.fn().mockResolvedValue(mockRegistration),
      addEventListener: vi.fn().mockImplementation((event, listener) => {
        swListeners[event] = listener
      }),
    }
    vi.stubGlobal("navigator", {
      serviceWorker: mockServiceWorkerContainer,
      onLine: true,
    })

    await registerServiceWorker()
    const updateEvent = dispatchEventSpy.mock.calls.find(
      (call: unknown[]) => (call[0] as Event).type === PWA_REFRESH_EVENT
    )?.[0] as CustomEvent<{ update: () => Promise<void> }> | undefined
    expect(updateEvent).toBeInstanceOf(CustomEvent)

    // The worker was activated by another tab. This tab stays on its current
    // document until its own visible update action is chosen.
    mockRegistration.waiting = null
    mockServiceWorkerContainer.controller = waitingWorker
    swListeners["controllerchange"]()
    expect(window.location.reload).not.toHaveBeenCalled()

    await updateEvent!.detail.update()
    expect(window.location.reload).toHaveBeenCalledOnce()
    await updateEvent!.detail.update()
    expect(window.location.reload).toHaveBeenCalledOnce()
  })

  it("waits for a queued controllerchange after this tab accepts the activating worker", async () => {
    const waitingWorker = { state: "installed", postMessage: vi.fn() }
    const mockRegistration: any = {
      active: { postMessage: vi.fn() },
      waiting: waitingWorker,
      addEventListener: vi.fn(),
      ready: Promise.resolve(),
    }
    const swListeners: Record<string, any> = {}
    const mockServiceWorkerContainer = {
      controller: { postMessage: vi.fn() },
      ready: Promise.resolve(mockRegistration),
      register: vi.fn().mockResolvedValue(mockRegistration),
      addEventListener: vi.fn().mockImplementation((event, listener) => {
        swListeners[event] = listener
      }),
    }
    vi.stubGlobal("navigator", {
      serviceWorker: mockServiceWorkerContainer,
      onLine: true,
    })

    await registerServiceWorker()
    const updateEvent = dispatchEventSpy.mock.calls.find(
      (call: unknown[]) => (call[0] as Event).type === PWA_REFRESH_EVENT
    )?.[0] as CustomEvent<{ update: () => Promise<void> }> | undefined
    expect(updateEvent).toBeInstanceOf(CustomEvent)

    // Activation has started and cleared waiting, but this tab's queued event
    // has not run yet. Its click records consent without reloading prematurely.
    waitingWorker.state = "activating"
    mockRegistration.waiting = null
    mockServiceWorkerContainer.controller = waitingWorker
    await updateEvent!.detail.update()
    expect(waitingWorker.postMessage).not.toHaveBeenCalled()
    expect(window.location.reload).not.toHaveBeenCalled()

    swListeners["controllerchange"]()
    expect(window.location.reload).toHaveBeenCalledOnce()
    swListeners["controllerchange"]()
    await updateEvent!.detail.update()
    expect(window.location.reload).toHaveBeenCalledOnce()
  })

  it("does not let a stale W1 prompt reload after W2 controls the page", async () => {
    const firstWaitingWorker = { postMessage: vi.fn() }
    const mockRegistration: any = {
      active: { postMessage: vi.fn() },
      waiting: firstWaitingWorker,
      addEventListener: vi.fn(),
      ready: Promise.resolve(),
    }
    const swListeners: Record<string, any> = {}
    const mockServiceWorkerContainer = {
      controller: { postMessage: vi.fn() },
      ready: Promise.resolve(mockRegistration),
      register: vi.fn().mockResolvedValue(mockRegistration),
      addEventListener: vi.fn().mockImplementation((event, listener) => {
        swListeners[event] = listener
      }),
    }
    vi.stubGlobal("navigator", {
      serviceWorker: mockServiceWorkerContainer,
      onLine: true,
    })

    await registerServiceWorker()
    const updateEvents = () =>
      dispatchEventSpy.mock.calls
        .map((call: unknown[]) => call[0] as Event)
        .filter((event: Event) => event.type === PWA_REFRESH_EVENT) as Array<
        CustomEvent<{ update: () => Promise<void> }>
      >
    const firstUpdateEvent = updateEvents()[0]
    expect(firstUpdateEvent).toBeInstanceOf(CustomEvent)
    if (!firstUpdateEvent) {
      throw new Error("Expected first service worker update event")
    }

    // W1 becomes the controller and its event is handled, but this tab has not
    // accepted W1. Its consent state now records controllerchange for W1.
    mockRegistration.waiting = null
    mockServiceWorkerContainer.controller = firstWaitingWorker
    swListeners["controllerchange"]()
    expect(window.location.reload).not.toHaveBeenCalled()

    // W2 becomes current before this tab handles the queued controllerchange.
    // Clicking the still-visible W1 prompt must not use W1's sticky eligibility.
    const secondWorker = { postMessage: vi.fn() }
    mockServiceWorkerContainer.controller = secondWorker
    await firstUpdateEvent.detail.update()
    expect(window.location.reload).not.toHaveBeenCalled()

    // The queued event creates independent consent state for W2. W2 still needs
    // this tab's own prompt action before a reload is allowed.
    swListeners["controllerchange"]()
    expect(window.location.reload).not.toHaveBeenCalled()
    const secondUpdateEvent = updateEvents()[1]
    expect(secondUpdateEvent).toBeInstanceOf(CustomEvent)
    if (!secondUpdateEvent) {
      throw new Error("Expected second service worker update event")
    }
    await secondUpdateEvent.detail.update()
    expect(window.location.reload).toHaveBeenCalledOnce()
    await secondUpdateEvent.detail.update()
    swListeners["controllerchange"]()
    expect(window.location.reload).toHaveBeenCalledOnce()
  })

  it("does not reload without update approval when the first claim event was missed while waiting for ready", async () => {
    let resolveReady!: (registration: any) => void
    const ready = new Promise<any>((resolve) => {
      resolveReady = resolve
    })
    const mockRegistration: any = {
      active: { postMessage: vi.fn() },
      ready,
    }
    let controller: ServiceWorker | null = null
    const mockServiceWorkerContainer = new EventTarget() as EventTarget & {
      controller: ServiceWorker | null
      ready: Promise<any>
      register: ReturnType<typeof vi.fn>
    }
    Object.defineProperty(mockServiceWorkerContainer, "controller", {
      get: () => controller,
    })
    mockServiceWorkerContainer.ready = ready
    mockServiceWorkerContainer.register = vi.fn().mockResolvedValue(mockRegistration)
    vi.stubGlobal("navigator", {
      serviceWorker: mockServiceWorkerContainer,
      onLine: true,
    })

    const registrationPromise = registerServiceWorker()
    controller = { postMessage: vi.fn() } as unknown as ServiceWorker
    // The first-claim event fires before registration reaches `ready`, so this
    // native EventTarget correctly has no listener to receive it.
    mockServiceWorkerContainer.dispatchEvent(new Event("controllerchange"))
    expect(window.location.reload).not.toHaveBeenCalled()

    resolveReady(mockRegistration)
    await registrationPromise

    controller = { postMessage: vi.fn() } as unknown as ServiceWorker
    mockServiceWorkerContainer.dispatchEvent(new Event("controllerchange"))

    expect(window.location.reload).not.toHaveBeenCalled()
  })

  it("ignores a queued initial claim and does not reload after an unaccepted update", async () => {
    let resolveReady!: (registration: any) => void
    const ready = new Promise<any>((resolve) => {
      resolveReady = resolve
    })
    const mockRegistration: any = {
      active: { postMessage: vi.fn() },
      ready,
    }
    let controller: ServiceWorker | null = null
    const mockServiceWorkerContainer = new EventTarget() as EventTarget & {
      controller: ServiceWorker | null
      ready: Promise<any>
      register: ReturnType<typeof vi.fn>
    }
    Object.defineProperty(mockServiceWorkerContainer, "controller", {
      get: () => controller,
    })
    mockServiceWorkerContainer.ready = ready
    mockServiceWorkerContainer.register = vi.fn().mockResolvedValue(mockRegistration)
    vi.stubGlobal("navigator", {
      serviceWorker: mockServiceWorkerContainer,
      onLine: true,
    })

    const registrationPromise = registerServiceWorker()
    controller = { postMessage: vi.fn() } as unknown as ServiceWorker
    resolveReady(mockRegistration)
    await registrationPromise

    // The initial controller is already assigned when the listener is added;
    // delivering its still-queued event must not look like an update.
    mockServiceWorkerContainer.dispatchEvent(new Event("controllerchange"))
    expect(window.location.reload).not.toHaveBeenCalled()

    controller = { postMessage: vi.fn() } as unknown as ServiceWorker
    mockServiceWorkerContainer.dispatchEvent(new Event("controllerchange"))
    expect(window.location.reload).not.toHaveBeenCalled()
  })

  it("returns null and logs when register throws an error", async () => {
    const mockServiceWorkerContainer = {
      register: vi.fn().mockRejectedValue(new Error("Network Error")),
    }
    vi.stubGlobal("navigator", {
      serviceWorker: mockServiceWorkerContainer,
    })

    let bootstrapStatus: ServiceWorkerBootstrapEventDetail["status"] | undefined
    window.addEventListener(
      SERVICE_WORKER_BOOTSTRAP_EVENT,
      (event) => {
        bootstrapStatus = (event as CustomEvent<ServiceWorkerBootstrapEventDetail>).detail.status
      },
      { once: true }
    )
    const result = await withExpectedConsole("error", "Service worker registration failed", () =>
      registerServiceWorker()
    )
    expect(result).toBeNull()
    expect(bootstrapStatus).toBe("failed")
  })
})
