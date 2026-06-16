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

import { EventAboutEditor } from "@/components/events/EventAboutEditor"
import type { Event } from "@/types/Event"

const baseEvent: Event = {
  id: "evt-1",
  title: "React 19 Patterns Workshop",
  title_en: "React 19 Patterns Workshop",
  starts_at: "2026-06-15T14:00:00Z",
  ends_at: "2026-06-15T16:00:00Z",
  created_by: "admin-1",
  created_at: "2026-05-01T10:00:00Z",
  is_active: true,
  image_url_optimized: null,
  about: "Практический воркшоп по конкурентным возможностям React 19.",
  about_en: "A hands-on workshop on React 19 concurrent features.",
}

const baseProps = {
  event: baseEvent,
  language: "en" as const,
  canEdit: true,
  onUpdate: vi.fn(() => Promise.resolve()),
  onError: vi.fn(),
  onSuccess: vi.fn(),
}

describe("EventAboutEditor", () => {
  it("renders the heading and the language-aware about text", () => {
    render(<EventAboutEditor {...baseProps} />)
    expect(
      screen.getByRole("heading", { name: "events:detail.sections.about.title" })
    ).toBeInTheDocument()
    expect(
      screen.getByText("A hands-on workshop on React 19 concurrent features.")
    ).toBeInTheDocument()
  })

  it("renders the Russian about text for the ru language", () => {
    render(<EventAboutEditor {...baseProps} language="ru" />)
    expect(
      screen.getByText("Практический воркшоп по конкурентным возможностям React 19.")
    ).toBeInTheDocument()
  })

  it("renders the empty placeholder when there is no about text", () => {
    render(
      <EventAboutEditor
        {...baseProps}
        event={{ ...baseEvent, about: "", about_en: "" }}
        language="ru"
      />
    )
    expect(screen.getByText("events:detail.sections.about.empty")).toBeInTheDocument()
  })

  it("enters edit mode and reverts on cancel", async () => {
    const user = userEvent.setup()
    render(<EventAboutEditor {...baseProps} />)
    await user.click(screen.getByLabelText("events:detail.sections.about.editAria"))
    const textarea = screen.getByRole("textbox")
    expect(textarea).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "common:buttons.cancel" }))
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument()
  })

  it("does not show the edit affordance when canEdit is false", () => {
    render(<EventAboutEditor {...baseProps} canEdit={false} />)
    expect(screen.queryByLabelText("events:detail.sections.about.editAria")).not.toBeInTheDocument()
  })
})
