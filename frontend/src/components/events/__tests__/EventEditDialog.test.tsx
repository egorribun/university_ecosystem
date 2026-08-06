import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"
import type { ComponentProps } from "react"

const { language } = vi.hoisted(() => ({ language: { current: "en" } }))

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: {
      get language() {
        return language.current
      },
    },
  }),
}))

vi.mock("@/components/media/SmartImage", () => ({
  default: ({ srcRaw, alt }: { srcRaw: string; alt: string }) => <img src={srcRaw} alt={alt} />,
}))

import { EventEditDialog } from "@/components/events/EventEditDialog"
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

    const dialog = await screen.findByRole("dialog")
    expect(dialog).toBeInTheDocument()
    expect(screen.getByLabelText("events:form.title_en")).toHaveValue("Workshop")
    expect(screen.getByLabelText("events:form.description_en")).toHaveValue("Description")
    expect(screen.getByLabelText("events:form.type_en")).toHaveValue("Seminar")
    expect(screen.getByLabelText("events:form.location_en")).toHaveValue("Main Building")
    expect(screen.getByLabelText("events:form.start")).toHaveValue("2026-06-15T14:00")
    expect(screen.getByLabelText("events:form.end")).toHaveValue("2026-06-15T16:00")
    expect(screen.getByLabelText("events:form.speaker")).toHaveValue("Dr. Ivanova")
    expect(screen.getByAltText("events:alt.preview")).toHaveAttribute("src", draft.image_url)

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

    await screen.findByRole("dialog")
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

    const fileInput = screen.getByLabelText("common:buttons.changePhoto") as HTMLInputElement
    fireEvent.change(fileInput, { target: { files: [] } })
    expect(props.setNewImage).not.toHaveBeenCalled()
  })

  it("passes a selected file to the setter and exposes date and loading guards", async () => {
    const user = userEvent.setup()
    const props = createProps({ imageLoading: true, dateError: true })
    const rendered = render(<EventEditDialog {...props} />)

    await screen.findByRole("dialog")
    expect(screen.getByText("events:form.errors.endsBeforeStarts")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "common:buttons.save" })).toBeDisabled()
    expect(screen.getByText("common:statuses.uploading").closest("label")).toHaveAttribute(
      "aria-disabled",
      "true"
    )

    const fileInput = document.querySelector<HTMLInputElement>('input[type="file"]')!
    const file = new File(["image"], "cover.png", { type: "image/png" })
    await user.upload(fileInput, file)
    expect(props.setNewImage).toHaveBeenCalledWith(file)

    rendered.unmount()
    const loadingProps = createProps({ loading: true })
    const loadingView = render(<EventEditDialog {...loadingProps} />)
    await waitFor(() => expect(screen.getByRole("dialog")).toBeInTheDocument())
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

    await screen.findByRole("dialog")
    expect(screen.getByLabelText("events:form.start")).toHaveValue("")
    expect(screen.getByLabelText("events:form.end")).toHaveValue("")
    expect(screen.getByLabelText("events:form.speaker")).toHaveValue("")
    expect(screen.queryByAltText("events:alt.preview")).not.toBeInTheDocument()

    const fileInput = document.querySelector<HTMLInputElement>('input[type="file"]')!
    Object.defineProperty(fileInput, "files", { configurable: true, value: undefined })
    fireEvent.change(fileInput)
    expect(props.setNewImage).not.toHaveBeenCalled()
  })
})
