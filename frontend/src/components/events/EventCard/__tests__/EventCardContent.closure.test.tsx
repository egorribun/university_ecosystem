import { createElement } from "react"
import { render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

const { formatDateMock, useTranslationMock, translationMock } = vi.hoisted(() => {
  const translationMock = vi.fn((key: string) => key)
  return {
    formatDateMock: vi.fn((value: string) => `formatted:${value}`),
    useTranslationMock: vi.fn(() => ({ t: translationMock })),
    translationMock,
  }
})

vi.mock("react-i18next", () => ({
  useTranslation: useTranslationMock,
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
    return createElement(
      "a",
      { href: to ?? "#", "data-params": JSON.stringify(params), ...props },
      children as never
    )
  },
}))

vi.mock("@/utils/date", () => ({
  formatDate: formatDateMock,
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

    const title = screen.getByRole("link", { name: "Campus lecture" })
    expect(title).toHaveAttribute("href", "/events/$id")
    expect(title).toHaveAttribute("data-params", '{"id":"event-1"}')
    expect(title).toHaveAttribute("tabindex", "-1")
    expect(title).toHaveClass("before:absolute", "before:inset-0", "outline-none")
    expect(screen.getByRole("heading", { level: 3 })).toHaveAttribute("id", "event-title-event-1")
    expect(screen.getByText("Dr. Ada Lovelace")).toBeInTheDocument()
    expect(screen.getByText("Main hall")).toBeInTheDocument()
    expect(screen.getByText("A practical lecture")).toBeInTheDocument()
    expect(
      screen.getByText("formatted:2026-08-04T10:00:00.000Z — formatted:2026-08-04T12:00:00.000Z")
    ).toBeInTheDocument()
    expect(screen.getByText("events:card.statuses.open")).toBeInTheDocument()
    expect(
      screen.getByText("formatted:2026-08-04T10:00:00.000Z — formatted:2026-08-04T12:00:00.000Z")
        .parentElement
    ).toHaveClass("text-xs")
    expect(useTranslationMock).toHaveBeenCalledWith(["events"])
    expect(formatDateMock).toHaveBeenCalledWith(
      baseProps.startsAt,
      expect.objectContaining({
        day: "numeric",
        month: "short",
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
      })
    )
    expect(translationMock).toHaveBeenCalledWith("events:card.statuses.open")
  })

  it("renders registered and ended states with optional metadata omitted", () => {
    const { container, rerender } = render(
      <EventCardContent {...baseProps} isRegistered hoveringDisabled />
    )

    expect(screen.getByText("events:card.statuses.registered")).toBeInTheDocument()
    expect(screen.queryByText("Dr. Ada Lovelace")).not.toBeInTheDocument()
    expect(container.querySelectorAll("svg")).toHaveLength(2)
    expect(container.querySelector(".events-card-preview")).not.toBeInTheDocument()

    rerender(<EventCardContent {...baseProps} isEnded hoveringDisabled />)
    expect(screen.getByText("events:card.statuses.ended")).toBeInTheDocument()
    expect(screen.getByRole("link", { name: "Campus lecture" })).not.toHaveClass(
      "group-hover:text-brand"
    )
    expect(screen.getByText("events:card.statuses.ended")).toHaveClass("text-(--text-secondary)")
  })

  it("keeps the hover affordance enabled when editing is not active", () => {
    render(<EventCardContent {...baseProps} hoveringDisabled={false} />)

    expect(screen.getByRole("link", { name: "Campus lecture" })).toHaveClass(
      "group-hover:text-brand",
      "transition-colors",
      "duration-fast"
    )
  })

  it("renders no metadata rows for empty optional values and keeps date formatting exact", () => {
    const { container } = render(
      <EventCardContent {...baseProps} speaker="" endsAt={undefined} location="" description="" />
    )

    expect(container.querySelectorAll("svg")).toHaveLength(2)
    expect(container.querySelector(".events-card-preview")).not.toBeInTheDocument()
    expect(container.querySelector('[id="event-location-event-1"]')).not.toBeInTheDocument()
    expect(screen.getByText("formatted:2026-08-04T10:00:00.000Z")).toBeInTheDocument()
  })

  it.each([
    ["open", false, false, "text-brand"],
    ["registered", true, false, "text-success-text"],
    ["ended", false, true, "text-(--text-secondary)"],
  ] as const)(
    "uses the %s status branch with its semantic class",
    (_label, isRegistered, isEnded, className) => {
      render(<EventCardContent {...baseProps} isRegistered={isRegistered} isEnded={isEnded} />)

      const status = screen.getByText(`events:card.statuses.${_label}`)
      expect(status).toHaveClass(className)
    }
  )
})
