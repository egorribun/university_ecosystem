import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, it, expect, vi } from "vitest"

const { mockPatch, mockLogError } = vi.hoisted(() => ({
  mockPatch: vi.fn(),
  mockLogError: vi.fn(),
}))

vi.mock("@/api/client", () => ({
  default: { patch: mockPatch },
  resetEtagCache: vi.fn(),
}))
vi.mock("@/app/logger", () => ({
  logError: mockLogError,
}))

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
  beforeEach(() => {
    mockPatch.mockReset()
    mockLogError.mockReset()
  })

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

  it("saves trimmed English text and refreshes the event", async () => {
    const user = userEvent.setup()
    const onUpdate = vi.fn(() => Promise.resolve())
    const onSuccess = vi.fn()
    mockPatch.mockResolvedValue({ status: 200 })
    render(<EventAboutEditor {...baseProps} onUpdate={onUpdate} onSuccess={onSuccess} />)

    await user.click(screen.getByLabelText("events:detail.sections.about.editAria"))
    const textarea = screen.getByRole("textbox")
    await user.clear(textarea)
    await user.type(textarea, "  Updated English text  ")
    await user.click(screen.getByRole("button", { name: "common:buttons.save" }))

    expect(mockPatch).toHaveBeenCalledWith("/events/evt-1", { about_en: "Updated English text" })
    expect(onSuccess).toHaveBeenCalledWith("events:detail.messages.aboutUpdated")
    expect(onUpdate).toHaveBeenCalledTimes(1)
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument()
  })

  it("uses the Russian payload and reports save failures", async () => {
    const user = userEvent.setup()
    const onError = vi.fn()
    const failure = new Error("request failed")
    mockPatch.mockRejectedValueOnce(failure)
    render(<EventAboutEditor {...baseProps} language="ru" onError={onError} />)

    await user.click(screen.getByLabelText("events:detail.sections.about.editAria"))
    const textarea = screen.getByRole("textbox")
    expect(textarea).toHaveAttribute("placeholder", "events:detail.sections.about.fieldLabel")
    await user.clear(textarea)
    await user.type(textarea, " Новое описание ")
    await user.click(screen.getByRole("button", { name: "common:buttons.save" }))

    expect(mockPatch).toHaveBeenCalledWith("/events/evt-1", { about: "Новое описание" })
    expect(mockLogError).toHaveBeenCalledWith("[EventAboutEditor] Save failed:", failure)
    expect(onError).toHaveBeenCalledWith("events:detail.messages.aboutUpdateFailed")
  })
})
