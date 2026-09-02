import type { MutableRefObject } from "react"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, it, expect, vi } from "vitest"

const { mockUseTranslation, mockUseMediaQuery } = vi.hoisted(() => ({
  mockUseTranslation: vi.fn(() => ({
    t: (key: string) => key,
    i18n: { language: "en", changeLanguage: () => Promise.resolve() },
  })),
  mockUseMediaQuery: vi.fn(() => false),
}))

vi.mock("react-i18next", () => ({
  useTranslation: mockUseTranslation,
}))
vi.mock("@/hooks/useMediaQuery", () => ({ default: mockUseMediaQuery }))

import { MapControls } from "@/components/map/MapControls"
import type { MapRef } from "react-map-gl/maplibre"

const nullMapRef = { current: null } as MutableRefObject<MapRef | null>

describe("MapControls", () => {
  it("renders the full control panel of buttons", () => {
    render(<MapControls mapRef={nullMapRef} />)
    expect(screen.getByRole("group", { name: "zoom.ariaLabel" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "zoom.in" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "zoom.out" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "controls.compass" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "controls.pitchToggle" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "zoom.reset" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "controls.fullscreen" })).toBeInTheDocument()
  })

  it("handles zoom clicks without a live map (null-safe)", async () => {
    const user = userEvent.setup()
    render(<MapControls mapRef={nullMapRef} />)
    await user.click(screen.getByRole("button", { name: "zoom.in" }))
    await user.click(screen.getByRole("button", { name: "zoom.out" }))
    expect(screen.getByRole("button", { name: "zoom.in" })).toBeInTheDocument()
  })

  it("keeps every map action safe when the map instance is unavailable", async () => {
    const user = userEvent.setup()
    const ref = {
      current: { getMap: vi.fn(() => null) },
    } as unknown as MutableRefObject<MapRef | null>
    render(<MapControls mapRef={ref} />)

    await user.click(screen.getByRole("button", { name: "zoom.in" }))
    await user.click(screen.getByRole("button", { name: "zoom.out" }))
    await user.click(screen.getByRole("button", { name: "controls.compass" }))
    await user.click(screen.getByRole("button", { name: "controls.pitchToggle" }))
    await user.click(screen.getByRole("button", { name: "zoom.reset" }))

    expect(ref.current?.getMap).toHaveBeenCalledTimes(5)
  })

  it("uses the map namespace and responsive media-query contracts", () => {
    mockUseTranslation.mockClear()
    mockUseMediaQuery.mockClear()
    render(<MapControls mapRef={nullMapRef} />)

    expect(mockUseTranslation).toHaveBeenCalledWith("map")
    expect(mockUseMediaQuery).toHaveBeenNthCalledWith(1, "(max-width: 640px)")
    expect(mockUseMediaQuery).toHaveBeenNthCalledWith(2, "(max-width: 380px), (max-height: 500px)")
  })

  it("toggles pitch, recenter, and fullscreen without crashing on a null map", async () => {
    const user = userEvent.setup()
    render(<MapControls mapRef={nullMapRef} />)
    await user.click(screen.getByRole("button", { name: "controls.pitchToggle" }))
    await user.click(screen.getByRole("button", { name: "zoom.reset" }))
    await user.click(screen.getByRole("button", { name: "controls.fullscreen" }))
    expect(screen.getByRole("button", { name: "controls.pitchToggle" })).toBeInTheDocument()
  })
})
