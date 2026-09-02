import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import {
  APP_HYDRATED_EVENT,
  BRAND_BOOT_LOADER_EXIT_TIMEOUT_MS,
  markAppHydrated,
} from "../hydration"

const appendLoader = (parent: Element = document.body) => {
  const loader = document.createElement("div")
  loader.dataset.brandBootLoader = ""
  loader.dataset.state = "active"
  loader.setAttribute("aria-busy", "true")
  parent.append(loader)
  return loader
}

describe("hydration boundary", () => {
  beforeEach(() => {
    vi.useFakeTimers()
    delete window.__APP_HYDRATED
    document.body.replaceChildren()
  })

  afterEach(() => {
    vi.useRealTimers()
    document.body.replaceChildren()
  })

  it("releases and removes the SSR loader once hydration is published", () => {
    const loader = appendLoader()
    const onHydrated = vi.fn()
    // Keep the wire-level event name literal here so changing the exported
    // constant cannot make the test follow the same typo as production.
    window.addEventListener("ue:app-hydrated", onHydrated)

    markAppHydrated()

    expect(window.__APP_HYDRATED).toBe(true)
    expect(onHydrated).toHaveBeenCalledOnce()
    vi.advanceTimersByTime(0)
    expect(loader).toHaveAttribute("data-state", "exiting")
    expect(loader).toHaveAttribute("aria-busy", "false")
    expect(loader).toBeInTheDocument()

    vi.advanceTimersByTime(BRAND_BOOT_LOADER_EXIT_TIMEOUT_MS - 1)
    expect(loader).toBeInTheDocument()
    vi.advanceTimersByTime(1)
    expect(loader).not.toBeInTheDocument()

    window.removeEventListener("ue:app-hydrated", onHydrated)
  })

  it("removes the legacy loader on transition end and cancels its fallback timer", () => {
    const loader = appendLoader()
    const clearTimeoutSpy = vi.spyOn(window, "clearTimeout")
    const addEventListenerSpy = vi.spyOn(loader, "addEventListener")
    const removeEventListenerSpy = vi.spyOn(loader, "removeEventListener")

    markAppHydrated()
    vi.advanceTimersByTime(0)
    expect(addEventListenerSpy).toHaveBeenCalledWith("transitionend", expect.any(Function), {
      once: true,
    })
    loader.dispatchEvent(new Event("transitionend"))

    expect(loader).not.toBeInTheDocument()
    expect(clearTimeoutSpy).toHaveBeenCalledWith(expect.anything())
    expect(removeEventListenerSpy).toHaveBeenCalledWith("transitionend", expect.any(Function))
    vi.advanceTimersByTime(BRAND_BOOT_LOADER_EXIT_TIMEOUT_MS)
    expect(loader).not.toBeInTheDocument()
  })

  it("does not remove a legacy loader adopted by the client root during its exit", () => {
    const root = document.createElement("div")
    root.id = "root"
    document.body.append(root)
    const loader = appendLoader()

    markAppHydrated()
    vi.advanceTimersByTime(0)
    root.append(loader)
    loader.dispatchEvent(new Event("transitionend"))

    expect(loader).toBeInTheDocument()
    expect(loader.closest("#root")).toBe(root)
    vi.advanceTimersByTime(BRAND_BOOT_LOADER_EXIT_TIMEOUT_MS)
    expect(loader).toBeInTheDocument()
  })

  it("does not remove a loader that belongs to the client root", () => {
    const root = document.createElement("div")
    root.id = "root"
    document.body.append(root)
    const loader = appendLoader(root)

    markAppHydrated()
    vi.advanceTimersByTime(BRAND_BOOT_LOADER_EXIT_TIMEOUT_MS)

    expect(loader).toHaveAttribute("data-state", "active")
    expect(loader).toHaveAttribute("aria-busy", "true")
    expect(loader).toBeInTheDocument()
  })

  it("publishes hydration and schedules cleanup only once", () => {
    const loader = appendLoader()
    const onHydrated = vi.fn()
    window.addEventListener("ue:app-hydrated", onHydrated)

    markAppHydrated()
    markAppHydrated()

    expect(onHydrated).toHaveBeenCalledOnce()
    vi.advanceTimersByTime(0)
    vi.advanceTimersByTime(BRAND_BOOT_LOADER_EXIT_TIMEOUT_MS)
    expect(loader).not.toBeInTheDocument()

    window.removeEventListener("ue:app-hydrated", onHydrated)
  })

  it("does not schedule a second legacy cleanup while the first is queued", () => {
    const loader = appendLoader()
    const onHydrated = vi.fn()
    const setTimeoutSpy = vi.spyOn(window, "setTimeout")
    window.addEventListener(APP_HYDRATED_EVENT, onHydrated)

    markAppHydrated()
    delete window.__APP_HYDRATED
    markAppHydrated()

    expect(onHydrated).toHaveBeenCalledTimes(2)
    expect(setTimeoutSpy).toHaveBeenCalledTimes(1)
    vi.advanceTimersByTime(0)
    vi.advanceTimersByTime(BRAND_BOOT_LOADER_EXIT_TIMEOUT_MS)
    expect(loader).not.toBeInTheDocument()

    window.removeEventListener(APP_HYDRATED_EVENT, onHydrated)
  })

  it("keeps hydration evaluation safe during SSR without window", () => {
    vi.stubGlobal("window", undefined)

    try {
      expect(() => markAppHydrated()).not.toThrow()
    } finally {
      vi.unstubAllGlobals()
    }
  })

  it("does not publish or schedule anything when hydration is already complete", () => {
    const loader = appendLoader()
    window.__APP_HYDRATED = true
    const dispatchSpy = vi.spyOn(window, "dispatchEvent")
    const setTimeoutSpy = vi.spyOn(window, "setTimeout")

    markAppHydrated()

    expect(dispatchSpy).not.toHaveBeenCalled()
    expect(setTimeoutSpy).not.toHaveBeenCalled()
    expect(loader).toHaveAttribute("data-state", "active")
  })
})
