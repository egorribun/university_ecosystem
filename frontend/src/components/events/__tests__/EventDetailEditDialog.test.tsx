import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { beforeEach, describe, it, expect, vi } from "vitest"
import { waitFor } from "@testing-library/react"

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
const mocks = vi.hoisted(() => ({
  patch: vi.fn(),
  uploadEventImage: vi.fn(),
}))
vi.mock("@/api/events", () => ({ uploadEventImage: mocks.uploadEventImage }))
vi.mock("@/api/client", () => ({
  default: { patch: mocks.patch },
  resetEtagCache: vi.fn(),
  registerSigningKeyAccessor: vi.fn(),
}))
vi.mock("@/app/logger", () => ({ logError: vi.fn() }))

import { EventDetailEditDialog } from "@/components/events/EventDetailEditDialog"
import type { Event } from "@/types/Event"

const baseEvent: Event = {
  id: "evt-1",
  title: "React 19 Patterns Workshop",
  title_en: "React 19 Patterns Workshop",
  description: "A hands-on deep dive into React 19 concurrent features.",
  location: "ГУК-305",
  event_type: "workshop",
  starts_at: "2026-06-15T14:00:00Z",
  ends_at: "2026-06-15T16:00:00Z",
  created_by: "u1",
  created_at: "2026-05-01T10:00:00Z",
  is_active: true,
  speaker: "Dr. Ivanova",
  image_url: "https://picsum.photos/seed/event-detail-edit/800/400",
  image_url_optimized: null,
}

const baseProps = {
  open: true,
  onClose: vi.fn(),
  event: baseEvent,
  onSuccess: vi.fn(),
  onError: vi.fn(),
}

function renderDialog(props = baseProps) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <EventDetailEditDialog {...props} />
    </QueryClientProvider>
  )
}

