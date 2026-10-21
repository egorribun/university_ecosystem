import { expectImagePickerKeyboard } from "@/tests/helpers/imagePickerKeyboard"
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, it, expect, vi, beforeEach } from "vitest"

vi.mock("framer-motion", async () =>
  (await import("@/tests/helpers/framerMotionMock")).framerMotionMock()
)
const { useTranslationMock } = vi.hoisted(() => ({
  useTranslationMock: vi.fn(() => ({
    t: (key: string) => key,
    i18n: { language: "en", changeLanguage: () => Promise.resolve() },
  })),
}))
const { campusTimezone } = vi.hoisted(() => ({
  campusTimezone: { current: "America/New_York" as string | null },
}))
vi.mock("react-i18next", () => ({
  useTranslation: useTranslationMock,
}))
vi.mock("@/contexts/CampusTimezoneContext", () => ({
  useCampusTimezone: () => campusTimezone.current,
}))
// NEVER let the upload request reach MSW — module-mock the api fn directly.
// vi.hoisted so the fn exists before the hoisted vi.mock factory runs.
const { uploadEventImage } = vi.hoisted(() => ({
  uploadEventImage: vi.fn<(file: File) => Promise<string>>(() =>
    Promise.resolve("https://cdn.example.com/uploaded.png")
  ),
}))
vi.mock("@/api/events", () => ({ uploadEventImage }))

import {
  EventCreateDialog,
  canSubmitEventDraft,
  createUploadGenerationCleanup,
  firstSelectedFile,
  hasInvalidEventDates,
  invalidateUploadGeneration,
  normalizeLocalizedValue,
} from "@/components/events/EventCreateDialog"
import * as eventDateTime from "@/utils/eventDateTime"

const baseProps = {
  open: true,
  onClose: vi.fn(),
  onCreated: vi.fn(),
  language: "ru" as const,
}

/**
 * TextField in EventCreateDialog gets no `id`, so `<label htmlFor>` is empty
 * → getByLabelText can't resolve. Find the label element by its text, walk to
 * the TextField wrapper, and return the input/textarea inside it.
 */
function fieldByLabel(labelText: string): HTMLElement {
  const labels = screen.getAllByText(labelText)
  const label = labels.find((el) => el.tagName === "LABEL")
  if (!label) throw new Error(`No <label> with text "${labelText}"`)
  const wrapper = label.parentElement
  const field = wrapper?.querySelector("input, textarea")
  if (!field) throw new Error(`No input/textarea near label "${labelText}"`)
  return field as HTMLElement
}

