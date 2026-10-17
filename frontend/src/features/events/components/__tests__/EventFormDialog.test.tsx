import { act, render } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import type { CreateEventPayload } from "@/api/events"

type CapturedProps = {
  open: boolean
  onClose: () => void
  onCreated: (draft: CreateEventPayload) => Promise<void>
  language: "ru" | "en"
}

const mocks = vi.hoisted(() => ({
  props: undefined as CapturedProps | undefined,
  createEvent: vi.fn(),
  logError: vi.fn(),
}))

vi.mock("@/components/events/EventCreateDialog", () => ({
  EventCreateDialog: (props: CapturedProps) => {
    mocks.props = props
    return <div data-testid="event-create-dialog" />
  },
}))

vi.mock("@/api/events", () => ({ createEvent: mocks.createEvent }))
vi.mock("@/app/logger", () => ({ logError: mocks.logError }))

import { EventFormDialog } from "@/features/events/components/EventFormDialog"

const draft: CreateEventPayload = {
  title: "Runtime event",
  starts_at: "2026-08-14T10:00:00Z",
  ends_at: "2026-08-14T11:00:00Z",
}

describe("EventFormDialog", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.props = undefined
  })

  it("forwards dialog props and preserves the current scroll anchor after creation", async () => {
    const onClose = vi.fn()
    const onSuccess = vi.fn()
    const scrollTo = vi.spyOn(window, "scrollTo").mockImplementation(() => undefined)
    mocks.createEvent.mockResolvedValue({ id: "event-1" })

    render(<EventFormDialog open onClose={onClose} onSuccess={onSuccess} language="en" />)

    expect(mocks.props).toMatchObject({ open: true, onClose, language: "en" })
    await act(async () => mocks.props?.onCreated(draft))

    expect(mocks.createEvent).toHaveBeenCalledWith(draft)
    expect(onClose).not.toHaveBeenCalled()
    expect(onSuccess).toHaveBeenCalledOnce()
    expect(scrollTo).not.toHaveBeenCalled()
  })

  it("logs a creation failure and keeps the dialog open", async () => {
    const error = new Error("backend unavailable")
    const onClose = vi.fn()
    const onSuccess = vi.fn()
    mocks.createEvent.mockRejectedValue(error)

    render(<EventFormDialog open onClose={onClose} onSuccess={onSuccess} language="ru" />)
    const onCreated = mocks.props?.onCreated
    expect(onCreated).toBeDefined()
    await expect(onCreated?.(draft)).rejects.toBe(error)

    expect(mocks.logError).toHaveBeenCalledWith("[EventFormDialog] createEvent failed:", error)
    expect(onClose).not.toHaveBeenCalled()
    expect(onSuccess).not.toHaveBeenCalled()
  })

  it("does not turn a post-create refresh error into a create failure", async () => {
    const refreshError = new Error("refresh unavailable")
    const onClose = vi.fn()
    const onSuccess = vi.fn(async () => {
      throw refreshError
    })
    mocks.createEvent.mockResolvedValue({ id: "event-2" })

    render(<EventFormDialog open onClose={onClose} onSuccess={onSuccess} language="en" />)
    await expect(mocks.props?.onCreated(draft)).resolves.toBeUndefined()

    expect(mocks.createEvent).toHaveBeenCalledWith(draft)
    expect(onSuccess).toHaveBeenCalledOnce()
    expect(mocks.logError).toHaveBeenCalledWith(
      "[EventFormDialog] refresh after create failed:",
      refreshError
    )
    expect(onClose).not.toHaveBeenCalled()
  })
})
