import { fireEvent, render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { beforeEach, describe, it, expect, vi } from "vitest"
import { waitFor } from "@testing-library/react"

vi.mock("framer-motion", async () =>
  (await import("@/tests/helpers/framerMotionMock")).framerMotionMock()
)
const { language, useTranslationMock } = vi.hoisted(() => {
  const currentLanguage = { current: "en" }
  return {
    language: currentLanguage,
    useTranslationMock: vi.fn(() => ({
      t: (key: string) => key,
      i18n: {
        get language() {
          return currentLanguage.current
        },
        changeLanguage: () => Promise.resolve(),
      },
    })),
  }
})
const { campusTimezone } = vi.hoisted(() => ({
  campusTimezone: { current: "America/New_York" as string | null },
}))
vi.mock("react-i18next", () => ({
  useTranslation: useTranslationMock,
}))
vi.mock("@/contexts/CampusTimezoneContext", () => ({
  useCampusTimezone: () => campusTimezone.current,
}))
const mocks = vi.hoisted(() => ({
  patch: vi.fn(),
  uploadEventImage: vi.fn(),
  logError: vi.fn(),
}))
vi.mock("@/api/events", () => ({ uploadEventImage: mocks.uploadEventImage }))
vi.mock("@/api/client", () => ({
  default: { patch: mocks.patch },
  resetEtagCache: vi.fn(),
  registerSigningKeyAccessor: vi.fn(),
}))
vi.mock("@/app/logger", () => ({ logError: mocks.logError }))

import {
  EventDetailEditDialog,
  normalizeLocalizedEditValue,
} from "@/components/events/EventDetailEditDialog"
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
    language.current = "en"
    campusTimezone.current = "America/New_York"
    mocks.patch.mockResolvedValue({ data: {} })
    mocks.uploadEventImage.mockResolvedValue("")
  })

  it("normalizes required localized title/location values deterministically", () => {
    expect(normalizeLocalizedEditValue("  Primary  ", "Fallback")).toBe("Primary")
    expect(normalizeLocalizedEditValue("   ", "  Fallback  ")).toBe("Fallback")
    expect(normalizeLocalizedEditValue(" ", "\t")).toBe("")
  })

  it("renders the edit dialog when open", () => {
    renderDialog()
    const dialog = screen.getByRole("dialog")
    expect(dialog).toBeInTheDocument()
    expect(dialog.querySelectorAll("input,textarea").length).toBeGreaterThan(0)
    expect(useTranslationMock).toHaveBeenCalledWith(["events", "common"])
    expect(screen.getByLabelText("events:form.title_en")).toHaveValue(baseEvent.title_en)
    expect(screen.getByLabelText("events:form.description_en")).toHaveValue("")
    expect(screen.getByLabelText("events:form.location_en")).toHaveValue("")
    expect(screen.getByLabelText("events:form.start")).toHaveValue("2026-06-15T10:00")
    expect(screen.getByLabelText("events:form.end")).toHaveValue("2026-06-15T12:00")
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
    expect(screen.getByLabelText("events:form.description_en")).toHaveValue("")
    expect(screen.getByLabelText("events:form.type_en")).toHaveValue("")
    expect(screen.getByLabelText("events:form.start")).toHaveValue("")
    expect(screen.getByLabelText("events:form.end")).toHaveValue("")
    expect(screen.getByLabelText("events:form.speaker")).toHaveValue("")

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

  it("preserves every localized value from a complete event payload", async () => {
    language.current = "ru"
    const localizedEvent = {
      ...baseEvent,
      title_en: "English title",
      description_en: "English description",
      event_type_en: "English type",
      location_en: "English room",
      starts_at: "2026-07-01T09:00:00Z",
      ends_at: "2026-07-01T10:00:00Z",
      speaker: "English speaker",
      about: "Russian about",
      about_en: "English about",
    }

    renderDialog({ ...baseProps, event: localizedEvent })
    expect(screen.getByLabelText("events:form.title")).toHaveValue(baseEvent.title)
    expect(screen.getByLabelText("events:form.description")).toHaveValue(baseEvent.description)
    expect(screen.getByLabelText("events:form.type")).toHaveValue(baseEvent.event_type)
    expect(screen.getByLabelText("events:form.location")).toHaveValue(baseEvent.location)
    expect(screen.getByLabelText("events:form.start")).toHaveValue("2026-07-01T05:00")
    expect(screen.getByLabelText("events:form.end")).toHaveValue("2026-07-01T06:00")
    expect(screen.getByLabelText("events:form.speaker")).toHaveValue("English speaker")

    const user = userEvent.setup()
    await user.click(screen.getByRole("button", { name: "common:buttons.save" }))
    await waitFor(() => expect(mocks.patch).toHaveBeenCalled())
    expect(mocks.patch).toHaveBeenCalledWith(
      "/events/evt-1",
      expect.objectContaining({
        title: baseEvent.title,
        title_en: "English title",
        description: baseEvent.description,
        description_en: "English description",
        event_type: baseEvent.event_type,
        event_type_en: "English type",
        location: baseEvent.location,
        location_en: "English room",
        about: "Russian about",
        about_en: "English about",
        starts_at: localizedEvent.starts_at,
        ends_at: localizedEvent.ends_at,
      })
    )
  })

  it("omits localized source fields from English saves and excludes response id", async () => {
    const localizedEvent = {
      ...baseEvent,
      title: "Localized English title",
      title_en: "English source title",
      description: "Localized English description",
      description_en: "English source description",
      event_type: "English display type",
      event_type_en: "English source type",
      location: "English display location",
      location_en: "English source location",
      about: "Localized English about",
      about_en: "English source about",
    }
    renderDialog({ ...baseProps, event: localizedEvent })

    await userEvent.setup().click(screen.getByRole("button", { name: "common:buttons.save" }))
    await waitFor(() => expect(mocks.patch).toHaveBeenCalledOnce())
    const payload = mocks.patch.mock.calls[0]?.[1] as Record<string, unknown>
    expect(payload).toMatchObject({
      title_en: "English source title",
      description_en: "English source description",
      event_type_en: "English source type",
      location_en: "English source location",
      about_en: "English source about",
      starts_at: baseEvent.starts_at,
      ends_at: baseEvent.ends_at,
    })
    for (const field of ["id", "title", "description", "event_type", "location", "about"]) {
      expect(payload).not.toHaveProperty(field)
    }
  })

  it("serializes changed campus wall times to UTC and blocks a DST gap", async () => {
    const user = userEvent.setup()
    const editView = renderDialog()
    expect(screen.getByLabelText("events:form.start")).toHaveValue("2026-06-15T10:00")

    fireEvent.change(screen.getByLabelText("events:form.start"), {
      target: { value: "2026-06-16T10:30" },
    })
    fireEvent.change(screen.getByLabelText("events:form.end"), {
      target: { value: "2026-06-16T11:30" },
    })
    await user.click(screen.getByRole("button", { name: "common:buttons.save" }))
    await waitFor(() => expect(mocks.patch).toHaveBeenCalledOnce())
    expect(mocks.patch).toHaveBeenCalledWith(
      "/events/evt-1",
      expect.objectContaining({
        starts_at: "2026-06-16T14:30:00.000Z",
        ends_at: "2026-06-16T15:30:00.000Z",
      })
    )

    editView.unmount()
    mocks.patch.mockClear()
    const gapEvent = { ...baseEvent, starts_at: "2026-03-08T06:00:00.000Z" }
    const gapView = renderDialog({ ...baseProps, event: gapEvent })
    fireEvent.change(screen.getByLabelText("events:form.start"), {
      target: { value: "2026-03-08T02:30" },
    })
    expect(screen.getByText("events:form.errors.nonexistentCampusTime")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "common:buttons.save" })).toBeDisabled()
    expect(mocks.patch).not.toHaveBeenCalled()
    gapView.unmount()
  })

  it("blocks edit saves when the server campus timezone is unavailable", () => {
    campusTimezone.current = null
    renderDialog()
    expect(screen.getAllByText("events:form.errors.campusTimezoneUnavailable")).toHaveLength(2)
    expect(screen.getByRole("button", { name: "common:buttons.save" })).toBeDisabled()
  })

  it("preserves non-null optional description and type values while normalizing nulls", async () => {
    language.current = "ru"
    const localizedEvent = {
      ...baseEvent,
      description: "Russian description",
      description_en: "English description",
      event_type: "lecture",
      event_type_en: "Lecture",
    }
    renderDialog({ ...baseProps, event: localizedEvent })

    expect(screen.getByLabelText("events:form.description")).toHaveValue("Russian description")
    expect(screen.getByLabelText("events:form.type")).toHaveValue("lecture")

    const user = userEvent.setup()
    await user.click(screen.getByRole("button", { name: "common:buttons.save" }))
    await waitFor(() => expect(mocks.patch).toHaveBeenCalledOnce())
    expect(mocks.patch).toHaveBeenCalledWith(
      "/events/evt-1",
      expect.objectContaining({
        description: "Russian description",
        event_type: "lecture",
      })
    )
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
    const invalidateQueries = vi.spyOn(QueryClient.prototype, "invalidateQueries")
    try {
      renderDialog({ ...baseProps, onClose, onSuccess })

      await user.click(screen.getByRole("button", { name: "common:buttons.save" }))

      await waitFor(() =>
        expect(onSuccess).toHaveBeenCalledWith("events:card.messages.saveSuccess")
      )
      expect(mocks.patch).toHaveBeenCalledWith(
        "/events/evt-1",
        expect.objectContaining({ image_url: baseEvent.image_url })
      )
      const payload = mocks.patch.mock.calls[0]?.[1] as Record<string, unknown>
      expect(payload).not.toHaveProperty("id")
      expect(onClose).toHaveBeenCalledOnce()
      expect(invalidateQueries).toHaveBeenNthCalledWith(1, {
        queryKey: ["events", "detail", baseEvent.id],
      })
      expect(invalidateQueries).toHaveBeenNthCalledWith(2, { queryKey: ["events", "list"] })
    } finally {
      invalidateQueries.mockRestore()
    }
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

  it("exposes image upload pending state and clears it after the upload resolves", async () => {
    let resolveUpload!: (url: string) => void
    let resolvePatch!: (value: unknown) => void
    mocks.patch.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolvePatch = resolve
        })
    )
    mocks.uploadEventImage.mockReturnValueOnce(
      new Promise<string>((resolve) => {
        resolveUpload = resolve
      })
    )
    const user = userEvent.setup()
    const createObjectUrl = vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:pending")
    const revokeObjectUrl = vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => undefined)
    try {
      renderDialog()
      const input = document.querySelector<HTMLInputElement>('input[type="file"]')!
      await user.upload(input, new File(["image"], "pending.png", { type: "image/png" }))
      await user.click(screen.getByRole("button", { name: "common:buttons.save" }))
      await waitFor(() => expect(screen.getByText("common:statuses.uploading")).toBeInTheDocument())

      resolveUpload("https://cdn.example/pending.png")
      await waitFor(() =>
        expect(screen.getByText("common:buttons.changePhoto")).toBeInTheDocument()
      )
      expect(mocks.uploadEventImage).toHaveBeenCalledOnce()
      expect(mocks.patch).toHaveBeenCalledWith(
        "/events/evt-1",
        expect.objectContaining({ image_url: "https://cdn.example/pending.png" })
      )
      expect(screen.getByAltText("events:alt.preview")).toHaveAttribute("src", "blob:pending")

      resolvePatch({ data: {} })
      await waitFor(() =>
        expect(screen.getByRole("button", { name: "common:buttons.save" })).toBeEnabled()
      )
    } finally {
      createObjectUrl.mockRestore()
      revokeObjectUrl.mockRestore()
    }
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
    expect(mocks.logError).toHaveBeenCalledWith(
      "[EventDetailEditDialog] Save failed:",
      expect.any(Error)
    )
    expect(screen.getByRole("button", { name: "common:buttons.save" })).toBeEnabled()
  })

  it("updates English fields without sending the path-only id or localized source fields", async () => {
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
    const update = mocks.patch.mock.calls.at(-1)?.[1] as Record<string, unknown>
    expect(update).not.toHaveProperty("id")
    expect(update).not.toHaveProperty("title")
    expect(update).not.toHaveProperty("description")
    expect(update).not.toHaveProperty("location")
    expect(update).not.toHaveProperty("event_type")
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

  it("discards a picked image and its preview when cancelled without a parent remount", async () => {
    const user = userEvent.setup()
    vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:discarded")
    vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => undefined)
    renderDialog()
    const fileInput = document.querySelector<HTMLInputElement>('input[type="file"]')!
    await user.upload(fileInput, new File(["image"], "cover.png", { type: "image/png" }))
    expect(screen.getByAltText("events:alt.preview")).toHaveAttribute("src", "blob:discarded")

    await user.click(screen.getByRole("button", { name: "common:buttons.cancel" }))

    expect(screen.getByAltText("events:alt.preview")).toHaveAttribute("src", baseEvent.image_url)
    await user.click(screen.getByRole("button", { name: "common:buttons.save" }))
    await waitFor(() => expect(mocks.patch).toHaveBeenCalledOnce())
    expect(mocks.uploadEventImage).not.toHaveBeenCalled()
    vi.restoreAllMocks()
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
    await waitFor(() => expect(saveButton).toBeEnabled())
  })

  it("refreshes the reset baseline when the event prop changes", async () => {
    const user = userEvent.setup()
    const { rerender } = renderDialog()
    const updatedEvent = {
      ...baseEvent,
      id: "evt-2",
      title_en: "Updated event title",
    }

    rerender(
      <QueryClientProvider
        client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
      >
        <EventDetailEditDialog {...baseProps} event={updatedEvent} />
      </QueryClientProvider>
    )
    await user.click(screen.getByRole("button", { name: "common:buttons.cancel" }))
    expect(screen.getByLabelText("events:form.title_en")).toHaveValue("Updated event title")
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
