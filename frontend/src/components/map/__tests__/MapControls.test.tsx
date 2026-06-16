import type { MutableRefObject } from "react"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, it, expect, vi } from "vitest"

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: "en", changeLanguage: () => Promise.resolve() },
  }),
}))
vi.mock("@/hooks/useMediaQuery", () => ({ default: () => false }))

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

  it("toggles pitch, recenter, and fullscreen without crashing on a null map", async () => {
    const user = userEvent.setup()
    render(<MapControls mapRef={nullMapRef} />)
    await user.click(screen.getByRole("button", { name: "controls.pitchToggle" }))
    await user.click(screen.getByRole("button", { name: "zoom.reset" }))
    await user.click(screen.getByRole("button", { name: "controls.fullscreen" }))
    expect(screen.getByRole("button", { name: "controls.pitchToggle" })).toBeInTheDocument()
  })
})
