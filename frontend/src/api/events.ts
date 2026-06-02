import * as v from "valibot"

import {
  createEventApiV1EventsPost,
  uploadEventImageApiV1EventsUploadImagePost,
} from "@/api/generated"
import type { EventCreate } from "@/api/generated"
import { ensureValidResponse } from "./validation"

export type CreateEventPayload = EventCreate

const uploadResponseSchema = v.object({ url: v.pipe(v.string(), v.trim(), v.minLength(1)) })

export const createEvent = async (payload: CreateEventPayload) => {
  const { data } = await createEventApiV1EventsPost({ body: payload })
  return data
}

export const uploadEventImage = async (file: File, eventId?: string | number) => {
  const { data } = await uploadEventImageApiV1EventsUploadImagePost({
    body: { file, event_id: eventId ?? 0 },
  })
  const parsed = ensureValidResponse(uploadResponseSchema, data, "POST /api/v1/events/upload_image")
  return parsed.url
}
