import { createElement } from "react"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, it, expect, vi } from "vitest"

const mocks = vi.hoisted(() => ({
  language: "en",
  popupOnClose: undefined as (() => void) | undefined,
  logError: vi.fn(),
}))

vi.mock("react-map-gl/maplibre", async () => {
  const { createElement } = await import("react")
  const base = (await import("@/tests/helpers/mapGlMock")).mapGlMock()
  return {
    ...base,
    Popup: ({ children, onClose }: { children?: unknown; onClose?: () => void }) => {
      mocks.popupOnClose = onClose
      return createElement("div", null, children as never)
    },
  }
})
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: mocks.language, changeLanguage: () => Promise.resolve() },
  }),
}))
vi.mock("@/app/logger", () => ({ logError: mocks.logError }))
vi.mock("@tanstack/react-router", () => ({
  Link: ({
    children,
    to,
    params: _params,
    ...rest
  }: { children?: unknown; to?: unknown; params?: unknown } & Record<string, unknown>) =>
    createElement("a", { href: typeof to === "string" ? to : "#", ...rest }, children as never),
}))

import { EventMarker } from "@/components/map/EventMarker"
import type { MapEvent } from "@/hooks/useMapEvents"

const EVENT = {
  id: "e1",
  title: "Hackathon 2026",
  startsAt: "2026-06-15T18:00:00Z",
  location: "ГУК-305",
  geoCoords: [55.71, 37.81],
  participantCount: 12,
} as unknown as MapEvent

const baseProps = { event: EVENT }

describe("EventMarker", () => {
  beforeEach(() => {
    mocks.language = "en"
    mocks.popupOnClose = undefined
    mocks.logError.mockReset()
  })

  it("renders the event pin with an accessible label", () => {
    render(<EventMarker {...baseProps} />)
    expect(screen.getByRole("button", { name: "events.markerLabel" })).toBeInTheDocument()
  })

  it("fires onPopupOpen when the pin is clicked", async () => {
    const user = userEvent.setup()
    const onPopupOpen = vi.fn()
    render(<EventMarker {...baseProps} onPopupOpen={onPopupOpen} />)
    await user.click(screen.getByRole("button", { name: "events.markerLabel" }))
    expect(onPopupOpen).toHaveBeenCalledOnce()
  })

  it.each(["Enter", " "])("opens the popup from the %j keyboard key", async (key) => {
    const user = userEvent.setup()
    const onPopupOpen = vi.fn()
    render(<EventMarker {...baseProps} onPopupOpen={onPopupOpen} />)

    const marker = screen.getByRole("button", { name: "events.markerLabel" })
    marker.focus()
    await user.keyboard(key === " " ? "[Space]" : `{${key}}`)

    expect(onPopupOpen).toHaveBeenCalledOnce()
  })

  it("ignores unrelated keyboard keys", async () => {
    const user = userEvent.setup()
    const onPopupOpen = vi.fn()
    render(<EventMarker {...baseProps} onPopupOpen={onPopupOpen} />)

    screen.getByRole("button", { name: "events.markerLabel" }).focus()
    await user.keyboard("a")
    expect(onPopupOpen).not.toHaveBeenCalled()
  })

  it("renders the popup with the event title and a details link when open", () => {
    render(<EventMarker {...baseProps} isPopupOpen />)
    expect(screen.getByText("Hackathon 2026")).toBeInTheDocument()
    expect(screen.getByRole("link", { name: /events\.viewDetails/ })).toBeInTheDocument()
  })

  it("forwards popup closure to the owner", () => {
    const onPopupClose = vi.fn()
    render(<EventMarker {...baseProps} isPopupOpen onPopupClose={onPopupClose} />)

    mocks.popupOnClose?.()
    expect(onPopupClose).toHaveBeenCalledOnce()
  })

  it("falls back to the source timestamp when date formatting fails", () => {
    mocks.language = "not_a_locale"
    render(<EventMarker {...baseProps} />)

    expect(mocks.logError).toHaveBeenCalledOnce()
  })
})
