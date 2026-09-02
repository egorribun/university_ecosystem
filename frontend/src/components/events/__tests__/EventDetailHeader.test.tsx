import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, it, expect, vi } from "vitest"

vi.mock("framer-motion", async () =>
  (await import("@/tests/helpers/framerMotionMock")).framerMotionMock()
)

const { useTranslationMock, translationMock } = vi.hoisted(() => {
  const translationMock = vi.fn((key: string) => key)
  return {
    useTranslationMock: vi.fn(() => ({
      t: translationMock,
      i18n: { language: "en", changeLanguage: () => Promise.resolve() },
    })),
    translationMock,
  }
})

const { formatDateMock } = vi.hoisted(() => ({
  formatDateMock: vi.fn((value: string) => `formatted:${value}`),
}))

vi.mock("react-i18next", () => ({
  useTranslation: useTranslationMock,
}))

vi.mock("@/utils/date", () => ({
  formatDate: formatDateMock,
}))

import { EventDetailHeader } from "@/components/events/EventDetailHeader"

const baseProps = {
  title: "AI Research Symposium 2026",
  eventType: "conference",
  participantCount: 248,
  startsAt: "2026-06-15T14:00:00Z",
  endsAt: "2026-06-15T18:00:00Z",
  location: "Main Auditorium",
  speaker: "Prof. A. Ivanova",
  isRegistered: false,
  isEnded: false,
  isAdmin: false,
  registering: false,
  onShare: vi.fn(),
  onRegister: vi.fn(),
  onUnregister: vi.fn(),
  onEditOpen: vi.fn(),
  onDeleteOpen: vi.fn(),
}