describe("EventDetailEditDialog", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.patch.mockResolvedValue({ data: {} })
    mocks.uploadEventImage.mockResolvedValue("")
  })

  it("renders the edit dialog when open", () => {
    renderDialog()
    const dialog = screen.getByRole("dialog")
    expect(dialog).toBeInTheDocument()
    expect(dialog.querySelectorAll("input,textarea").length).toBeGreaterThan(0)
    expect(useTranslationMock).toHaveBeenCalledWith(["events", "common"])
  })

  it("does not render the dialog when closed", () => {
    renderDialog({ ...baseProps, open: false })
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
  })

  it("normalizes nullable event fields and falls back to localized title/location", () => {
    const sparseEvent = {
      ...baseEvent,
      title: "",
      title_en: "Fallback title",
      description: null,
      description_en: null,
      event_type: null,
      event_type_en: null,
      location: "",
      location_en: "Fallback location",
      starts_at: null,
      ends_at: null,
      speaker: null,
      image_url: null,
      about: null,
      about_en: null,
    } as unknown as Event

    const { unmount } = renderDialog({ ...baseProps, event: sparseEvent })
    expect(screen.getByDisplayValue("Fallback title")).toBeInTheDocument()
    expect(screen.getByDisplayValue("Fallback location")).toBeInTheDocument()

    unmount()
    renderDialog({
      ...baseProps,
      event: {
        ...sparseEvent,
        title: null,
        title_en: null,
        location: null,
        location_en: null,
      } as unknown as Event,
    })
    expect(screen.getByRole("dialog")).toBeInTheDocument()
  })

  it("fires onClose when the cancel button is clicked", async () => {
    const user = userEvent.setup()
    const onClose = vi.fn()
    renderDialog({ ...baseProps, onClose })
    await user.click(screen.getByRole("button", { name: "common:buttons.cancel" }))
    expect(onClose).toHaveBeenCalledOnce()
  })

  it("saves the draft, invalidates detail/list queries, and reports success", async () => {
    const user = userEvent.setup()
    const onClose = vi.fn()
    const onSuccess = vi.fn()
    renderDialog({ ...baseProps, onClose, onSuccess })

    await user.click(screen.getByRole("button", { name: "common:buttons.save" }))

    await waitFor(() => expect(onSuccess).toHaveBeenCalledWith("events:card.messages.saveSuccess"))
    expect(mocks.patch).toHaveBeenCalledWith(
      "/events/evt-1",
      expect.objectContaining({ id: "evt-1", image_url: baseEvent.image_url })
    )
    expect(onClose).toHaveBeenCalledOnce()
  })

  it("uploads a replacement image and revokes its preview URL on close", async () => {
    const user = userEvent.setup()
    const createObjectUrl = vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:preview")
    const revokeObjectUrl = vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => undefined)
    mocks.uploadEventImage.mockResolvedValue("https://cdn.example/new.png")
    const { unmount } = renderDialog()
    const fileInput = document.querySelector<HTMLInputElement>('input[type="file"]')
    const file = new File(["image"], "cover.png", { type: "image/png" })

    expect(fileInput).not.toBeNull()
    await user.upload(fileInput!, file)
    expect(createObjectUrl).toHaveBeenCalledWith(file)
    expect(screen.getByAltText("events:alt.preview")).toBeInTheDocument()

    await user.click(screen.getByRole("button", { name: "common:buttons.save" }))
    await waitFor(() => expect(mocks.uploadEventImage).toHaveBeenCalledWith(file))
    expect(mocks.patch).toHaveBeenCalledWith(
      "/events/evt-1",
      expect.objectContaining({ image_url: "https://cdn.example/new.png" })
    )
    unmount()
    expect(revokeObjectUrl).toHaveBeenCalledWith("blob:preview")
    createObjectUrl.mockRestore()
    revokeObjectUrl.mockRestore()
  })

  it("reports save failures without closing the dialog", async () => {
    const user = userEvent.setup()
    const onClose = vi.fn()
    const onError = vi.fn()
    mocks.patch.mockRejectedValue(new Error("server unavailable"))
    renderDialog({ ...baseProps, onClose, onError })

    await user.click(screen.getByRole("button", { name: "common:buttons.save" }))

    await waitFor(() => expect(onError).toHaveBeenCalledWith("events:card.messages.saveFailure"))
    expect(onClose).not.toHaveBeenCalled()
  })

  it("updates localized fields and submits the complete edited draft", async () => {
    const user = userEvent.setup()
    renderDialog()

    const title = screen.getByLabelText("events:form.title_en")
    const location = screen.getByLabelText("events:form.location_en")
    await user.clear(title)
    await user.type(title, "Updated English title")
    await user.clear(location)
    await user.type(location, "Updated room")
    await user.click(screen.getByRole("button", { name: "common:buttons.save" }))

    await waitFor(() => expect(mocks.patch).toHaveBeenCalled())
    expect(mocks.patch).toHaveBeenCalledWith(
      "/events/evt-1",
      expect.objectContaining({
        title_en: "Updated English title",
        location_en: "Updated room",
      })
    )
  })

  it("resets edited values when cancelled without a parent remount", async () => {
    const user = userEvent.setup()
    const onClose = vi.fn()
    renderDialog({ ...baseProps, onClose })

    const title = screen.getByLabelText("events:form.title_en")
    await user.clear(title)
    await user.type(title, "Unsaved title")
    await user.click(screen.getByRole("button", { name: "common:buttons.cancel" }))

    expect(onClose).toHaveBeenCalledOnce()
    expect(title).toHaveValue(baseEvent.title)
  })

  it("keeps the save action disabled while the patch request is pending", async () => {
    let resolvePatch!: (value: unknown) => void
    const pendingPatch = new Promise((resolve) => {
      resolvePatch = resolve
    })
    mocks.patch.mockImplementationOnce(() => pendingPatch)
    const user = userEvent.setup()
    renderDialog()

    const saveButton = screen.getByRole("button", { name: "common:buttons.save" })
    await user.click(saveButton)
    expect(saveButton).toBeDisabled()

    resolvePatch({ data: {} })
    await waitFor(() => expect(mocks.patch).toHaveBeenCalledOnce())
  })

  it("reports image upload failures and does not issue a patch", async () => {
    const user = userEvent.setup()
    const onError = vi.fn()
    const createObjectUrl = vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:failed")
    const revokeObjectUrl = vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => undefined)
    mocks.uploadEventImage.mockRejectedValueOnce(new Error("upload failed"))

    try {
      renderDialog({ ...baseProps, onError })
      const input = document.querySelector<HTMLInputElement>('input[type="file"]')!
      await user.upload(input, new File(["image"], "failed.png", { type: "image/png" }))
      await user.click(screen.getByRole("button", { name: "common:buttons.save" }))

      await waitFor(() => expect(onError).toHaveBeenCalledWith("events:card.messages.saveFailure"))
      expect(mocks.patch).not.toHaveBeenCalled()
    } finally {
      createObjectUrl.mockRestore()
      revokeObjectUrl.mockRestore()
    }
  })
})
