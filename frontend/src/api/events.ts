import * as v from "valibot"

import type { components } from "@/api/generated/schema"
import { apiClient } from "./client"
import { ensureValidResponse } from "./validation"

export type CreateEventPayload = components["schemas"]["EventCreate"]

const uploadResponseSchema = v.object({ url: v.pipe(v.string(), v.trim(), v.minLength(1)) })

export const createEvent = (payload: CreateEventPayload) =>
  apiClient.post("/api/v1/events", payload)

export const uploadEventImage = async (file: File) => {
  const formData = new FormData()
  formData.append("file", file)
  const response = await apiClient.post("/api/v1/events/upload_image", formData, {
    headers: { "Content-Type": "multipart/form-data" },
  })
  const parsed = ensureValidResponse(
    uploadResponseSchema,
    response.data,
    "POST /api/v1/events/upload_image"
  )
  return parsed.url
}
