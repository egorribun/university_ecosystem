import type { MutableRefObject } from "react"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"
import type { MapRef } from "react-map-gl/maplibre"

const { mockLogError, mockUseMediaQuery } = vi.hoisted(() => ({
  mockLogError: vi.fn(),
  mockUseMediaQuery: vi.fn(() => false),
}))

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: "en", changeLanguage: () => Promise.resolve() },
  }),
}))
vi.mock("@/app/logger", () => ({ logError: mockLogError }))
vi.mock("@/hooks/useMediaQuery", () => ({ default: mockUseMediaQuery }))

import { MapControls } from "@/components/map/MapControls"

const createMapFixture = () => {
  const container = document.createElement("div")
  container.className = "map-card-matte"
  const requestFullscreen = vi.fn().mockResolvedValue(undefined)
  Object.defineProperty(container, "requestFullscreen", {
    configurable: true,
    value: requestFullscreen,
  })

  const map = {
    easeTo: vi.fn(),
    flyTo: vi.fn(),
    getContainer: vi.fn(() => container),
    zoomIn: vi.fn(),
    zoomOut: vi.fn(),
  }
  const ref = {
    current: { ...map, getMap: vi.fn(() => map) },
  } as unknown as MutableRefObject<MapRef | null>

  return { container, map, ref, requestFullscreen }
}

beforeEach(() => {
  mockLogError.mockReset()
  mockUseMediaQuery.mockReset()
  mockUseMediaQuery.mockReturnValue(false)
  Object.defineProperty(document, "fullscreenElement", {
    configurable: true,
    value: null,
  })
})

describe("MapControls closure", () => {
  it("delegates zoom, compass, pitch, and recenter actions to the live map", async () => {
    const user = userEvent.setup()
    const { map, ref } = createMapFixture()
    render(<MapControls mapRef={ref} />)

    await user.click(screen.getByRole("button", { name: "zoom.in" }))
    await user.click(screen.getByRole("button", { name: "zoom.out" }))
    await user.click(screen.getByRole("button", { name: "controls.compass" }))
    await user.click(screen.getByRole("button", { name: "controls.pitchToggle" }))
    await user.click(screen.getByRole("button", { name: "controls.pitchToggle" }))
    await user.click(screen.getByRole("button", { name: "zoom.reset" }))

    expect(map.zoomIn).toHaveBeenCalledOnce()
    expect(map.zoomOut).toHaveBeenCalledOnce()
    expect(map.easeTo).toHaveBeenNthCalledWith(1, { bearing: 0, duration: 400 })
    expect(map.easeTo).toHaveBeenNthCalledWith(2, { pitch: 0, duration: 400 })
    expect(map.easeTo).toHaveBeenNthCalledWith(3, { pitch: 45, duration: 400 })
    expect(map.flyTo).toHaveBeenCalledWith(
      expect.objectContaining({ zoom: 16, pitch: 45, bearing: 0, duration: 800 })
    )
  })

  it("uses the responsive icon-size presets", () => {
    mockUseMediaQuery.mockReturnValueOnce(true).mockReturnValueOnce(false)
    const { ref } = createMapFixture()
    const { rerender } = render(<MapControls mapRef={ref} />)
    expect(screen.getByRole("button", { name: "zoom.in" }).querySelector("svg")).toHaveAttribute(
      "width",
      "14"
    )

    mockUseMediaQuery.mockReturnValueOnce(false).mockReturnValueOnce(true)
    rerender(<MapControls mapRef={ref} />)
    expect(screen.getByRole("button", { name: "zoom.in" }).querySelector("svg")).toHaveAttribute(
      "width",
      "12"
    )
  })

  it("handles fullscreen enter/exit, syncs fullscreenchange, and logs promise failures", async () => {
    const user = userEvent.setup()
    const { container, ref, requestFullscreen } = createMapFixture()
    requestFullscreen.mockRejectedValueOnce(new Error("enter failed"))
    const exitFullscreen = vi.fn().mockRejectedValueOnce(new Error("exit failed"))
    Object.defineProperty(document, "exitFullscreen", {
      configurable: true,
      value: exitFullscreen,
    })
    render(<MapControls mapRef={ref} />)

    const fullscreenButton = screen.getByRole("button", { name: "controls.fullscreen" })
    await user.click(fullscreenButton)
    await Promise.resolve()
    expect(requestFullscreen).toHaveBeenCalledOnce()

    Object.defineProperty(document, "fullscreenElement", {
      configurable: true,
      value: container,
    })
    document.dispatchEvent(new Event("fullscreenchange"))
    await user.click(fullscreenButton)
    await Promise.resolve()

    expect(exitFullscreen).toHaveBeenCalledOnce()
    expect(mockLogError).toHaveBeenCalledTimes(2)
  })
})
