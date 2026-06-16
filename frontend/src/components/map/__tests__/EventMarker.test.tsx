import { createElement } from "react"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, it, expect, vi } from "vitest"

vi.mock("react-map-gl/maplibre", async () =>
  (await import("@/tests/helpers/mapGlMock")).mapGlMock()
)
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: "en", changeLanguage: () => Promise.resolve() },
  }),
}))
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

  it("renders the popup with the event title and a details link when open", () => {
    render(<EventMarker {...baseProps} isPopupOpen />)
    expect(screen.getByText("Hackathon 2026")).toBeInTheDocument()
    expect(screen.getByRole("link", { name: /events\.viewDetails/ })).toBeInTheDocument()
  })
})