describe("EventCreateDialog", () => {
  beforeEach(() => {
    campusTimezone.current = "America/New_York"
    uploadEventImage.mockReset()
    uploadEventImage.mockResolvedValue("https://cdn.example.com/uploaded.png")
  })

  it("opens the image picker by keyboard and pointer without creating", async () => {
    const onCreated = vi.fn()
    const onClose = vi.fn()
    render(<EventCreateDialog {...baseProps} onCreated={onCreated} onClose={onClose} />)

    fireEvent.change(fieldByLabel("events:form.title"), {
      target: { value: "Keyboard image" },
    })
    fireEvent.change(fieldByLabel("events:form.location"), {
      target: { value: "Campus hall" },
    })
    fireEvent.change(fieldByLabel("events:form.start"), {
      target: { value: "2030-01-15T10:00" },
    })
    fireEvent.change(fieldByLabel("events:form.end"), {
      target: { value: "2030-01-15T11:00" },
    })
    expect(screen.getByRole("button", { name: "common:buttons.create" })).toBeEnabled()

    const input = document.querySelector<HTMLInputElement>('input[type="file"]')!
    await expectImagePickerKeyboard(
      screen.getByRole("button", { name: "events:form.uploadImage" }),
      input,
      fieldByLabel("events:form.speaker"),
      fieldByLabel("events:form.start")
    )

    expect(uploadEventImage).not.toHaveBeenCalled()
    expect(onCreated).not.toHaveBeenCalled()
    expect(onClose).not.toHaveBeenCalled()
  })

  it("normalizes localized required values and rejects whitespace-only fallbacks", () => {
    expect(normalizeLocalizedValue("  Primary title  ", "Fallback title")).toBe("Primary title")
    expect(normalizeLocalizedValue("   ", "  Fallback title  ")).toBe("Fallback title")
    expect(normalizeLocalizedValue(" ", "\t")).toBe("")
  })

  it("reports date errors only for complete, non-increasing ranges", () => {
    expect(hasInvalidEventDates("", "2026-01-15T10:00")).toBe(false)
    expect(hasInvalidEventDates("2026-01-15T10:00", "")).toBe(false)
    expect(hasInvalidEventDates("2026-01-15T12:00", "2026-01-15T10:00")).toBe(true)
    expect(hasInvalidEventDates("2026-01-15T10:00", "2026-01-15T12:00")).toBe(false)
    expect(hasInvalidEventDates("2026-01-15T10:00", "2026-01-15T10:00")).toBe(true)
    expect(hasInvalidEventDates("2026-01-15T10:00", "not-a-date")).toBe(false)
    expect(hasInvalidEventDates("not-a-date", "2026-01-15T12:00")).toBe(false)

    expect(hasInvalidEventDates("infinite-start", "infinite-end")).toBe(false)
  })

  it("requires every submit precondition", () => {
    const valid = {
      normalizedTitle: "Title",
      startsAt: "2026-01-15T10:00",
      endsAt: "2026-01-15T11:00",
      normalizedLocation: "Room",
      imageUploading: false,
      imageUploadFailed: false,
      dateError: false,
    } as const
    expect(canSubmitEventDraft(valid)).toBe(true)
    for (const key of ["normalizedTitle", "startsAt", "endsAt", "normalizedLocation"] as const) {
      expect(canSubmitEventDraft({ ...valid, [key]: "" })).toBe(false)
    }
    expect(canSubmitEventDraft({ ...valid, imageUploading: true })).toBe(false)
    const failedUpload = { ...valid, imageUploadFailed: true }
    expect(canSubmitEventDraft(failedUpload)).toBe(false)
    expect(canSubmitEventDraft({ ...valid, dateError: true })).toBe(false)
  })

  it("returns only the first selected file and invalidates upload generations monotonically", () => {
    const file = new File(["payload"], "cover.png", { type: "image/png" })
    expect(firstSelectedFile(null)).toBeUndefined()
    expect(firstSelectedFile(undefined)).toBeUndefined()
    expect(firstSelectedFile([] as unknown as FileList)).toBeUndefined()
    expect(firstSelectedFile([file] as unknown as FileList)).toBe(file)

    const generation = { current: 4 }
    invalidateUploadGeneration(generation)
    expect(generation.current).toBe(5)
  })

  it("keeps upload cancellation lifecycle contracts explicit", () => {
    const generation = { current: 4 }
    const onCleanup = vi.fn()
    const cleanup = createUploadGenerationCleanup(generation, onCleanup)

    cleanup()

    expect(generation.current).toBe(5)
    expect(onCleanup).toHaveBeenCalledOnce()

    const noCallbackGeneration = { current: 7 }
    expect(() => createUploadGenerationCleanup(noCallbackGeneration)()).not.toThrow()
    expect(noCallbackGeneration.current).toBe(8)
  })

  it("renders nothing when open=false", () => {
    render(<EventCreateDialog {...baseProps} open={false} />)
    expect(screen.queryByText("events:dialogs.create.title")).not.toBeInTheDocument()
  })

  it("renders the create dialog with localized RU labels and a disabled submit", () => {
    render(<EventCreateDialog {...baseProps} />)
    expect(screen.getByText("events:dialogs.create.title")).toBeInTheDocument()
    expect(screen.getByText("events:form.title")).toBeInTheDocument()
    expect(screen.getByText("events:form.location")).toBeInTheDocument()
    expect(screen.getByText("events:form.start")).toBeInTheDocument()
    expect(screen.getByText("events:form.end")).toBeInTheDocument()
    expect(screen.getByText("events:form.description")).toBeInTheDocument()
    expect(screen.getByText("events:form.type")).toBeInTheDocument()
    expect(screen.getByText("events:form.speaker")).toBeInTheDocument()
    expect(screen.getByText("events:form.image")).toBeInTheDocument()
    expect(screen.getByText("events:form.uploadImage")).toBeInTheDocument()
    expect(useTranslationMock).toHaveBeenCalledWith(["events", "common"])
    expect(fieldByLabel("events:form.title")).toHaveValue("")
    expect(fieldByLabel("events:form.description")).toHaveValue("")
    expect(fieldByLabel("events:form.type")).toHaveValue("")
    expect(fieldByLabel("events:form.location")).toHaveValue("")
    expect(fieldByLabel("events:form.speaker")).toHaveValue("")
    expect(fieldByLabel("events:form.start")).toHaveValue("")
    expect(fieldByLabel("events:form.end")).toHaveValue("")
    expect(screen.queryByText("events:form.errors.endsBeforeStarts")).not.toBeInTheDocument()
    // Submit disabled until required fields are filled
    expect(screen.getByRole("button", { name: "common:buttons.create" })).toBeDisabled()
  })

  it("uses the _en label keys when language is en", () => {
    render(<EventCreateDialog {...baseProps} language="en" />)
    expect(screen.getByText("events:form.title_en")).toBeInTheDocument()
    expect(screen.getByText("events:form.location_en")).toBeInTheDocument()
    expect(screen.getByText("events:form.description_en")).toBeInTheDocument()
    expect(screen.getByText("events:form.type_en")).toBeInTheDocument()
  })

  it("updates optional description, type, and speaker fields", async () => {
    const user = userEvent.setup()
    render(<EventCreateDialog {...baseProps} language="en" />)

    await user.type(fieldByLabel("events:form.description_en"), "Talk details")
    await user.type(fieldByLabel("events:form.type_en"), "Workshop")
    await user.type(fieldByLabel("events:form.speaker"), "Dr. Ada Lovelace")

    expect(fieldByLabel("events:form.description_en")).toHaveValue("Talk details")
    expect(fieldByLabel("events:form.type_en")).toHaveValue("Workshop")
    expect(fieldByLabel("events:form.speaker")).toHaveValue("Dr. Ada Lovelace")
  })

  it("enables submit once title/location/dates are valid and fires onCreated", async () => {
    const user = userEvent.setup()
    const onCreated = vi.fn()
    const onClose = vi.fn()
    render(<EventCreateDialog {...baseProps} onCreated={onCreated} onClose={onClose} />)

    await user.type(fieldByLabel("events:form.title"), "Tech Talk")
    await user.type(fieldByLabel("events:form.location"), "Hall A")
    await user.type(fieldByLabel("events:form.start"), "2026-01-15T10:00")
    await user.type(fieldByLabel("events:form.end"), "2026-01-15T12:00")

    const submit = screen.getByRole("button", { name: "common:buttons.create" })
    expect(submit).toBeEnabled()

    await user.click(submit)
    expect(onCreated).toHaveBeenCalledOnce()
    const draft = onCreated.mock.calls[0]?.[0] as Record<string, string>
    expect(draft.title).toBe("Tech Talk")
    expect(draft.location).toBe("Hall A")
    expect(draft.starts_at).toBe("2026-01-15T15:00:00.000Z")
    expect(draft.ends_at).toBe("2026-01-15T17:00:00.000Z")
    // handleSubmit also closes the dialog
    expect(onClose).toHaveBeenCalledOnce()
  })

  it.each([
    ["title", "events:form.title"],
    ["location", "events:form.location"],
    ["start", "events:form.start"],
    ["end", "events:form.end"],
  ] as const)("keeps create disabled when the required %s is missing", (_field, missingLabel) => {
    render(<EventCreateDialog {...baseProps} />)
    const values: Record<string, string> = {
      "events:form.title": "Required title",
      "events:form.location": "Required room",
      "events:form.start": "2026-01-15T10:00",
      "events:form.end": "2026-01-15T11:00",
    }
    for (const [label, value] of Object.entries(values)) {
      if (label !== missingLabel) fireEvent.change(fieldByLabel(label), { target: { value } })
    }

    expect(screen.getByRole("button", { name: "common:buttons.create" })).toBeDisabled()
  })

  it("shows the end-before-start validation error and keeps submit disabled", async () => {
    const user = userEvent.setup()
    render(<EventCreateDialog {...baseProps} />)

    await user.type(fieldByLabel("events:form.title"), "Reversed")
    await user.type(fieldByLabel("events:form.location"), "Hall B")
    await user.type(fieldByLabel("events:form.start"), "2026-01-15T12:00")
    await user.type(fieldByLabel("events:form.end"), "2026-01-15T10:00")

    expect(screen.getByText("events:form.errors.endsBeforeStarts")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "common:buttons.create" })).toBeDisabled()
  })

  it.each([
    ["en", "2026-03-08T02:30", "events:form.errors.nonexistentCampusTime"],
    ["ru", "2026-11-01T01:30", "events:form.errors.ambiguousCampusTime"],
  ] as const)("blocks campus DST wall time errors in %s", (language, start, errorKey) => {
    campusTimezone.current = "America/New_York"
    const onCreated = vi.fn()
    render(<EventCreateDialog {...baseProps} language={language} onCreated={onCreated} />)

    fireEvent.change(
      fieldByLabel(language === "en" ? "events:form.title_en" : "events:form.title"),
      {
        target: { value: "DST event" },
      }
    )
    fireEvent.change(
      fieldByLabel(language === "en" ? "events:form.location_en" : "events:form.location"),
      { target: { value: "Campus hall" } }
    )
    fireEvent.change(fieldByLabel("events:form.start"), { target: { value: start } })
    fireEvent.change(fieldByLabel("events:form.end"), {
      target: { value: "2026-11-01T03:00" },
    })

    expect(screen.getByText(errorKey)).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "common:buttons.create" })).toBeDisabled()
    expect(onCreated).not.toHaveBeenCalled()
  })

  it("shows a readable error and blocks submission without the server campus timezone", () => {
    campusTimezone.current = null
    render(<EventCreateDialog {...baseProps} />)
    expect(screen.getAllByText("events:form.errors.campusTimezoneUnavailable")).toHaveLength(2)
    expect(screen.getByRole("button", { name: "common:buttons.create" })).toBeDisabled()
  })

  it("invokes onClose via the Cancel button", async () => {
    const user = userEvent.setup()
    const onClose = vi.fn()
    render(<EventCreateDialog {...baseProps} onClose={onClose} />)
    await user.click(screen.getByRole("button", { name: "common:buttons.cancel" }))
    expect(onClose).toHaveBeenCalledOnce()
  })

  it("blocks event creation after an image upload fails", async () => {
    const user = userEvent.setup()
    const onCreated = vi.fn()
    uploadEventImage.mockRejectedValueOnce(new Error("upload failed"))

    const urlCtor = URL as unknown as {
      createObjectURL?: (obj: unknown) => string
      revokeObjectURL?: (url: string) => void
    }
    const previousCreate = urlCtor.createObjectURL
    const previousRevoke = urlCtor.revokeObjectURL
    urlCtor.createObjectURL = vi.fn(() => "blob:failed-upload")
    urlCtor.revokeObjectURL = vi.fn()

    try {
      render(<EventCreateDialog {...baseProps} onCreated={onCreated} />)
      await user.type(fieldByLabel("events:form.title"), "Needs a cover")
      await user.type(fieldByLabel("events:form.location"), "Campus hall")
      await user.type(fieldByLabel("events:form.start"), "2026-01-15T10:00")
      await user.type(fieldByLabel("events:form.end"), "2026-01-15T11:00")
      await user.upload(
        document.querySelector<HTMLInputElement>('input[type="file"]')!,
        new File(["image"], "cover.png", { type: "image/png" })
      )

      expect(await screen.findByRole("alert")).toHaveTextContent(
        "events:detail.upload.errors.failed"
      )
      expect(screen.getByRole("button", { name: "common:buttons.create" })).toBeDisabled()
      expect(onCreated).not.toHaveBeenCalled()
    } finally {
      urlCtor.createObjectURL = previousCreate
      urlCtor.revokeObjectURL = previousRevoke
    }
  })

  it("keeps the required-image failure after the parent hides and reopens the dialog", async () => {
    const user = userEvent.setup()
    const onCreated = vi.fn()
    uploadEventImage.mockRejectedValueOnce(new Error("upload failed"))

    const urlCtor = URL as unknown as {
      createObjectURL?: (obj: unknown) => string
      revokeObjectURL?: (url: string) => void
    }
    const previousCreate = urlCtor.createObjectURL
    const previousRevoke = urlCtor.revokeObjectURL
    urlCtor.createObjectURL = vi.fn(() => "blob:reopened-failed-upload")
    urlCtor.revokeObjectURL = vi.fn()

    try {
      const props = { ...baseProps, onCreated }
      const { rerender } = render(<EventCreateDialog {...props} />)
      await user.type(fieldByLabel("events:form.title"), "Keep the failed-upload state")
      await user.type(fieldByLabel("events:form.location"), "Campus hall")
      await user.type(fieldByLabel("events:form.start"), "2026-01-15T10:00")
      await user.type(fieldByLabel("events:form.end"), "2026-01-15T11:00")
      await user.upload(
        document.querySelector<HTMLInputElement>('input[type="file"]')!,
        new File(["image"], "cover.png", { type: "image/png" })
      )

      expect(await screen.findByRole("alert")).toHaveTextContent(
        "events:detail.upload.errors.failed"
      )
      rerender(<EventCreateDialog {...props} open={false} />)
      rerender(<EventCreateDialog {...props} open />)

      expect(fieldByLabel("events:form.title")).toHaveValue("Keep the failed-upload state")
      expect(screen.getByRole("alert")).toHaveTextContent("events:detail.upload.errors.failed")
      expect(screen.getByRole("button", { name: "common:buttons.create" })).toBeDisabled()
      expect(onCreated).not.toHaveBeenCalled()
    } finally {
      urlCtor.createObjectURL = previousCreate
      urlCtor.revokeObjectURL = previousRevoke
    }
  })

  it("rejects an empty upload URL as a missing event picture", async () => {
    const user = userEvent.setup()
    uploadEventImage.mockResolvedValueOnce(" ")
    const urlCtor = URL as unknown as {
      createObjectURL?: (obj: unknown) => string
      revokeObjectURL?: (url: string) => void
    }
    const previousCreate = urlCtor.createObjectURL
    const previousRevoke = urlCtor.revokeObjectURL
    urlCtor.createObjectURL = vi.fn(() => "blob:empty-upload-url")
    urlCtor.revokeObjectURL = vi.fn()

    try {
      render(<EventCreateDialog {...baseProps} />)
      await user.type(fieldByLabel("events:form.title"), "Needs a usable picture")
      await user.type(fieldByLabel("events:form.location"), "Campus hall")
      await user.type(fieldByLabel("events:form.start"), "2026-01-15T10:00")
      await user.type(fieldByLabel("events:form.end"), "2026-01-15T11:00")
      await user.upload(
        document.querySelector<HTMLInputElement>('input[type="file"]')!,
        new File(["image"], "cover.png", { type: "image/png" })
      )

      expect(await screen.findByRole("alert")).toHaveTextContent(
        "events:detail.upload.errors.failed"
      )
      expect(screen.getByRole("button", { name: "common:buttons.create" })).toBeDisabled()
    } finally {
      urlCtor.createObjectURL = previousCreate
      urlCtor.revokeObjectURL = previousRevoke
    }
  })

  it("describes the event dialog for assistive technology", () => {
    render(<EventCreateDialog {...baseProps} />)

    const dialog = screen.getByRole("dialog")
    const descriptionId = dialog.getAttribute("aria-describedby")
    expect(descriptionId).toBe("event-create-dialog-description")
    expect(document.getElementById(descriptionId!)).toHaveTextContent(
      "events:dialogs.create.description"
    )
  })

  it("keeps the event draft open while asynchronous creation is pending", async () => {
    const user = userEvent.setup()
    let resolveCreate!: (value: void | PromiseLike<void>) => void
    const onCreated = vi.fn(
      () =>
        new Promise<void>((resolve) => {
          resolveCreate = resolve
        })
    )
    const onClose = vi.fn()
    render(<EventCreateDialog {...baseProps} onCreated={onCreated} onClose={onClose} />)
    await user.type(fieldByLabel("events:form.title"), "Wait for event creation")
    await user.type(fieldByLabel("events:form.location"), "Campus hall")
    await user.type(fieldByLabel("events:form.start"), "2026-01-15T10:00")
    await user.type(fieldByLabel("events:form.end"), "2026-01-15T11:00")

    await user.click(screen.getByRole("button", { name: "common:buttons.create" }))
    await waitFor(() => expect(onCreated).toHaveBeenCalledOnce())

    const createButton = screen.getByRole("button", { name: "common:buttons.create" })
    expect(createButton).toBeDisabled()
    await user.click(createButton)
    expect(onCreated).toHaveBeenCalledOnce()
    expect(fieldByLabel("events:form.title")).toBeDisabled()
    await user.keyboard("{Escape}")
    expect(screen.getByRole("dialog")).toBeInTheDocument()
    expect(onClose).not.toHaveBeenCalled()

    await act(async () => resolveCreate(undefined))
    await waitFor(() => expect(onClose).toHaveBeenCalledOnce())
  })

  it("keeps the event draft and reports asynchronous creation failures", async () => {
    const user = userEvent.setup()
    const failure = new Error("event creation failed")
    const rejectedCreate = Promise.reject(failure)
    // Attach a handler so the baseline implementation can report the missing
    // UI behavior without creating an unhandled-rejection warning.
    void rejectedCreate.catch(() => undefined)
    const onCreated = vi.fn(() => rejectedCreate)
    const onClose = vi.fn()
    render(<EventCreateDialog {...baseProps} onCreated={onCreated} onClose={onClose} />)
    await user.type(fieldByLabel("events:form.title"), "Retry event creation")
    await user.type(fieldByLabel("events:form.location"), "Campus hall")
    await user.type(fieldByLabel("events:form.start"), "2026-01-15T10:00")
    await user.type(fieldByLabel("events:form.end"), "2026-01-15T11:00")

    await user.click(screen.getByRole("button", { name: "common:buttons.create" }))

    expect(await screen.findByRole("alert")).toHaveTextContent("common:errors.generic")
    expect(screen.getByRole("dialog")).toBeInTheDocument()
    expect(fieldByLabel("events:form.title")).toHaveValue("Retry event creation")
    expect(onClose).not.toHaveBeenCalled()
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "common:buttons.create" })).toHaveFocus()
    })
  })

  it("uploads an image and stores the returned URL on the draft", async () => {
    // jsdom's URL lacks createObjectURL/revokeObjectURL — assign directly so
    // the component's synchronous preview path doesn't throw before the upload.
    const urlCtor = URL as unknown as {
      createObjectURL?: (obj: unknown) => string
      revokeObjectURL?: (url: string) => void
    }
    const prevCreate = urlCtor.createObjectURL
    const prevRevoke = urlCtor.revokeObjectURL
    const createObjectURL = vi
      .fn<(object: unknown) => string>()
      .mockReturnValueOnce("blob:first-preview")
      .mockReturnValueOnce("blob:second-preview")
    const revokeObjectURL = vi.fn()
    urlCtor.createObjectURL = createObjectURL
    urlCtor.revokeObjectURL = revokeObjectURL

    try {
      const user = userEvent.setup()
      const onCreated = vi.fn()
      render(<EventCreateDialog {...baseProps} onCreated={onCreated} />)

      const fileInput = document.querySelector<HTMLInputElement>('input[type="file"]')!
      const file = new File(["x"], "banner.png", { type: "image/png" })
      await user.upload(fileInput, file)

      const replacement = new File(["y"], "replacement.png", { type: "image/png" })
      await user.upload(fileInput, replacement)

      expect(uploadEventImage).toHaveBeenCalledTimes(2)
      expect(revokeObjectURL).toHaveBeenCalledWith("blob:first-preview")
      // image preview block now visible (selected label key)
      expect(await screen.findByText("events:form.imageSelected")).toBeInTheDocument()

      // fill the rest + submit to assert image_url propagated into the draft
      await user.type(fieldByLabel("events:form.title"), "With Image")
      await user.type(fieldByLabel("events:form.location"), "Hall C")
      await user.type(fieldByLabel("events:form.start"), "2026-01-15T10:00")
      await user.type(fieldByLabel("events:form.end"), "2026-01-15T11:00")
      await user.click(screen.getByRole("button", { name: "common:buttons.create" }))

      const draft = onCreated.mock.calls[0]?.[0] as Record<string, string>
      expect(draft.image_url).toBe("https://cdn.example.com/uploaded.png")
    } finally {
      urlCtor.createObjectURL = prevCreate
      urlCtor.revokeObjectURL = prevRevoke
    }
  })

  it("reports upload failure, releases its preview Blob, and permits retry", async () => {
    uploadEventImage.mockRejectedValueOnce(new Error("upload failed"))
    const urlCtor = URL as unknown as {
      createObjectURL?: (obj: unknown) => string
      revokeObjectURL?: (url: string) => void
    }
    const previousCreate = urlCtor.createObjectURL
    const previousRevoke = urlCtor.revokeObjectURL
    const createObjectURL = vi
      .fn<(object: unknown) => string>()
      .mockReturnValueOnce("blob:failed-upload")
      .mockReturnValueOnce("blob:retried-upload")
    const revokeObjectURL = vi.fn()
    urlCtor.createObjectURL = createObjectURL
    urlCtor.revokeObjectURL = revokeObjectURL

    try {
      const user = userEvent.setup()
      const onCreated = vi.fn()
      render(<EventCreateDialog {...baseProps} onCreated={onCreated} />)
      const fileInput = document.querySelector<HTMLInputElement>('input[type="file"]')!

      await user.upload(fileInput, new File(["bad"], "failed.png", { type: "image/png" }))
      expect(await screen.findByRole("alert")).toHaveTextContent(
        "events:detail.upload.errors.failed"
      )
      expect(screen.queryByAltText("events:alt.preview")).not.toBeInTheDocument()
      expect(screen.getByText("events:form.uploadImage")).toBeInTheDocument()
      await waitFor(() => expect(revokeObjectURL).toHaveBeenCalledWith("blob:failed-upload"))

      await user.upload(fileInput, new File(["retry"], "retry.png", { type: "image/png" }))
      expect(await screen.findByText("events:form.imageSelected")).toBeInTheDocument()
      expect(screen.queryByRole("alert")).not.toBeInTheDocument()
      expect(screen.getByAltText("events:alt.preview")).toHaveAttribute(
        "src",
        "https://cdn.example.com/uploaded.png"
      )
      await waitFor(() => expect(revokeObjectURL).toHaveBeenCalledWith("blob:retried-upload"))

      await user.type(fieldByLabel("events:form.title"), "Retry upload")
      await user.type(fieldByLabel("events:form.location"), "Hall G")
      await user.type(fieldByLabel("events:form.start"), "2026-01-15T10:00")
      await user.type(fieldByLabel("events:form.end"), "2026-01-15T11:00")
      await user.click(screen.getByRole("button", { name: "common:buttons.create" }))

      expect(onCreated).toHaveBeenCalledWith(
        expect.objectContaining({ image_url: "https://cdn.example.com/uploaded.png" })
      )
    } finally {
      urlCtor.createObjectURL = previousCreate
      urlCtor.revokeObjectURL = previousRevoke
    }
  })

  it("keeps a replacement upload canonical when an earlier upload resolves after cancel", async () => {
    let resolveFirstUpload!: (url: string) => void
    const firstUpload = new Promise<string>((resolve) => {
      resolveFirstUpload = resolve
    })
    uploadEventImage
      .mockImplementationOnce(() => firstUpload)
      .mockResolvedValueOnce("https://cdn.example.com/replacement.png")

    const urlCtor = URL as unknown as {
      createObjectURL?: (obj: unknown) => string
      revokeObjectURL?: (url: string) => void
    }
    const previousCreate = urlCtor.createObjectURL
    const previousRevoke = urlCtor.revokeObjectURL
    const createObjectURL = vi
      .fn<(object: unknown) => string>()
      .mockReturnValueOnce("blob:stale-preview")
      .mockReturnValueOnce("blob:replacement-preview")
    const revokeObjectURL = vi.fn()
    urlCtor.createObjectURL = createObjectURL
    urlCtor.revokeObjectURL = revokeObjectURL

    try {
      const user = userEvent.setup()
      const onCreated = vi.fn()
      render(<EventCreateDialog {...baseProps} onCreated={onCreated} />)

      const firstInput = document.querySelector<HTMLInputElement>('input[type="file"]')!
      await user.upload(firstInput, new File(["old"], "old.png", { type: "image/png" }))
      expect(await screen.findByText("common:statuses.uploading")).toBeInTheDocument()
      expect(screen.getByAltText("events:alt.preview")).toHaveAttribute("src", "blob:stale-preview")

      await user.click(screen.getByRole("button", { name: "common:buttons.cancel" }))
      await user.click(screen.getByRole("button", { name: "common:buttons.discardChanges" }))
      expect(screen.queryByAltText("events:alt.preview")).not.toBeInTheDocument()
      expect(revokeObjectURL).toHaveBeenCalledWith("blob:stale-preview")

      const replacementInput = document.querySelector<HTMLInputElement>('input[type="file"]')!
      await user.upload(
        replacementInput,
        new File(["new"], "replacement.png", { type: "image/png" })
      )
      await waitFor(() => expect(uploadEventImage).toHaveBeenCalledTimes(2))
      const canonicalPreview = await screen.findByAltText("events:alt.preview")
      const canonicalSrc = canonicalPreview.getAttribute("src")
      expect(canonicalSrc).toContain("replacement.png")
      expect(revokeObjectURL).toHaveBeenCalledWith("blob:replacement-preview")

      await act(async () => {
        resolveFirstUpload("https://cdn.example.com/stale.png")
        await firstUpload
      })

      expect(screen.getByAltText("events:alt.preview")).toHaveAttribute("src", canonicalSrc)

      await user.type(fieldByLabel("events:form.title"), "Replacement")
      await user.type(fieldByLabel("events:form.location"), "Hall D")
      await user.type(fieldByLabel("events:form.start"), "2026-01-15T10:00")
      await user.type(fieldByLabel("events:form.end"), "2026-01-15T11:00")
      await user.click(screen.getByRole("button", { name: "common:buttons.create" }))

      expect(onCreated).toHaveBeenCalledWith(
        expect.objectContaining({ image_url: "https://cdn.example.com/replacement.png" })
      )
    } finally {
      urlCtor.createObjectURL = previousCreate
      urlCtor.revokeObjectURL = previousRevoke
    }
  })

  it("discards an upload that finishes after the dialog was cancelled", async () => {
    let resolveUpload!: (url: string) => void
    const pendingUpload = new Promise<string>((resolve) => {
      resolveUpload = resolve
    })
    uploadEventImage.mockImplementationOnce(() => pendingUpload)
    vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:cancelled-upload")
    vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => undefined)
    try {
      const user = userEvent.setup()
      render(<EventCreateDialog {...baseProps} />)
      const fileInput = document.querySelector<HTMLInputElement>('input[type="file"]')!
      await user.upload(fileInput, new File(["img"], "late.png", { type: "image/png" }))
      expect(await screen.findByText("common:statuses.uploading")).toBeInTheDocument()

      await user.click(screen.getByRole("button", { name: "common:buttons.cancel" }))
      await user.click(screen.getByRole("button", { name: "common:buttons.discardChanges" }))
      await act(async () => {
        resolveUpload("https://cdn.example.com/late.png")
        await pendingUpload
      })

      expect(screen.queryByAltText("events:alt.preview")).not.toBeInTheDocument()
      expect(screen.queryByText("common:statuses.uploading")).not.toBeInTheDocument()
    } finally {
      vi.restoreAllMocks()
    }
  })

  it("ignores a file-input change when no file was selected", () => {
    // Keep the invalid-file mutation deterministic: Stryker's `if (file)` ->
    // `if (true)` must reach the upload path without jsdom throwing because it
    // does not provide URL.createObjectURL. The production contract remains
    // unchanged: an empty selection must never create a preview or upload.
    const urlCtor = URL as unknown as {
      createObjectURL?: (obj: unknown) => string
      revokeObjectURL?: (url: string) => void
    }
    const previousCreate = urlCtor.createObjectURL
    const previousRevoke = urlCtor.revokeObjectURL
    const createObjectURL = vi
      .fn<(object: unknown) => string>()
      .mockReturnValue("blob:unexpected-empty-selection")
    const revokeObjectURL = vi.fn()
    urlCtor.createObjectURL = createObjectURL
    urlCtor.revokeObjectURL = revokeObjectURL

    try {
      render(<EventCreateDialog {...baseProps} />)
      const fileInput = document.querySelector<HTMLInputElement>('input[type="file"]')!

      fireEvent.change(fileInput, { target: { files: [] } })
      fireEvent.change(fileInput, { target: { files: null } })

      expect(createObjectURL).not.toHaveBeenCalled()
      expect(uploadEventImage).not.toHaveBeenCalled()
    } finally {
      urlCtor.createObjectURL = previousCreate
      urlCtor.revokeObjectURL = previousRevoke
    }
  })

  it("keeps an in-flight upload valid across ordinary draft edits", async () => {
    let resolveUpload!: (url: string) => void
    uploadEventImage.mockImplementationOnce(
      () =>
        new Promise<string>((resolve) => {
          resolveUpload = resolve
        })
    )

    const urlCtor = URL as unknown as {
      createObjectURL?: (obj: unknown) => string
      revokeObjectURL?: (url: string) => void
    }
    const previousCreate = urlCtor.createObjectURL
    const previousRevoke = urlCtor.revokeObjectURL
    urlCtor.createObjectURL = vi.fn(() => "blob:editing")
    urlCtor.revokeObjectURL = vi.fn()

    try {
      const user = userEvent.setup()
      render(<EventCreateDialog {...baseProps} />)
      const input = document.querySelector<HTMLInputElement>('input[type="file"]')!
      await user.upload(input, new File(["x"], "editing.png", { type: "image/png" }))
      await user.type(fieldByLabel("events:form.title"), "Draft edit")

      resolveUpload("https://cdn.example.com/editing.png")
      await waitFor(() => expect(screen.getByText("events:form.imageSelected")).toBeInTheDocument())
      expect(screen.queryByText("common:statuses.uploading")).not.toBeInTheDocument()
    } finally {
      urlCtor.createObjectURL = previousCreate
      urlCtor.revokeObjectURL = previousRevoke
    }
  })

  it("keeps the last uploaded image usable when a replacement upload fails", async () => {
    const user = userEvent.setup()
    const firstImageUrl = "https://cdn.example.com/first-image.png"
    uploadEventImage
      .mockResolvedValueOnce(firstImageUrl)
      .mockRejectedValueOnce(new Error("replacement upload failed"))
    const onCreated = vi.fn()
    const urlCtor = URL as unknown as {
      createObjectURL?: (obj: unknown) => string
      revokeObjectURL?: (url: string) => void
    }
    const previousCreate = urlCtor.createObjectURL
    const previousRevoke = urlCtor.revokeObjectURL
    urlCtor.createObjectURL = vi
      .fn<(obj: unknown) => string>()
      .mockReturnValueOnce("blob:first-image")
      .mockReturnValueOnce("blob:replacement-image")
    urlCtor.revokeObjectURL = vi.fn()

    try {
      render(<EventCreateDialog {...baseProps} onCreated={onCreated} />)
      const fileInput = document.querySelector<HTMLInputElement>('input[type="file"]')!
      await user.upload(fileInput, new File(["first"], "first.png", { type: "image/png" }))
      await waitFor(() => expect(screen.getByText("events:form.imageSelected")).toBeInTheDocument())

      await user.upload(
        fileInput,
        new File(["replacement"], "replacement.png", { type: "image/png" })
      )
      await waitFor(() => expect(uploadEventImage).toHaveBeenCalledTimes(2))
      await waitFor(() =>
        expect(screen.queryByText("common:statuses.uploading")).not.toBeInTheDocument()
      )

      expect(screen.getByText("events:form.imageSelected")).toBeInTheDocument()
      expect(screen.queryByRole("alert")).not.toBeInTheDocument()
      await user.type(fieldByLabel("events:form.title"), "Use last successful image")
      await user.type(fieldByLabel("events:form.location"), "Hall M")
      await user.type(fieldByLabel("events:form.start"), "2026-01-15T10:00")
      await user.type(fieldByLabel("events:form.end"), "2026-01-15T11:00")
      await user.click(screen.getByRole("button", { name: "common:buttons.create" }))

      expect(onCreated).toHaveBeenCalledWith(expect.objectContaining({ image_url: firstImageUrl }))
    } finally {
      urlCtor.createObjectURL = previousCreate
      urlCtor.revokeObjectURL = previousRevoke
    }
  })

  it("does not let a stale upload clear a newer upload's pending state after reopening", async () => {
    let resolveFirst!: (url: string) => void
    let resolveSecond!: (url: string) => void
    const firstUpload = new Promise<string>((resolve) => {
      resolveFirst = resolve
    })
    const secondUpload = new Promise<string>((resolve) => {
      resolveSecond = resolve
    })
    uploadEventImage
      .mockImplementationOnce(() => firstUpload)
      .mockImplementationOnce(() => secondUpload)

    const urlCtor = URL as unknown as {
      createObjectURL?: (obj: unknown) => string
      revokeObjectURL?: (url: string) => void
    }
    const previousCreate = urlCtor.createObjectURL
    const previousRevoke = urlCtor.revokeObjectURL
    urlCtor.createObjectURL = vi
      .fn<(obj: unknown) => string>()
      .mockReturnValueOnce("blob:first")
      .mockReturnValueOnce("blob:second")
    urlCtor.revokeObjectURL = vi.fn()
    let view: ReturnType<typeof render> | undefined

    try {
      const user = userEvent.setup()
      view = render(<EventCreateDialog {...baseProps} />)
      const firstInput = document.querySelector<HTMLInputElement>('input[type="file"]')!
      const firstFile = new File(["a"], "first.png", { type: "image/png" })
      const secondFile = new File(["b"], "second.png", { type: "image/png" })
      await user.upload(firstInput, firstFile)
      expect(uploadEventImage).toHaveBeenCalledTimes(1)
      expect(uploadEventImage).toHaveBeenNthCalledWith(1, firstFile)
      expect(firstInput.closest("label")).toHaveAttribute("aria-disabled", "true")

      // The disabled chooser must not start another request in the same dialog.
      await user.upload(firstInput, secondFile)
      expect(uploadEventImage).toHaveBeenCalledTimes(1)
      expect(firstInput.files?.[0]).toBe(firstFile)
      expect(screen.getByAltText("events:alt.preview")).toHaveAttribute("src", "blob:first")

      // A parent can close and reopen while the first request is still pending.
      view.rerender(<EventCreateDialog {...baseProps} open={false} />)
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
      view.rerender(<EventCreateDialog {...baseProps} open />)
      const secondInput = document.querySelector<HTMLInputElement>('input[type="file"]')!
      expect(secondInput.closest("label")).not.toHaveAttribute("aria-disabled")
      await user.upload(secondInput, secondFile)
      expect(uploadEventImage).toHaveBeenCalledTimes(2)
      expect(uploadEventImage).toHaveBeenNthCalledWith(2, secondFile)
      expect(screen.getByText("common:statuses.uploading")).toBeInTheDocument()
      expect(screen.getByAltText("events:alt.preview")).toHaveAttribute("src", "blob:second")

      await act(async () => {
        resolveFirst("https://cdn.example.com/stale.png")
        await firstUpload
      })
      expect(screen.getByText("common:statuses.uploading")).toBeInTheDocument()
      expect(secondInput.closest("label")).toHaveAttribute("aria-disabled", "true")
      expect(screen.getByAltText("events:alt.preview")).toHaveAttribute("src", "blob:second")

      await act(async () => {
        resolveSecond("https://cdn.example.com/second.png")
        await secondUpload
      })
      expect(screen.queryByText("common:statuses.uploading")).not.toBeInTheDocument()
      expect(screen.getByText("events:form.imageSelected")).toBeInTheDocument()
      expect(secondInput.closest("label")).not.toHaveAttribute("aria-disabled")
      expect(screen.getByAltText("events:alt.preview")).toHaveAttribute(
        "src",
        "https://cdn.example.com/second.png"
      )
    } finally {
      try {
        try {
          view?.unmount()
        } finally {
          await act(async () => {
            resolveFirst("https://cdn.example.com/stale.png")
            resolveSecond("https://cdn.example.com/second.png")
            await Promise.all([firstUpload, secondUpload])
          })
        }
      } finally {
        urlCtor.createObjectURL = previousCreate
        urlCtor.revokeObjectURL = previousRevoke
      }
    }
  })

  it("revokes no preview when closing without an image", () => {
    const revokeObjectURL = vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => undefined)
    const { unmount } = render(<EventCreateDialog {...baseProps} />)

    unmount()
    expect(revokeObjectURL).not.toHaveBeenCalled()
    revokeObjectURL.mockRestore()
  })

  it("clears upload state when the dialog is closed and reopened", async () => {
    const user = userEvent.setup()
    const { rerender } = render(<EventCreateDialog {...baseProps} />)
    const input = document.querySelector<HTMLInputElement>('input[type="file"]')!
    const urlCtor = URL as unknown as {
      createObjectURL?: (obj: unknown) => string
      revokeObjectURL?: (url: string) => void
    }
    const previousCreate = urlCtor.createObjectURL
    const previousRevoke = urlCtor.revokeObjectURL
    urlCtor.createObjectURL = vi.fn(() => "blob:close")
    urlCtor.revokeObjectURL = vi.fn()

    try {
      // Start a pending upload, then close while it is still in flight.
      uploadEventImage.mockImplementationOnce(() => new Promise<string>(() => undefined))
      await user.upload(input, new File(["x"], "close.png", { type: "image/png" }))
      expect(screen.getByText("common:statuses.uploading")).toBeInTheDocument()
      await user.click(screen.getByRole("button", { name: "common:buttons.cancel" }))
      await user.click(screen.getByRole("button", { name: "common:buttons.discardChanges" }))

      rerender(<EventCreateDialog {...baseProps} open />)
      expect(screen.getByText("events:form.uploadImage")).toBeInTheDocument()
      expect(document.querySelector<HTMLInputElement>('input[type="file"]')).not.toBeDisabled()
    } finally {
      urlCtor.createObjectURL = previousCreate
      urlCtor.revokeObjectURL = previousRevoke
    }
  })

  it("keeps Russian and English localized drafts independent", async () => {
    const user = userEvent.setup()
    const onCreated = vi.fn()
    const { rerender } = render(
      <EventCreateDialog {...baseProps} language="en" onCreated={onCreated} />
    )

    await user.type(fieldByLabel("events:form.title_en"), "English title")
    await user.type(fieldByLabel("events:form.location_en"), "English hall")

    rerender(<EventCreateDialog {...baseProps} language="ru" onCreated={onCreated} />)
    expect(fieldByLabel("events:form.title")).toHaveValue("")
    expect(fieldByLabel("events:form.location")).toHaveValue("")
    await user.type(fieldByLabel("events:form.title"), "Русское название")
    await user.type(fieldByLabel("events:form.location"), "Русский зал")

    rerender(<EventCreateDialog {...baseProps} language="en" onCreated={onCreated} />)
    expect(fieldByLabel("events:form.title_en")).toHaveValue("English title")
    expect(fieldByLabel("events:form.location_en")).toHaveValue("English hall")

    rerender(<EventCreateDialog {...baseProps} language="ru" onCreated={onCreated} />)
    expect(fieldByLabel("events:form.title")).toHaveValue("Русское название")
    expect(fieldByLabel("events:form.location")).toHaveValue("Русский зал")
  })

  it("keeps localized optional description and event type values independent", async () => {
    const user = userEvent.setup()
    const { rerender } = render(<EventCreateDialog {...baseProps} language="en" />)

    await user.type(fieldByLabel("events:form.description_en"), "English details")
    await user.type(fieldByLabel("events:form.type_en"), "Lecture")
    rerender(<EventCreateDialog {...baseProps} language="ru" />)
    expect(fieldByLabel("events:form.description")).toHaveValue("")
    expect(fieldByLabel("events:form.type")).toHaveValue("")

    await user.type(fieldByLabel("events:form.description"), "Русские детали")
    await user.type(fieldByLabel("events:form.type"), "Лекция")
    rerender(<EventCreateDialog {...baseProps} language="en" />)
    expect(fieldByLabel("events:form.description_en")).toHaveValue("English details")
    expect(fieldByLabel("events:form.type_en")).toHaveValue("Lecture")
  })

  it("confirms before discarding a dirty draft from Cancel, Escape, or the backdrop", async () => {
    const user = userEvent.setup()
    const onClose = vi.fn()
    render(<EventCreateDialog {...baseProps} onClose={onClose} />)

    await user.type(fieldByLabel("events:form.title"), "Temporary title")
    await user.type(fieldByLabel("events:form.location"), "Temporary hall")
    await user.click(screen.getByRole("button", { name: "common:buttons.cancel" }))

    expect(screen.getByText("common:dialogs.unsavedChanges.description")).toBeInTheDocument()
    expect(onClose).not.toHaveBeenCalled()
    await user.click(screen.getByRole("button", { name: "common:buttons.keepEditing" }))
    expect(fieldByLabel("events:form.title")).toHaveValue("Temporary title")

    await user.keyboard("{Escape}")
    expect(screen.getByText("common:dialogs.unsavedChanges.description")).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "common:buttons.keepEditing" }))

    const backdrop = document.querySelector('[role="presentation"] > div')
    if (!(backdrop instanceof HTMLElement)) throw new Error("Dialog backdrop not found")
    fireEvent.click(backdrop)
    expect(screen.getByText("common:dialogs.unsavedChanges.description")).toBeInTheDocument()
    expect(onClose).not.toHaveBeenCalled()

    await user.click(screen.getByRole("button", { name: "common:buttons.discardChanges" }))
    expect(onClose).toHaveBeenCalledOnce()
    expect(fieldByLabel("events:form.title")).toHaveValue("")
    expect(fieldByLabel("events:form.location")).toHaveValue("")
  })

  it("rejects equal start and end timestamps", async () => {
    const user = userEvent.setup()
    render(<EventCreateDialog {...baseProps} />)

    await user.type(fieldByLabel("events:form.title"), "Equal dates")
    await user.type(fieldByLabel("events:form.location"), "Hall E")
    await user.type(fieldByLabel("events:form.start"), "2026-01-15T10:00")
    await user.type(fieldByLabel("events:form.end"), "2026-01-15T10:00")

    expect(screen.getByText("events:form.errors.endsBeforeStarts")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "common:buttons.create" })).toBeDisabled()
  })

  it("blocks submission while an image upload is still pending", async () => {
    let resolveUpload!: (url: string) => void
    const pendingUpload = new Promise<string>((resolve) => {
      resolveUpload = resolve
    })
    uploadEventImage.mockImplementationOnce(() => pendingUpload)

    const urlCtor = URL as unknown as {
      createObjectURL?: (obj: unknown) => string
      revokeObjectURL?: (url: string) => void
    }
    const previousCreate = urlCtor.createObjectURL
    const previousRevoke = urlCtor.revokeObjectURL
    urlCtor.createObjectURL = vi.fn(() => "blob:pending")
    urlCtor.revokeObjectURL = vi.fn()

    try {
      const user = userEvent.setup()
      render(<EventCreateDialog {...baseProps} />)
      const fileInput = document.querySelector<HTMLInputElement>('input[type="file"]')!
      await user.type(fieldByLabel("events:form.title"), "Pending upload")
      await user.type(fieldByLabel("events:form.location"), "Hall pending")
      await user.type(fieldByLabel("events:form.start"), "2026-01-15T10:00")
      await user.type(fieldByLabel("events:form.end"), "2026-01-15T11:00")
      await user.upload(fileInput, new File(["x"], "pending.png", { type: "image/png" }))
      expect(screen.getByText("common:statuses.uploading")).toBeInTheDocument()
      expect(screen.getByRole("button", { name: "common:buttons.create" })).toBeDisabled()

      resolveUpload("https://cdn.example.com/pending.png")
      await waitFor(() => expect(screen.getByText("events:form.imageSelected")).toBeInTheDocument())
      expect(screen.queryByText("common:statuses.uploading")).not.toBeInTheDocument()
      expect(screen.getByRole("button", { name: "common:buttons.create" })).toBeEnabled()
    } finally {
      urlCtor.createObjectURL = previousCreate
      urlCtor.revokeObjectURL = previousRevoke
    }
  })

  it("submits an English-only title and location through normalization", async () => {
    const user = userEvent.setup()
    const onCreated = vi.fn()
    render(<EventCreateDialog {...baseProps} language="en" onCreated={onCreated} />)

    await user.type(fieldByLabel("events:form.title_en"), "Only English")
    await user.type(fieldByLabel("events:form.location_en"), "English room")
    await user.type(fieldByLabel("events:form.start"), "2026-01-15T10:00")
    await user.type(fieldByLabel("events:form.end"), "2026-01-15T11:00")

    const submit = screen.getByRole("button", { name: "common:buttons.create" })
    expect(submit).toBeEnabled()
    await user.click(submit)
    expect(onCreated).toHaveBeenCalledWith(
      expect.objectContaining({ title_en: "Only English", location_en: "English room" })
    )
  })

  it("also enables a Russian-only draft when English fallbacks are empty", async () => {
    const user = userEvent.setup()
    const onCreated = vi.fn()
    render(<EventCreateDialog {...baseProps} language="ru" onCreated={onCreated} />)

    await user.type(fieldByLabel("events:form.title"), "Русское название")
    await user.type(fieldByLabel("events:form.location"), "Русский зал")
    await user.type(fieldByLabel("events:form.start"), "2026-01-15T10:00")
    await user.type(fieldByLabel("events:form.end"), "2026-01-15T11:00")

    expect(screen.getByRole("button", { name: "common:buttons.create" })).toBeEnabled()
    await user.click(screen.getByRole("button", { name: "common:buttons.create" }))
    expect(onCreated).toHaveBeenCalledWith(
      expect.objectContaining({ title: "Русское название", location: "Русский зал" })
    )
  })

  it("keeps date validation clear until both timestamps are present", async () => {
    const user = userEvent.setup()
    render(<EventCreateDialog {...baseProps} />)

    await user.type(fieldByLabel("events:form.title"), "Partial dates")
    await user.type(fieldByLabel("events:form.location"), "Hall F")
    await user.type(fieldByLabel("events:form.start"), "2026-01-15T10:00")

    expect(screen.queryByText("events:form.errors.endsBeforeStarts")).not.toBeInTheDocument()
  })

  it("invalidates an upload when the dialog unmounts before the request resolves", async () => {
    let resolveUpload!: (url: string) => void
    const pending = new Promise<string>((resolve) => {
      resolveUpload = resolve
    })
    uploadEventImage.mockImplementationOnce(() => pending)

    const createObjectUrl = vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:unmounted")
    const revokeObjectUrl = vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => undefined)
    try {
      const user = userEvent.setup()
      const { unmount } = render(<EventCreateDialog {...baseProps} />)
      const input = document.querySelector<HTMLInputElement>('input[type="file"]')!
      await user.upload(input, new File(["x"], "unmounted.png", { type: "image/png" }))
      expect(screen.getByText("common:statuses.uploading")).toBeInTheDocument()

      unmount()
      await act(async () => {
        resolveUpload("https://cdn.example.com/stale.png")
        await pending
      })

      expect(revokeObjectUrl).toHaveBeenCalledWith("blob:unmounted")
    } finally {
      createObjectUrl.mockRestore()
      revokeObjectUrl.mockRestore()
    }
  })

  it("cancels and resets an upload when the parent closes the dialog", async () => {
    let resolveUpload!: (url: string) => void
    const pending = new Promise<string>((resolve) => {
      resolveUpload = resolve
    })
    uploadEventImage.mockImplementationOnce(() => pending)

    const createObjectUrl = vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:parent-close")
    const revokeObjectUrl = vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => undefined)
    try {
      const user = userEvent.setup()
      const { rerender } = render(<EventCreateDialog {...baseProps} />)
      const input = document.querySelector<HTMLInputElement>('input[type="file"]')!
      await user.upload(input, new File(["x"], "parent-close.png", { type: "image/png" }))
      expect(screen.getByText("common:statuses.uploading")).toBeInTheDocument()

      // Closing through the parent bypasses the local close button, so the
      // visibility lifecycle cleanup must invalidate and reset the upload.
      rerender(<EventCreateDialog {...baseProps} open={false} />)
      resolveUpload("https://cdn.example.com/stale-parent-close.png")
      await act(async () => {
        await pending
      })

      rerender(<EventCreateDialog {...baseProps} open />)
      expect(screen.queryByText("common:statuses.uploading")).not.toBeInTheDocument()
      expect(screen.getByText("events:form.uploadImage")).toBeInTheDocument()
      expect(screen.queryByAltText("events:alt.preview")).not.toBeInTheDocument()
      expect(revokeObjectUrl).toHaveBeenCalledWith("blob:parent-close")
    } finally {
      createObjectUrl.mockRestore()
      revokeObjectUrl.mockRestore()
    }
  })

  it("does not show a stale upload error over a replacement upload", async () => {
    let rejectStaleUpload!: (reason: unknown) => void
    let resolveReplacementUpload!: (url: string) => void
    const staleUpload = new Promise<string>((_resolve, reject) => {
      rejectStaleUpload = reject
    })
    const replacementUpload = new Promise<string>((resolve) => {
      resolveReplacementUpload = resolve
    })
    uploadEventImage
      .mockImplementationOnce(() => staleUpload)
      .mockImplementationOnce(() => replacementUpload)

    const urlCtor = URL as unknown as {
      createObjectURL?: (object: unknown) => string
      revokeObjectURL?: (url: string) => void
    }
    const previousCreate = urlCtor.createObjectURL
    const previousRevoke = urlCtor.revokeObjectURL
    const createObjectURL = vi
      .fn<(object: unknown) => string>()
      .mockReturnValueOnce("blob:stale-failure")
      .mockReturnValueOnce("blob:replacement")
    const revokeObjectURL = vi.fn()
    urlCtor.createObjectURL = createObjectURL
    urlCtor.revokeObjectURL = revokeObjectURL

    try {
      const user = userEvent.setup()
      render(<EventCreateDialog {...baseProps} />)
      const fileInput = document.querySelector<HTMLInputElement>('input[type="file"]')!

      await user.upload(fileInput, new File(["old"], "old.png", { type: "image/png" }))
      expect(await screen.findByText("common:statuses.uploading")).toBeInTheDocument()
      await user.click(screen.getByRole("button", { name: "common:buttons.cancel" }))
      await user.click(screen.getByRole("button", { name: "common:buttons.discardChanges" }))
      await user.upload(
        document.querySelector<HTMLInputElement>('input[type="file"]')!,
        new File(["new"], "new.png", { type: "image/png" })
      )
      await waitFor(() => expect(uploadEventImage).toHaveBeenCalledTimes(2))

      await act(async () => {
        rejectStaleUpload(new Error("stale upload failed"))
        await Promise.resolve()
      })

      expect(screen.getByText("common:statuses.uploading")).toBeInTheDocument()
      expect(screen.queryByRole("alert")).not.toBeInTheDocument()
      expect(revokeObjectURL).toHaveBeenCalledWith("blob:stale-failure")

      await act(async () => {
        resolveReplacementUpload("https://cdn.example.com/replacement.png")
        await replacementUpload
      })
      expect(await screen.findByText("events:form.imageSelected")).toBeInTheDocument()
    } finally {
      urlCtor.createObjectURL = previousCreate
      urlCtor.revokeObjectURL = previousRevoke
    }
  })

  it("revalidates the campus timezone inside the submit handler", async () => {
    const user = userEvent.setup()
    const onCreated = vi.fn()
    const onClose = vi.fn()
    render(<EventCreateDialog {...baseProps} onCreated={onCreated} onClose={onClose} />)

    await user.type(fieldByLabel("events:form.title"), "Timezone race")
    await user.type(fieldByLabel("events:form.location"), "Hall K")
    await user.type(fieldByLabel("events:form.start"), "2026-01-15T10:00")
    await user.type(fieldByLabel("events:form.end"), "2026-01-15T11:00")
    const createButton = screen.getByRole("button", { name: "common:buttons.create" })
    expect(createButton).toBeEnabled()

    const unavailableTimezone = eventDateTime.resolveCampusEventDateRange(
      "2026-01-15T10:00",
      "2026-01-15T11:00",
      null
    )
    const resolveRange = vi
      .spyOn(eventDateTime, "resolveCampusEventDateRange")
      .mockReturnValueOnce(unavailableTimezone)
    try {
      fireEvent.click(createButton)
      expect(resolveRange).toHaveBeenCalledTimes(1)
    } finally {
      resolveRange.mockRestore()
    }

    expect(onCreated).not.toHaveBeenCalled()
    expect(onClose).not.toHaveBeenCalled()
  })

  it("reactivates focus containment after Escape during pending creation", async () => {
    const user = userEvent.setup()
    let resolveCreate!: (value: void | PromiseLike<void>) => void
    const onCreated = vi.fn(
      () =>
        new Promise<void>((resolve) => {
          resolveCreate = resolve
        })
    )
    const onClose = vi.fn()
    const outsideAction = document.createElement("button")
    outsideAction.type = "button"
    outsideAction.textContent = "Outside action"
    document.body.append(outsideAction)

    try {
      render(<EventCreateDialog {...baseProps} onCreated={onCreated} onClose={onClose} />)
      await user.type(fieldByLabel("events:form.title"), "Keep focus trapped")
      await user.type(fieldByLabel("events:form.location"), "Campus hall")
      await user.type(fieldByLabel("events:form.start"), "2026-01-15T10:00")
      await user.type(fieldByLabel("events:form.end"), "2026-01-15T11:00")
      await user.click(screen.getByRole("button", { name: "common:buttons.create" }))
      await waitFor(() => expect(onCreated).toHaveBeenCalledOnce())

      await user.keyboard("{Escape}")
      expect(screen.getByRole("dialog")).toBeInTheDocument()
      expect(fieldByLabel("events:form.title")).toHaveValue("Keep focus trapped")
      expect(onClose).not.toHaveBeenCalled()

      outsideAction.focus()
      await waitFor(() => {
        expect(screen.getByRole("dialog")).toContainElement(document.activeElement as HTMLElement)
        expect(outsideAction).not.toHaveFocus()
      })
      await user.keyboard("{Tab}")
      expect(screen.getByRole("dialog")).toContainElement(document.activeElement as HTMLElement)

      await act(async () => resolveCreate(undefined))
      await waitFor(() => expect(onClose).toHaveBeenCalledOnce())
    } finally {
      outsideAction.remove()
    }
  })

  it("names the create dialog from its visible title", () => {
    render(<EventCreateDialog {...baseProps} />)

    expect(screen.getByRole("dialog", { name: "events:dialogs.create.title" })).toBeInTheDocument()
  })

  it("names discard confirmation and restores the create name when editing resumes", async () => {
    const user = userEvent.setup()
    const onClose = vi.fn()
    render(<EventCreateDialog {...baseProps} onClose={onClose} />)

    await user.type(fieldByLabel("events:form.title"), "Preserved draft")
    await user.click(screen.getByRole("button", { name: "common:buttons.cancel" }))

    expect(
      screen.getByRole("dialog", { name: "common:dialogs.unsavedChanges.title" })
    ).toBeInTheDocument()
    expect(
      screen.queryByRole("dialog", { name: "events:dialogs.create.title" })
    ).not.toBeInTheDocument()
    expect(onClose).not.toHaveBeenCalled()

    await user.click(screen.getByRole("button", { name: "common:buttons.keepEditing" }))

    expect(screen.getByRole("dialog", { name: "events:dialogs.create.title" })).toBeInTheDocument()
    expect(
      screen.queryByRole("dialog", { name: "common:dialogs.unsavedChanges.title" })
    ).not.toBeInTheDocument()
    expect(fieldByLabel("events:form.title")).toHaveValue("Preserved draft")
    expect(onClose).not.toHaveBeenCalled()
  })
})
