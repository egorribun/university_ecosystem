import type { MutableRefObject } from "react"
import { fireEvent, render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
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

interface MapFixture {
  container: HTMLDivElement
  map: {
    easeTo: ReturnType<typeof vi.fn>
    flyTo: ReturnType<typeof vi.fn>
    getContainer: ReturnType<typeof vi.fn>
    zoomIn: ReturnType<typeof vi.fn>
    zoomOut: ReturnType<typeof vi.fn>
  }
  ref: MutableRefObject<MapRef | null>
  requestFullscreen: ReturnType<typeof vi.fn>
}

function createMapFixture(): MapFixture {
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

afterEach(() => {
  vi.restoreAllMocks()
})

describe("MapControls mutation contracts", () => {
  it("exposes one labelled group with six keyboard-operable controls", () => {
    const { ref } = createMapFixture()
    render(<MapControls mapRef={ref} />)

    const group = screen.getByRole("group", { name: "zoom.ariaLabel" })
    const buttons = screen.getAllByRole("button")

    expect(group).toHaveAttribute("aria-label", "zoom.ariaLabel")
    expect(buttons).toHaveLength(6)
    expect(buttons.map((button) => button.getAttribute("aria-label"))).toEqual([
      "zoom.in",
      "zoom.out",
      "controls.compass",
      "controls.pitchToggle",
      "zoom.reset",
      "controls.fullscreen",
    ])
    for (const button of buttons) {
      expect(button).toHaveAttribute("type", "button")
      expect(button).toHaveStyle({ minWidth: "44px", minHeight: "44px" })
    }
  })

  it("starts in 3D mode and recentering restores the 3D affordance", async () => {
    const user = userEvent.setup()
    const { ref } = createMapFixture()
    render(<MapControls mapRef={ref} />)

    const pitchButton = screen.getByRole("button", { name: "controls.pitchToggle" })
    const recenterButton = screen.getByRole("button", { name: "zoom.reset" })

    expect(pitchButton.querySelector("svg")).toHaveClass("lucide-map")
    await user.click(pitchButton)
    expect(pitchButton.querySelector("svg")).toHaveClass("lucide-box")

    await user.click(recenterButton)
    expect(pitchButton.querySelector("svg")).toHaveClass("lucide-map")
  })

  it("rebinds every map action when the mapRef prop changes", async () => {
    const user = userEvent.setup()
    const first = createMapFixture()
    const second = createMapFixture()
    const { rerender } = render(<MapControls mapRef={first.ref} />)

    rerender(<MapControls mapRef={second.ref} />)
    await user.click(screen.getByRole("button", { name: "zoom.in" }))
    await user.click(screen.getByRole("button", { name: "zoom.out" }))
    await user.click(screen.getByRole("button", { name: "controls.compass" }))
    await user.click(screen.getByRole("button", { name: "controls.pitchToggle" }))
    await user.click(screen.getByRole("button", { name: "zoom.reset" }))
    await user.click(screen.getByRole("button", { name: "controls.fullscreen" }))

    expect(first.map.zoomIn).not.toHaveBeenCalled()
    expect(first.map.zoomOut).not.toHaveBeenCalled()
    expect(first.map.easeTo).not.toHaveBeenCalled()
    expect(first.map.flyTo).not.toHaveBeenCalled()
    expect(first.requestFullscreen).not.toHaveBeenCalled()

    expect(second.map.zoomIn).toHaveBeenCalledOnce()
    expect(second.map.zoomOut).toHaveBeenCalledOnce()
    expect(second.map.easeTo).toHaveBeenCalledWith({ bearing: 0, duration: 400 })
    expect(second.map.easeTo).toHaveBeenCalledWith({ pitch: 0, duration: 400 })
    expect(second.map.flyTo).toHaveBeenCalledWith(
      expect.objectContaining({ zoom: 17, pitch: 45, bearing: 0, duration: 800 })
    )
    expect(second.requestFullscreen).toHaveBeenCalledOnce()
  })

  it("reflects both fullscreen transitions and cleans up the listener", () => {
    const addEventListener = vi.spyOn(document, "addEventListener")
    const removeEventListener = vi.spyOn(document, "removeEventListener")
    const { container, ref } = createMapFixture()
    const { unmount } = render(<MapControls mapRef={ref} />)
    const fullscreenButton = screen.getByRole("button", { name: "controls.fullscreen" })

    expect(fullscreenButton.querySelector("svg")).toHaveClass("lucide-maximize-2")

    const registration = addEventListener.mock.calls.find(([type]) => type === "fullscreenchange")
    expect(registration).toBeDefined()
    const handler = registration![1]
    expect(handler).toEqual(expect.any(Function))

    Object.defineProperty(document, "fullscreenElement", {
      configurable: true,
      value: container,
    })
    fireEvent(document, new Event("fullscreenchange"))
    expect(fullscreenButton.querySelector("svg")).toHaveClass("lucide-minimize-2")

    Object.defineProperty(document, "fullscreenElement", {
      configurable: true,
      value: null,
    })
    fireEvent(document, new Event("fullscreenchange"))
    expect(fullscreenButton.querySelector("svg")).toHaveClass("lucide-maximize-2")

    unmount()
    expect(removeEventListener).toHaveBeenCalledWith("fullscreenchange", handler)
  })

  it("does not invoke fullscreen APIs when no live map can be resolved", async () => {
    const user = userEvent.setup()
    const nullRef = { current: null } as MutableRefObject<MapRef | null>
    const { unmount } = render(<MapControls mapRef={nullRef} />)
    await user.click(screen.getByRole("button", { name: "controls.fullscreen" }))
    unmount()

    const getMap = vi.fn(() => null)
    const unavailableRef = {
      current: { getMap },
    } as unknown as MutableRefObject<MapRef | null>
    render(<MapControls mapRef={unavailableRef} />)
    await user.click(screen.getByRole("button", { name: "controls.fullscreen" }))

    expect(getMap).toHaveBeenCalledOnce()
  })

  it("keeps fullscreen safe when the map container or matte is unavailable", async () => {
    const user = userEvent.setup()
    const noContainerMap = { getContainer: vi.fn(() => null) }
    const noContainerRef = {
      current: { getMap: vi.fn(() => noContainerMap) },
    } as unknown as MutableRefObject<MapRef | null>
    const { unmount } = render(<MapControls mapRef={noContainerRef} />)
    await user.click(screen.getByRole("button", { name: "controls.fullscreen" }))
    unmount()

    const outsideContainer = document.createElement("div")
    const outsideMap = { getContainer: vi.fn(() => outsideContainer) }
    const outsideRef = {
      current: { getMap: vi.fn(() => outsideMap) },
    } as unknown as MutableRefObject<MapRef | null>
    render(<MapControls mapRef={outsideRef} />)
    await user.click(screen.getByRole("button", { name: "controls.fullscreen" }))

    expect(noContainerMap.getContainer).toHaveBeenCalledOnce()
    expect(outsideMap.getContainer).toHaveBeenCalledOnce()
  })
})
