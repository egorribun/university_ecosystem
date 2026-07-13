/* eslint-disable @typescript-eslint/no-explicit-any */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { registerServiceWorker } from "../register-sw"
import { PWA_REFRESH_EVENT } from "@/app/pwaEvents"
import { SERVICE_WORKER_MESSAGE_TYPES } from "@/constants/serviceWorkerMessages"

describe("registerServiceWorker", () => {
  let addEventListenerSpy: any
  let dispatchEventSpy: any
  let originalLocation: any

  beforeEach(() => {
    addEventListenerSpy = vi.spyOn(window, "addEventListener")
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

  it("returns null if serviceWorker is not supported by browser", async () => {
    vi.stubGlobal("navigator", {})
    const reg = await registerServiceWorker()
    expect(reg).toBeNull()
  })

  it("registers service worker successfully and sets up listeners", async () => {
    const mockController = {
      postMessage: vi.fn(),
    }
    const mockActive = {
      postMessage: vi.fn(),
    }
    const mockWaiting = {
      postMessage: vi.fn(),
    }
    const mockInstalling = {
      state: "installing",
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }

    const mockRegistration: any = {
      active: mockActive,
      waiting: mockWaiting,
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

    // 1. Success run
    const reg = await registerServiceWorker("/custom-sw.js")
    expect(reg).toBe(mockRegistration)
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

    // Trigger update found listener setup check
    expect(mockRegistration.addEventListener).toHaveBeenCalledWith(
      "updatefound",
      expect.any(Function)
    )
    const updateFoundHandler = mockRegistration.addEventListener.mock.calls[0][1]

    // Simulate updatefound with a new installing sw
    let stateChangeHandler: any = null
    const installingSw = {
      state: "installing",
      addEventListener: vi.fn().mockImplementation((event, cb) => {
        if (event === "statechange") stateChangeHandler = cb
      }),
      removeEventListener: vi.fn(),
    }
    mockRegistration.installing = installingSw
    updateFoundHandler()

    expect(installingSw.addEventListener).toHaveBeenCalledWith("statechange", expect.any(Function))

    // Simulate installing SW state transitioning to "installed"
    installingSw.state = "installed"
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

    // Verify controllerchange listener reloads window
    expect(swListeners["controllerchange"]).toBeDefined()
    swListeners["controllerchange"]()
    expect(window.location.reload).toHaveBeenCalledTimes(1)
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

  it("does not reload page on controllerchange if window.name matches mock api initializer", async () => {
    const swListeners: Record<string, any> = {}
    const mockRegistration: any = {
      ready: Promise.resolve(),
    }
    const mockServiceWorkerContainer = {
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

    swListeners["controllerchange"]()
    expect(window.location.reload).not.toHaveBeenCalled()
  })

  it("returns null and logs when register throws an error", async () => {
    const mockServiceWorkerContainer = {
      register: vi.fn().mockRejectedValue(new Error("Network Error")),
    }
    vi.stubGlobal("navigator", {
      serviceWorker: mockServiceWorkerContainer,
    })

    const result = await registerServiceWorker()
    expect(result).toBeNull()
  })
})