describe("EventDetailHeader", () => {
  it("renders title, meta pills, share and register actions", () => {
    const { container } = render(<EventDetailHeader {...baseProps} />)
    expect(screen.getByRole("heading", { level: 1, name: baseProps.title })).toBeInTheDocument()
    expect(screen.getByText("events:card.participants")).toBeInTheDocument()
    expect(screen.getByText("Main Auditorium")).toBeInTheDocument()
    expect(screen.getByText("Prof. A. Ivanova")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "events:detail.actions.share" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "events:card.actions.register" })).toBeInTheDocument()
    const date = container.querySelector("time")
    expect(date).toHaveAttribute("dateTime", "2026-06-15T14:00:00.000Z")
    expect(date).toHaveTextContent(
      "formatted:2026-06-15T14:00:00Z — formatted:2026-06-15T18:00:00Z"
    )
    expect(formatDateMock).toHaveBeenCalledWith(
      baseProps.startsAt,
      expect.objectContaining({
        day: "numeric",
        month: "short",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
      })
    )
    expect(screen.getByRole("button", { name: "events:detail.actions.share" })).toHaveAttribute(
      "aria-label",
      "events:detail.actions.share"
    )
    expect(useTranslationMock).toHaveBeenCalledWith(["events", "common"])
    expect(translationMock).toHaveBeenCalledWith("events:card.participants", { count: 248 })
  })

  it("shows unregister when the user is registered", () => {
    render(<EventDetailHeader {...baseProps} isRegistered />)
    expect(
      screen.getByRole("button", { name: "events:card.actions.unregister" })
    ).toBeInTheDocument()
    expect(
      screen.queryByRole("button", { name: "events:card.actions.register" })
    ).not.toBeInTheDocument()
  })

  it("disables the register action while registration is pending", () => {
    render(<EventDetailHeader {...baseProps} registering />)
    expect(screen.getByRole("button", { name: "events:card.actions.register" })).toBeDisabled()
  })

  it("hides register/unregister and shows admin actions for admins", () => {
    render(<EventDetailHeader {...baseProps} isAdmin />)
    expect(
      screen.queryByRole("button", { name: "events:card.actions.register" })
    ).not.toBeInTheDocument()
    expect(screen.getByRole("button", { name: "common:buttons.edit" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "common:buttons.delete" })).toBeInTheDocument()
  })

  it("fires share and register callbacks", async () => {
    const user = userEvent.setup()
    const onShare = vi.fn()
    const onRegister = vi.fn()
    render(<EventDetailHeader {...baseProps} onShare={onShare} onRegister={onRegister} />)
    await user.click(screen.getByRole("button", { name: "events:detail.actions.share" }))
    await user.click(screen.getByRole("button", { name: "events:card.actions.register" }))
    expect(onShare).toHaveBeenCalledOnce()
    expect(onRegister).toHaveBeenCalledOnce()
  })

  it("fires unregister and admin edit/delete callbacks and disables registration while pending", async () => {
    const user = userEvent.setup()
    const onUnregister = vi.fn()
    const onEditOpen = vi.fn()
    const onDeleteOpen = vi.fn()
    const { rerender } = render(
      <EventDetailHeader
        {...baseProps}
        isRegistered
        onUnregister={onUnregister}
        onEditOpen={onEditOpen}
        onDeleteOpen={onDeleteOpen}
      />
    )

    await user.click(screen.getByRole("button", { name: "events:card.actions.unregister" }))
    expect(onUnregister).toHaveBeenCalledOnce()

    rerender(
      <EventDetailHeader
        {...baseProps}
        isAdmin
        registering
        onEditOpen={onEditOpen}
        onDeleteOpen={onDeleteOpen}
      />
    )
    await user.click(screen.getByRole("button", { name: "common:buttons.edit" }))
    await user.click(screen.getByRole("button", { name: "common:buttons.delete" }))
    expect(onEditOpen).toHaveBeenCalledOnce()
    expect(onDeleteOpen).toHaveBeenCalledOnce()
    expect(
      screen.queryByRole("button", { name: "events:card.actions.register" })
    ).not.toBeInTheDocument()
  })

  it("uses the English category fallback and ended status when optional dates are absent", () => {
    render(
      <EventDetailHeader
        {...baseProps}
        eventType={undefined}
        eventTypeEn="lecture"
        endsAt={undefined}
        isRegistered={false}
        isEnded
      />
    )

    expect(screen.getByText("events:categories.lecture")).toBeInTheDocument()
    expect(
      screen.queryByRole("button", { name: "events:card.actions.register" })
    ).not.toBeInTheDocument()
    expect(screen.getByText("events:card.statuses.ended")).toBeInTheDocument()
  })

  it("omits optional metadata and registration for ended events", () => {
    render(
      <EventDetailHeader
        {...baseProps}
        startsAt={undefined}
        endsAt={undefined}
        location={undefined}
        speaker={undefined}
        isEnded
      />
    )

    expect(screen.queryByText("Main Auditorium")).not.toBeInTheDocument()
    expect(screen.queryByText("Prof. A. Ivanova")).not.toBeInTheDocument()
    expect(
      screen.queryByRole("button", { name: "events:card.actions.register" })
    ).not.toBeInTheDocument()
    expect(screen.getByText("events:card.statuses.ended")).toBeInTheDocument()
  })

  it("does not create empty metadata chips when optional values are absent", () => {
    const { container } = render(
      <EventDetailHeader
        {...baseProps}
        startsAt={undefined}
        endsAt={undefined}
        location={undefined}
        speaker={undefined}
        isEnded
      />
    )

    expect(container.querySelectorAll(".matte-chip")).toHaveLength(1)
  })

  it("keeps the end separator out when no end time is supplied", () => {
    const { container } = render(<EventDetailHeader {...baseProps} endsAt={undefined} />)

    expect(container.querySelector("time")).toHaveTextContent("formatted:2026-06-15T14:00:00Z")
    expect(container.querySelector("time")).not.toHaveTextContent(" — ")
  })

  it("announces a registered status before the ended status in the live region", () => {
    render(<EventDetailHeader {...baseProps} isRegistered isEnded />)
    const liveRegion = document.querySelector('[aria-live="polite"]')
    expect(liveRegion).toHaveTextContent("events:card.statuses.registered")
    expect(liveRegion).not.toHaveTextContent("events:card.statuses.ended")
  })

  it("keeps the registration live region empty for an open anonymous event", () => {
    render(<EventDetailHeader {...baseProps} />)

    expect(document.querySelector('[aria-live="polite"]')).toHaveTextContent("")
  })
})
