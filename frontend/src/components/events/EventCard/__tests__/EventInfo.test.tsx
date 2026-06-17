import { render, screen } from "@testing-library/react"
import { describe, it, expect, vi } from "vitest"

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: "en", changeLanguage: () => Promise.resolve() },
  }),
}))

import { EventInfo } from "@/components/events/EventCard/EventInfo"

const baseProps = {
  title: "Annual Tech Conference",
  startsAt: "2026-06-01T10:00:00Z",
  endsAt: "2026-06-01T18:00:00Z",
  location: "Main Auditorium",
  description: "A full-day conference covering the latest technology trends.",
}

describe("EventInfo", () => {
  it("renders title, location and description", () => {
    render(<EventInfo {...baseProps} />)
    expect(screen.getByRole("heading", { name: "Annual Tech Conference" })).toBeInTheDocument()
    expect(screen.getByText("Main Auditorium")).toBeInTheDocument()
    expect(
      screen.getByText("A full-day conference covering the latest technology trends.")
    ).toBeInTheDocument()
  })

  it("applies the titleId to the heading when provided", () => {
    render(<EventInfo {...baseProps} titleId="event-heading-1" />)
    expect(screen.getByRole("heading", { name: "Annual Tech Conference" })).toHaveAttribute(
      "id",
      "event-heading-1"
    )
  })

  it("renders the speaker line when speaker is provided", () => {
    render(<EventInfo {...baseProps} speaker="Dr. Jane Doe" />)
    expect(screen.getByText("events:form.speaker: Dr. Jane Doe")).toBeInTheDocument()
  })

  it("omits the speaker line when speaker is absent", () => {
    render(<EventInfo {...baseProps} />)
    expect(screen.queryByText(/events:form\.speaker/)).not.toBeInTheDocument()
  })

  it("renders the date and location tooltip labels via i18n keys", () => {
    const { container } = render(<EventInfo {...baseProps} />)
    expect(container.querySelector('[title="events:form.dates"]')).toBeInTheDocument()
    expect(container.querySelector('[title="events:form.location"]')).toBeInTheDocument()
    expect(container.querySelector('[data-tooltip="events:form.dates"]')).toBeInTheDocument()
    expect(container.querySelector('[data-tooltip="events:form.location"]')).toBeInTheDocument()
  })

  it("renders both start and end timestamps as <time> elements", () => {
    const { container } = render(<EventInfo {...baseProps} />)
    expect(container.querySelector('time[datetime="2026-06-01T10:00:00Z"]')).toBeInTheDocument()
    expect(container.querySelector('time[datetime="2026-06-01T18:00:00Z"]')).toBeInTheDocument()
  })
})
