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
    window.addEventListener(APP_HYDRATED_EVENT, onHydrated)

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

    window.removeEventListener(APP_HYDRATED_EVENT, onHydrated)
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
    window.addEventListener(APP_HYDRATED_EVENT, onHydrated)

    markAppHydrated()
    markAppHydrated()

    expect(onHydrated).toHaveBeenCalledOnce()
    vi.advanceTimersByTime(0)
    vi.advanceTimersByTime(BRAND_BOOT_LOADER_EXIT_TIMEOUT_MS)
    expect(loader).not.toBeInTheDocument()

    window.removeEventListener(APP_HYDRATED_EVENT, onHydrated)
  })
})
