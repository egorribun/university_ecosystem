import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, it, expect, vi } from "vitest"

vi.mock("framer-motion", async () =>
  (await import("@/tests/helpers/framerMotionMock")).framerMotionMock()
)
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: "en", changeLanguage: () => Promise.resolve() },
  }),
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
    render(<EventDetailHeader {...baseProps} />)
    expect(screen.getByRole("heading", { level: 1, name: baseProps.title })).toBeInTheDocument()
    expect(screen.getByText("events:card.participants")).toBeInTheDocument()
    expect(screen.getByText("Main Auditorium")).toBeInTheDocument()
    expect(screen.getByText("Prof. A. Ivanova")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "events:detail.actions.share" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "events:card.actions.register" })).toBeInTheDocument()
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
    expect(screen.queryByRole("button", { name: "events:card.actions.register" })).not.toBeInTheDocument()
    expect(screen.getByText("events:card.statuses.ended")).toBeInTheDocument()
  })
})
