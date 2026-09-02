import { createEvent, fireEvent, render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"
import type { ComponentProps, ReactNode } from "react"

const { language } = vi.hoisted(() => ({ language: { current: "en" } }))
const { useTranslationMock, translationMock } = vi.hoisted(() => {
  const translationMock = vi.fn((key: string) => key)
  return {
    useTranslationMock: vi.fn(() => ({
      t: translationMock,
      i18n: {
        get language() {
          return language.current
        },
      },
    })),
    translationMock,
  }
})

vi.mock("react-i18next", () => ({
  useTranslation: useTranslationMock,
}))

vi.mock("@/components/ui/Dialog", () => {
  const MockDialog = ({
    open,
    onClose,
    title,
    children,
    footer,
  }: {
    open: boolean
    onClose: () => void
    title?: ReactNode
    children: ReactNode
    footer?: ReactNode
  }) =>
    open ? (
      <div role="dialog" aria-label="Event edit dialog">
        <div>{title}</div>
        {children}
        <div>{footer}</div>
        <button type="button" onClick={onClose}>
          Close
        </button>
      </div>
    ) : null

  return { Dialog: MockDialog, default: MockDialog }
})

vi.mock("@/components/media/SmartImage", () => ({
  default: ({ srcRaw, alt }: { srcRaw: string; alt: string }) => <img src={srcRaw} alt={alt} />,
}))

import { EventEditDialog, normalizeDatetimeLocal } from "@/components/events/EventEditDialog"
import type { EventEditDraft } from "@/types/Event"

const draft: EventEditDraft = {
  id: "evt-1",
  title: "Мастер-класс",
  title_en: "Workshop",
  description: "Описание",
  description_en: "Description",
  event_type: "Семинар",
  event_type_en: "Seminar",
  location: "ГУК-305",
  location_en: "Main Building",
  starts_at: "2026-06-15T14:00",
  ends_at: "2026-06-15T16:00",
  speaker: "Dr. Ivanova",
  image_url: "https://cdn.example/event.png",
}

const createProps = (overrides: Partial<ComponentProps<typeof EventEditDialog>> = {}) => ({
  open: true,
  onClose: vi.fn(),
  draft,
  setDraft: vi.fn(),
  onSave: vi.fn(),
  loading: false,
  imageLoading: false,
  dateError: false,
  normalizedTitle: "Workshop",
  normalizedLocation: "Main Building",
  newImage: null,
  setNewImage: vi.fn(),
  previewUrl: null,
  ...overrides,
})

describe("EventEditDialog", () => {
  beforeEach(() => {
    language.current = "en"
    vi.clearAllMocks()
  })

  it("renders nothing when closed", () => {
    render(<EventEditDialog {...createProps({ open: false })} />)
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
  })

  it("renders English fields, preview, and saves or cancels through the dialog controls", async () => {
    const user = userEvent.setup()
    const props = createProps()
    render(<EventEditDialog {...props} />)

    const dialog = screen.getByRole("dialog")
    expect(dialog).toBeInTheDocument()
    expect(screen.getByLabelText("events:form.title_en")).toHaveValue("Workshop")
    expect(screen.getByLabelText("events:form.description_en")).toHaveValue("Description")
    expect(screen.getByLabelText("events:form.type_en")).toHaveValue("Seminar")
    expect(screen.getByLabelText("events:form.location_en")).toHaveValue("Main Building")
    expect(screen.getByLabelText("events:form.start")).toHaveValue("2026-06-15T14:00")
    expect(screen.getByLabelText("events:form.end")).toHaveValue("2026-06-15T16:00")
    expect(screen.getByLabelText("events:form.speaker")).toHaveValue("Dr. Ivanova")
    expect(screen.getByAltText("events:alt.preview")).toHaveAttribute("src", draft.image_url)
    expect(screen.getByLabelText("events:form.title_en")).toHaveClass(
      "bg-(--input-bg)",
      "border",
      "focus:border-brand"
    )
    expect(screen.getByLabelText("events:form.description_en")).toHaveClass(
      "min-h-(--min-h-textarea)",
      "resize-y"
    )
    expect(screen.getByLabelText("events:form.end")).not.toHaveClass("border-error-border")
    expect(useTranslationMock).toHaveBeenCalledWith(["events", "common"])
    expect(translationMock).toHaveBeenCalledWith("events:card.dialogs.edit.title")
    expect(screen.getByText("common:buttons.changePhoto")).toBeInTheDocument()

    await user.clear(screen.getByLabelText("events:form.title_en"))
    await user.type(screen.getByLabelText("events:form.title_en"), "Updated")
    await user.clear(screen.getByLabelText("events:form.description_en"))
    await user.type(screen.getByLabelText("events:form.description_en"), "Updated description")
    await user.clear(screen.getByLabelText("events:form.type_en"))
    await user.type(screen.getByLabelText("events:form.type_en"), "Lecture")
    await user.clear(screen.getByLabelText("events:form.location_en"))
    await user.type(screen.getByLabelText("events:form.location_en"), "Room 101")
    await user.clear(screen.getByLabelText("events:form.start"))
    await user.type(screen.getByLabelText("events:form.start"), "2026-06-16T10:00")
    await user.clear(screen.getByLabelText("events:form.end"))
    await user.type(screen.getByLabelText("events:form.end"), "2026-06-16T12:00")
    fireEvent.change(screen.getByLabelText("events:form.speaker"), {
      target: { value: "Prof. Smith" },
    })

    expect(props.setDraft).toHaveBeenCalled()
    expect(props.setDraft).toHaveBeenLastCalledWith(
      expect.objectContaining({ speaker: "Prof. Smith" })
    )
    await user.click(screen.getByRole("button", { name: "common:buttons.save" }))
    expect(props.onSave).toHaveBeenCalledOnce()

    await user.click(screen.getByRole("button", { name: "common:buttons.cancel" }))
    expect(props.onClose).toHaveBeenCalledOnce()
    await user.click(screen.getByRole("button", { name: "Close" }))
    expect(props.onClose).toHaveBeenCalledTimes(2)
  })

  it("uses Russian fields, updates localized values, and ignores an empty file selection", async () => {
    language.current = "ru"
    const props = createProps({ previewUrl: "blob:preview" })
    render(<EventEditDialog {...props} />)

    screen.getByRole("dialog")
    expect(screen.getByLabelText("events:form.title")).toHaveValue("Мастер-класс")
    expect(screen.getByLabelText("events:form.description")).toHaveValue("Описание")
    expect(screen.getByLabelText("events:form.type")).toHaveValue("Семинар")
    expect(screen.getByLabelText("events:form.location")).toHaveValue("ГУК-305")
    expect(screen.getByAltText("events:alt.preview")).toHaveAttribute("src", "blob:preview")

    fireEvent.change(screen.getByLabelText("events:form.title"), {
      target: { value: "Новое название" },
    })
    expect(props.setDraft).toHaveBeenLastCalledWith(
      expect.objectContaining({ title: "Новое название" })
    )

    fireEvent.change(screen.getByLabelText("events:form.description"), {
      target: { value: "Новое описание" },
    })
    expect(props.setDraft).toHaveBeenLastCalledWith(
      expect.objectContaining({ description: "Новое описание" })
    )
    fireEvent.change(screen.getByLabelText("events:form.type"), {
      target: { value: "Лекция" },
    })
    expect(props.setDraft).toHaveBeenLastCalledWith(
      expect.objectContaining({ event_type: "Лекция" })
    )
    fireEvent.change(screen.getByLabelText("events:form.location"), {
      target: { value: "Аудитория 101" },
    })
    expect(props.setDraft).toHaveBeenLastCalledWith(
      expect.objectContaining({ location: "Аудитория 101" })
    )

    const fileInput = document.querySelector<HTMLInputElement>('input[type="file"]')!
    fireEvent.change(fileInput, { target: { files: [] } })
    expect(props.setNewImage).not.toHaveBeenCalled()
  })

  it("passes a selected file to the setter and exposes date and loading guards", async () => {
    const user = userEvent.setup()
    const props = createProps({ imageLoading: true, dateError: true })
    const rendered = render(<EventEditDialog {...props} />)

    screen.getByRole("dialog")
    expect(screen.getByText("events:form.errors.endsBeforeStarts")).toBeInTheDocument()
    expect(screen.getByLabelText("events:form.end")).toHaveClass("border-error-border")
    expect(screen.getByRole("button", { name: "common:buttons.save" })).toBeDisabled()
    expect(screen.getByText("common:statuses.uploading").closest("label")).toHaveAttribute(
      "aria-disabled",
      "true"
    )

    const fileInput = document.querySelector<HTMLInputElement>('input[type="file"]')!
    const file = new File(["image"], "cover.png", { type: "image/png" })
    await user.upload(fileInput, file)
    expect(props.setNewImage).toHaveBeenCalledWith(file)

    const click = createEvent.click(fileInput)
    const stopPropagation = vi.spyOn(click, "stopPropagation")
    fireEvent(fileInput, click)
    expect(stopPropagation).toHaveBeenCalledOnce()

    rendered.unmount()
    const loadingProps = createProps({ loading: true })
    const loadingView = render(<EventEditDialog {...loadingProps} />)
    expect(screen.getByRole("dialog")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "common:buttons.save" })).toBeDisabled()
    loadingView.unmount()
  })

  it("falls back for missing optional draft values and an unavailable file list", async () => {
    const props = createProps({
      draft: {
        ...draft,
        title: undefined,
        title_en: undefined,
        description: undefined,
        description_en: undefined,
        event_type: undefined,
        event_type_en: undefined,
        location: undefined,
        location_en: undefined,
        starts_at: undefined,
        ends_at: undefined,
        speaker: undefined,
        image_url: undefined,
      },
    })
    render(<EventEditDialog {...props} />)

    screen.getByRole("dialog")
    expect(screen.getByLabelText("events:form.title_en")).toHaveValue("")
    expect(screen.getByLabelText("events:form.description_en")).toHaveValue("")
    expect(screen.getByLabelText("events:form.type_en")).toHaveValue("")
    expect(screen.getByLabelText("events:form.location_en")).toHaveValue("")
    expect(screen.getByLabelText("events:form.start")).toHaveValue("")
    expect(screen.getByLabelText("events:form.end")).toHaveValue("")
    expect(screen.getByLabelText("events:form.speaker")).toHaveValue("")
    expect(screen.queryByAltText("events:alt.preview")).not.toBeInTheDocument()

    const fileInput = document.querySelector<HTMLInputElement>('input[type="file"]')!
    Object.defineProperty(fileInput, "files", { configurable: true, value: undefined })
    fireEvent.change(fileInput)
    expect(props.setNewImage).not.toHaveBeenCalled()
  })

  it("normalizes ISO datetimes to datetime-local precision", async () => {
    render(
      <EventEditDialog
        {...createProps({
          draft: {
            ...draft,
            starts_at: "2026-06-15T14:00:45.000Z",
            ends_at: "2026-06-15T16:00:45.000Z",
          },
        })}
      />
    )

    screen.getByRole("dialog")
    expect(screen.getByLabelText("events:form.start")).toHaveValue("2026-06-15T14:00")
    expect(screen.getByLabelText("events:form.end")).toHaveValue("2026-06-15T16:00")
  })

  it("returns a stable empty value for missing datetime inputs", () => {
    expect(normalizeDatetimeLocal(undefined)).toBe("")
    expect(normalizeDatetimeLocal(null)).toBe("")
    expect(normalizeDatetimeLocal("")).toBe("")
    expect(normalizeDatetimeLocal("2026-06-15T14:00:45.000Z")).toBe("2026-06-15T14:00")
  })

  it("preserves every localized edit callback and updates the preview when props change", async () => {
    const props = createProps()
    const { rerender } = render(<EventEditDialog {...props} />)

    screen.getByRole("dialog")

    fireEvent.change(screen.getByLabelText("events:form.description_en"), {
      target: { value: "A precise description" },
    })
    expect(props.setDraft).toHaveBeenLastCalledWith(
      expect.objectContaining({ description_en: "A precise description" })
    )

    fireEvent.change(screen.getByLabelText("events:form.type_en"), {
      target: { value: "Seminar" },
    })
    expect(props.setDraft).toHaveBeenLastCalledWith(
      expect.objectContaining({ event_type_en: "Seminar" })
    )
    fireEvent.change(screen.getByLabelText("events:form.start"), {
      target: { value: "2026-06-17T09:30" },
    })
    expect(props.setDraft).toHaveBeenLastCalledWith(
      expect.objectContaining({ starts_at: "2026-06-17T09:30" })
    )
    fireEvent.change(screen.getByLabelText("events:form.end"), {
      target: { value: "2026-06-17T11:30" },
    })
    expect(props.setDraft).toHaveBeenLastCalledWith(
      expect.objectContaining({ ends_at: "2026-06-17T11:30" })
    )

    expect(screen.getByLabelText("events:form.start")).toHaveValue("2026-06-15T14:00")
    expect(screen.getByLabelText("events:form.end")).toHaveValue("2026-06-15T16:00")

    rerender(
      <EventEditDialog
        {...props}
        draft={{ ...draft, image_url: "https://cdn.example/updated.png" }}
        previewUrl={null}
      />
    )
    expect(screen.getByAltText("events:alt.preview")).toHaveAttribute(
      "src",
      "https://cdn.example/updated.png"
    )

    rerender(
      <EventEditDialog
        {...props}
        draft={{ ...draft, image_url: "https://cdn.example/updated.png" }}
        previewUrl="blob:latest"
      />
    )
    expect(screen.getByAltText("events:alt.preview")).toHaveAttribute("src", "blob:latest")
  })

  it("disables saving when a normalized title or location is missing", async () => {
    const { unmount } = render(
      <EventEditDialog
        {...createProps({ normalizedTitle: "", normalizedLocation: "Main Building" })}
      />
    )
    screen.getByRole("dialog")
    expect(screen.getByRole("button", { name: "common:buttons.save" })).toBeDisabled()
    unmount()

    render(
      <EventEditDialog {...createProps({ normalizedTitle: "Workshop", normalizedLocation: "" })} />
    )
    screen.getByRole("dialog")
    expect(screen.getByRole("button", { name: "common:buttons.save" })).toBeDisabled()
  })
})
