import { createElement } from "react"
import { render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}))

vi.mock("@tanstack/react-router", () => ({
  Link: ({
    children,
    to,
    params,
    ...props
  }: {
    children?: unknown
    to?: string
    params?: unknown
    [key: string]: unknown
  }) => {
    void params
    return createElement("a", { href: to ?? "#", ...props }, children as never)
  },
}))

vi.mock("@/utils/date", () => ({
  formatDate: (value: string) => `formatted:${value}`,
}))

import EventCardContent from "@/components/events/EventCard/EventCardContent"

const baseProps = {
  id: "event-1",
  title: "Campus lecture",
  startsAt: "2026-08-04T10:00:00.000Z",
  participantCount: 12,
  isRegistered: false,
  isEnded: false,
}

describe("EventCardContent closure", () => {
  it("renders all optional event metadata and the open status", () => {
    render(
      <EventCardContent
        {...baseProps}
        speaker="Dr. Ada Lovelace"
        endsAt="2026-08-04T12:00:00.000Z"
        location="Main hall"
        description="A practical lecture"
      />
    )

    expect(screen.getByRole("link", { name: "Campus lecture" })).toHaveAttribute(
      "href",
      "/events/$id"
    )
    expect(screen.getByText("Dr. Ada Lovelace")).toBeInTheDocument()
    expect(screen.getByText("Main hall")).toBeInTheDocument()
    expect(screen.getByText("A practical lecture")).toBeInTheDocument()
    expect(
      screen.getByText("formatted:2026-08-04T10:00:00.000Z — formatted:2026-08-04T12:00:00.000Z")
    ).toBeInTheDocument()
    expect(screen.getByText("events:card.statuses.open")).toBeInTheDocument()
  })

  it("renders registered and ended states with optional metadata omitted", () => {
    const { rerender } = render(<EventCardContent {...baseProps} isRegistered hoveringDisabled />)

    expect(screen.getByText("events:card.statuses.registered")).toBeInTheDocument()
    expect(screen.queryByText("Dr. Ada Lovelace")).not.toBeInTheDocument()

    rerender(<EventCardContent {...baseProps} isEnded hoveringDisabled />)
    expect(screen.getByText("events:card.statuses.ended")).toBeInTheDocument()
    expect(screen.getByRole("link", { name: "Campus lecture" })).not.toHaveClass(
      "group-hover:text-brand"
    )
  })
})
