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
    const paths = [...loader.querySelectorAll('path[pathLength="1000"]')]
    expect(paths).toHaveLength(6)
    expect(paths.map((path) => path.getAttribute("d"))).toEqual([
      "M 432.53,279.03 A 102.77 102.77 0 0 0 356.91,313.10 L 184.73,504.69 A 20.43 20.43 0 0 0 215.20,532.06 L 384.10,343.81 A 68.71 68.71 0 0 1 434.70,320.99 L 813.00,318.00 A 46.0 46.0 0 0 1 823.00,405.00 L 458.17,405.16 A 23.73 23.73 0 0 0 440.53,413.02 L 358.13,504.69 A 22.39 22.39 0 0 0 374.96,542.05 L 761.598,539.011 A 2 2 0 0 0 763.069,538.349 L 870.501,419.037 A 85.7985 85.7985 0 0 0 806.844,276.072 Z",
      "M 260.0,528.7 L 392.6,373.0 Q 413.0,349.0 444.5,349.2 L 804.0,351.0",
      "M 312.9,515.8 L 409.8,400.1 Q 427.5,379.0 455.0,379.1 L 804.0,381.0",
      "M 432.53,279.03 A 102.77 102.77 0 0 0 356.91,313.10 L 184.73,504.69 A 20.43 20.43 0 0 0 215.20,532.06 L 384.10,343.81 A 68.71 68.71 0 0 1 434.70,320.99 L 813.00,318.00 A 46.0 46.0 0 0 1 823.00,405.00 L 458.17,405.16 A 23.73 23.73 0 0 0 440.53,413.02 L 358.13,504.69 A 22.39 22.39 0 0 0 374.96,542.05 L 761.598,539.011 A 2 2 0 0 0 763.069,538.349 L 870.501,419.037 A 85.7985 85.7985 0 0 0 806.844,276.072 Z",
      "M 260.0,528.7 L 392.6,373.0 Q 413.0,349.0 444.5,349.2 L 804.0,351.0",
      "M 312.9,515.8 L 409.8,400.1 Q 427.5,379.0 455.0,379.1 L 804.0,381.0",
    ])
    expect(loader.querySelector(".brand-boot-loader__red-group")).toHaveAttribute(
      "transform",
      "rotate(180 540.6 544.9)"
    )
  })

  it("starts one shared exit on the hydration event and unmounts on opacity transition", () => {
    render(<BrandBootLoader />)
    const loader = screen.getByRole("status", { name: "Загрузка" })

    fireEvent.transitionEnd(loader, { propertyName: "opacity" })
    expect(loader).toHaveAttribute("data-state", "active")

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
