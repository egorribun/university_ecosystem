import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, it, expect, vi } from "vitest"

const { mockPatch, mockLogError, mockUseTranslation, mockTranslate } = vi.hoisted(() => ({
  mockPatch: vi.fn(),
  mockLogError: vi.fn(),
  mockTranslate: vi.fn((key: string) => key),
  mockUseTranslation: vi.fn(() => ({
    t: (key: string) => mockTranslate(key),
    i18n: { language: "en", changeLanguage: () => Promise.resolve() },
  })),
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
  useTranslation: mockUseTranslation,
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
    mockUseTranslation.mockClear()
    mockTranslate.mockClear()
  })

  it("renders the heading and the language-aware about text", () => {
    render(<EventAboutEditor {...baseProps} />)
    expect(
      screen.getByRole("heading", { name: "events:detail.sections.about.title" })
    ).toBeInTheDocument()
    expect(
      screen.getByText("A hands-on workshop on React 19 concurrent features.")
    ).toBeInTheDocument()
    expect(mockUseTranslation).toHaveBeenCalledWith(["events", "common"])
  })

  it("renders the Russian about text for the ru language", () => {
    render(<EventAboutEditor {...baseProps} language="ru" />)
    expect(
      screen.getByText("Практический воркшоп по конкурентным возможностям React 19.")
    ).toBeInTheDocument()
  })

  it("refreshes the localized baseline when the language changes", async () => {
    const user = userEvent.setup()
    const { rerender } = render(<EventAboutEditor {...baseProps} />)

    expect(
      screen.getByText("A hands-on workshop on React 19 concurrent features.")
    ).toBeInTheDocument()

    rerender(<EventAboutEditor {...baseProps} language="ru" />)
    expect(
      screen.getByText("Практический воркшоп по конкурентным возможностям React 19.")
    ).toBeInTheDocument()

    await user.click(screen.getByLabelText("events:detail.sections.about.editAria"))
    expect(screen.getByRole("textbox")).toHaveValue(
      "Практический воркшоп по конкурентным возможностям React 19."
    )
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
    expect(screen.getByText("events:detail.sections.about.empty")).toHaveClass(
      "text-(--text-secondary)"
    )
  })

  it("uses the primary text style for a populated about section", () => {
    const { rerender } = render(<EventAboutEditor {...baseProps} />)

    expect(screen.getByText("A hands-on workshop on React 19 concurrent features.")).toHaveClass(
      "text-text-primary"
    )

    rerender(
      <EventAboutEditor
        {...baseProps}
        event={{ ...baseEvent, about: "", about_en: "" }}
        language="ru"
      />
    )
    expect(screen.getByText("events:detail.sections.about.empty")).toHaveAttribute(
      "class",
      expect.stringContaining("text-(--text-secondary)")
    )
  })

  it.each([
    ["en", { ...baseEvent, about_en: null }],
    ["ru", { ...baseEvent, about: null }],
  ] as const)("treats a null %s about value as empty", (language, event) => {
    render(<EventAboutEditor {...baseProps} event={event} language={language} />)

    expect(screen.getByText("events:detail.sections.about.empty")).toBeInTheDocument()
  })

  it("enters edit mode and reverts on cancel", async () => {
    const user = userEvent.setup()
    render(<EventAboutEditor {...baseProps} />)
    await user.click(screen.getByLabelText("events:detail.sections.about.editAria"))
    const textarea = screen.getByRole("textbox")
    expect(textarea).toBeInTheDocument()
    expect(textarea).toHaveClass("w-full", "min-h-(--min-h-textarea)", "resize-y")
    expect(textarea).toHaveAttribute("placeholder", "events:detail.sections.about.fieldLabel_en")
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

  it("keeps save disabled for an unchanged or whitespace-only draft and enables real changes", async () => {
    const user = userEvent.setup()
    mockPatch.mockResolvedValue({ status: 200 })
    render(<EventAboutEditor {...baseProps} />)

    await user.click(screen.getByLabelText("events:detail.sections.about.editAria"))
    const textarea = screen.getByRole("textbox")
    const save = screen.getByRole("button", { name: "common:buttons.save" })
    expect(save).toBeDisabled()

    await user.clear(textarea)
    await user.type(textarea, "   A hands-on workshop on React 19 concurrent features.   ")
    expect(save).toBeDisabled()

    await user.clear(textarea)
    await user.type(textarea, "Updated workshop details")
    expect(save).toBeEnabled()
  })

  it("compares trimmed drafts with trimmed baselines", async () => {
    const user = userEvent.setup()
    mockPatch.mockResolvedValue({ status: 200 })
    render(
      <EventAboutEditor
        {...baseProps}
        event={{ ...baseEvent, about_en: "  Stable workshop details  " }}
      />
    )

    await user.click(screen.getByLabelText("events:detail.sections.about.editAria"))
    expect(screen.getByRole("button", { name: "common:buttons.save" })).toBeDisabled()
  })

  it("exposes the pending state and restores heading focus after a successful save", async () => {
    const user = userEvent.setup()
    let resolvePatch: ((value: { status: number }) => void) | undefined
    mockPatch.mockReturnValue(
      new Promise<{ status: number }>((resolve) => {
        resolvePatch = resolve
      })
    )
    const onUpdate = vi.fn(() => Promise.resolve())
    render(<EventAboutEditor {...baseProps} onUpdate={onUpdate} />)

    await user.click(screen.getByLabelText("events:detail.sections.about.editAria"))
    const textarea = screen.getByRole("textbox")
    await user.clear(textarea)
    await user.type(textarea, "Updated workshop details")
    await user.click(screen.getByRole("button", { name: "common:buttons.save" }))

    expect(
      screen.getByRole("button", { name: "events:detail.sections.about.savePending" })
    ).toBeDisabled()
    expect(textarea).toBeDisabled()
    expect(screen.getByRole("button", { name: "common:buttons.cancel" })).toBeDisabled()

    resolvePatch?.({ status: 200 })
    await screen.findByRole("heading", { name: "events:detail.sections.about.title" })
    await vi.waitFor(() =>
      expect(
        screen.getByRole("heading", { name: "events:detail.sections.about.title" })
      ).toHaveFocus()
    )
    expect(onUpdate).toHaveBeenCalledOnce()
  })

  it("clears the pending state after a successful save", async () => {
    const user = userEvent.setup()
    mockPatch.mockResolvedValue({ status: 200 })
    render(<EventAboutEditor {...baseProps} />)

    const heading = screen.getByRole("heading", { name: "events:detail.sections.about.title" })
    expect(heading).toHaveAttribute("tabindex", "-1")

    await user.click(screen.getByLabelText("events:detail.sections.about.editAria"))
    const textarea = screen.getByRole("textbox")
    await user.clear(textarea)
    await user.type(textarea, "Updated workshop details")
    await user.click(screen.getByRole("button", { name: "common:buttons.save" }))

    await waitFor(() => expect(screen.queryByRole("textbox")).not.toBeInTheDocument())
    await user.click(screen.getByLabelText("events:detail.sections.about.editAria"))
    const reopenedTextarea = screen.getByRole("textbox")
    await user.clear(reopenedTextarea)
    await user.type(reopenedTextarea, "Another workshop update")
    expect(screen.getByRole("button", { name: "common:buttons.save" })).toBeEnabled()
  })

  it("reports refresh failures without leaving the editor stuck in the pending state", async () => {
    const user = userEvent.setup()
    const failure = new Error("refresh failed")
    mockPatch.mockResolvedValue({ status: 200 })
    const onUpdate = vi.fn(() => Promise.reject(failure))
    const onError = vi.fn()
    render(<EventAboutEditor {...baseProps} onUpdate={onUpdate} onError={onError} />)

    await user.click(screen.getByLabelText("events:detail.sections.about.editAria"))
    const textarea = screen.getByRole("textbox")
    await user.clear(textarea)
    await user.type(textarea, "Updated workshop details")
    await user.click(screen.getByRole("button", { name: "common:buttons.save" }))

    await vi.waitFor(() =>
      expect(onError).toHaveBeenCalledWith("events:detail.messages.aboutUpdateFailed")
    )
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
    await waitFor(() => {
      expect(mockLogError).toHaveBeenCalledWith("[EventAboutEditor] Save failed:", failure)
      expect(onError).toHaveBeenCalledWith("events:detail.messages.aboutUpdateFailed")
    })
    expect(screen.getByRole("textbox")).toBeInTheDocument()
  })
})
