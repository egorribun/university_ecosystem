import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, it, expect, vi, beforeEach } from "vitest"

vi.mock("framer-motion", async () =>
  (await import("@/tests/helpers/framerMotionMock")).framerMotionMock()
)
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: "en", changeLanguage: () => Promise.resolve() },
  }),
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
    urlCtor.createObjectURL = () => "blob:preview"
    urlCtor.revokeObjectURL = () => {}

    try {
      const user = userEvent.setup()
      const onCreated = vi.fn()
      render(<EventCreateDialog {...baseProps} onCreated={onCreated} />)

      const fileInput = document.querySelector<HTMLInputElement>('input[type="file"]')!
      const file = new File(["x"], "banner.png", { type: "image/png" })
      await user.upload(fileInput, file)

      expect(uploadEventImage).toHaveBeenCalledOnce()
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
})
