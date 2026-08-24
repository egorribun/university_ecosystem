import { beforeEach, describe, expect, it, vi } from "vitest"

const generated = vi.hoisted(() => ({
  createEvent: vi.fn(),
  uploadEventImage: vi.fn(),
}))

vi.mock("@/api/generated", () => ({
  createEventApiV1EventsPost: generated.createEvent,
  uploadEventImageApiV1EventsUploadImagePost: generated.uploadEventImage,
}))

import { ApiResponseValidationError } from "@/api/validation"
import { createEvent, uploadEventImage, type CreateEventPayload } from "@/api/events"

const payload: CreateEventPayload = {
  title: "Coverage lecture",
  starts_at: "2026-08-14T10:00:00Z",
  ends_at: "2026-08-14T11:00:00Z",
}

describe("event API runtime contract", () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it("forwards an event draft and returns the generated client payload", async () => {
    const created = { id: "event-1", ...payload }
    generated.createEvent.mockResolvedValue({ data: created })

    await expect(createEvent(payload)).resolves.toEqual(created)
    expect(generated.createEvent).toHaveBeenCalledWith({ body: payload })
  })

  it.each([
    [undefined, 0],
    ["event-2", "event-2"],
    [17, 17],
  ])("uploads an image using event id %s", async (eventId, expectedEventId) => {
    const file = new File(["image"], "event.webp", { type: "image/webp" })
    generated.uploadEventImage.mockResolvedValue({ data: { url: " https://cdn.test/e.webp " } })

    await expect(uploadEventImage(file, eventId)).resolves.toBe("https://cdn.test/e.webp")
    expect(generated.uploadEventImage).toHaveBeenCalledWith({
      body: { file, event_id: expectedEventId },
    })
  })

  it("rejects malformed upload responses instead of leaking invalid data", async () => {
    const file = new File(["image"], "event.webp", { type: "image/webp" })
    generated.uploadEventImage.mockResolvedValue({ data: { url: "   " } })

    await expect(uploadEventImage(file)).rejects.toBeInstanceOf(ApiResponseValidationError)
  })
})
