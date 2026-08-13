import { StrictMode } from "react"
import { act, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { APP_HYDRATED_EVENT } from "@/app/hydration"
import { BRAND_BOOT_LOADER_EXIT_TIMEOUT_MS, BrandBootLoader } from "../BrandBootLoader"

describe("BrandBootLoader", () => {
  let hidden = false

  beforeEach(() => {
    vi.useFakeTimers()
    delete window.__APP_HYDRATED
    hidden = false
    vi.spyOn(document, "hidden", "get").mockImplementation(() => hidden)
  })

  afterEach(() => {
    vi.restoreAllMocks()
    vi.useRealTimers()
  })

  it("renders one accessible persistent status and decorative mark", () => {
    render(<BrandBootLoader />)

    const loader = screen.getByRole("status", { name: "Загрузка" })
    expect(loader).toHaveAttribute("data-state", "active")
    expect(loader).toHaveAttribute("aria-live", "polite")
    expect(loader).toHaveAttribute("aria-atomic", "true")
    expect(loader).toHaveAttribute("aria-busy", "true")
    expect(screen.getByText("Загрузка")).toBeVisible()
    expect(loader.querySelector("svg")).toHaveAttribute("aria-hidden", "true")
    expect(loader.querySelector(".brand-boot-loader__dots")).toHaveAttribute("aria-hidden", "true")
    expect(loader.querySelectorAll('path[pathLength="1000"]')).toHaveLength(6)
  })

  it("starts one shared exit on the hydration event and unmounts on opacity transition", () => {
    render(<BrandBootLoader />)
    const loader = screen.getByRole("status", { name: "Загрузка" })

    act(() => window.dispatchEvent(new Event(APP_HYDRATED_EVENT)))
    expect(loader).toHaveAttribute("data-state", "exiting")
    expect(loader).toHaveAttribute("aria-busy", "false")

    fireEvent.transitionEnd(loader, { propertyName: "opacity" })
    expect(screen.queryByRole("status", { name: "Загрузка" })).not.toBeInTheDocument()
  })

  it("uses the timeout fallback when transitionend is unavailable", () => {
    render(<BrandBootLoader />)
    act(() => window.dispatchEvent(new Event(APP_HYDRATED_EVENT)))

    act(() => vi.advanceTimersByTime(BRAND_BOOT_LOADER_EXIT_TIMEOUT_MS))
    expect(screen.queryByRole("status", { name: "Загрузка" })).not.toBeInTheDocument()
  })

  it("does not miss hydration that completed before its effect subscribed", () => {
    window.__APP_HYDRATED = true
    render(<BrandBootLoader />)

    expect(screen.getByRole("status", { name: "Загрузка" })).toHaveAttribute(
      "data-state",
      "exiting"
    )
  })

  it("remains idempotent under StrictMode and duplicate completion events", () => {
    render(
      <StrictMode>
        <BrandBootLoader />
      </StrictMode>
    )

    act(() => {
      window.dispatchEvent(new Event(APP_HYDRATED_EVENT))
      window.dispatchEvent(new Event(APP_HYDRATED_EVENT))
    })

    expect(screen.getByRole("status", { name: "Загрузка" })).toHaveAttribute(
      "data-state",
      "exiting"
    )

    act(() => {
      vi.advanceTimersByTime(BRAND_BOOT_LOADER_EXIT_TIMEOUT_MS)
    })

    expect(screen.queryByRole("status", { name: "Загрузка" })).not.toBeInTheDocument()
  })

  it("pauses and resumes the logo timeline with document visibility", () => {
    render(<BrandBootLoader />)
    const loader = screen.getByRole("status", { name: "Загрузка" })

    hidden = true
    act(() => document.dispatchEvent(new Event("visibilitychange")))
    expect(loader).toHaveAttribute("data-paused", "true")

    hidden = false
    act(() => document.dispatchEvent(new Event("visibilitychange")))
    expect(loader).not.toHaveAttribute("data-paused")
  })
})
