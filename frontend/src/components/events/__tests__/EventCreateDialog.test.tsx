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
vi.mock("react-i18next", () => ({
  useTranslation: useTranslationMock,
}))
// NEVER let the upload request reach MSW — module-mock the api fn directly.
// vi.hoisted so the fn exists before the hoisted vi.mock factory runs.
const { uploadEventImage } = vi.hoisted(() => ({
  uploadEventImage: vi.fn<(file: File) => Promise<string>>(() =>
    Promise.resolve("https://cdn.example.com/uploaded.png")
  ),
}))
vi.mock("@/api/events", () => ({ uploadEventImage }))

import { EventCreateDialog } from "@/components/events/EventCreateDialog"

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
    uploadEventImage.mockClear()
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
    // Submit disabled until required fields are filled
    expect(screen.getByRole("button", { name: "common:buttons.create" })).toBeDisabled()
  })

  it("uses the _en label keys when language is en", () => {
    render(<EventCreateDialog {...baseProps} language="en" />)
    expect(screen.getByText("events:form.title_en")).toBeInTheDocument()
    expect(screen.getByText("events:form.location_en")).toBeInTheDocument()
    expect(screen.getByText("events:form.description_en")).toBeInTheDocument()
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
    expect(draft.starts_at).toBe("2026-01-15T10:00")
    expect(draft.ends_at).toBe("2026-01-15T12:00")
    // handleSubmit also closes the dialog
    expect(onClose).toHaveBeenCalledOnce()
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

  it("invokes onClose via the Cancel button", async () => {
    const user = userEvent.setup()
    const onClose = vi.fn()
    render(<EventCreateDialog {...baseProps} onClose={onClose} />)
    await user.click(screen.getByRole("button", { name: "common:buttons.cancel" }))
    expect(onClose).toHaveBeenCalledOnce()
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

      expect(createObjectURL).not.toHaveBeenCalled()
      expect(uploadEventImage).not.toHaveBeenCalled()
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

  it("resets the draft immediately when the dialog is closed", async () => {
    const user = userEvent.setup()
    const onClose = vi.fn()
    render(<EventCreateDialog {...baseProps} onClose={onClose} />)

    await user.type(fieldByLabel("events:form.title"), "Temporary title")
    await user.type(fieldByLabel("events:form.location"), "Temporary hall")
    await user.click(screen.getByRole("button", { name: "common:buttons.cancel" }))

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
})
