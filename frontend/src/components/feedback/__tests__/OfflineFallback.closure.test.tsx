import { fireEvent, render, screen } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

const navigate = vi.hoisted(() => vi.fn())

vi.mock("framer-motion", async () =>
  (await import("@/tests/helpers/framerMotionMock")).framerMotionMock()
)
vi.mock("@tanstack/react-router", () => ({ useNavigate: () => navigate }))
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

import OfflineFallback from "@/components/feedback/OfflineFallback"

describe("OfflineFallback closure paths", () => {
  let originalLocation: Location

  beforeEach(() => {
    originalLocation = window.location
    const location = Object.create(originalLocation) as Location
    Object.defineProperty(location, "reload", { value: vi.fn(), configurable: true })
    Object.defineProperty(window, "location", { value: location, configurable: true })
    navigate.mockReset()
  })

  afterEach(() => {
    Object.defineProperty(window, "location", {
      value: originalLocation,
      configurable: true,
    })
  })

  it("reloads by default and can navigate back home", () => {
    render(<OfflineFallback />)

    fireEvent.click(screen.getByRole("button", { name: "offlineFallback.retry" }))
    expect(window.location.reload).toHaveBeenCalledOnce()

    fireEvent.click(screen.getByRole("button", { name: "offlineFallback.backHome" }))
    expect(navigate).toHaveBeenCalledWith({ to: "/" })
  })
})
