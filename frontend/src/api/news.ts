import * as v from "valibot"

import type { components } from "@/api/generated/schema"
import { apiClient } from "./client"
import { ensureValidResponse } from "./validation"

export type NewsItem = components["schemas"]["NewsOut"]

type FetchNewsOptions = {
  ifNoneMatch?: string | null
  signal?: AbortSignal
}

type FetchNewsItemOptions = {
  ifNoneMatch?: string | null
  signal?: AbortSignal
}

export type CreateNewsPayload = components["schemas"]["NewsCreate"]
export type UpdateNewsPayload = components["schemas"]["NewsUpdate"] | null

const newsUploadResponseSchema = v.object({ url: v.pipe(v.string(), v.trim(), v.minLength(1)) })

const applyParsedData = <T extends v.GenericSchema<unknown, unknown>>(response: { data: unknown }, schema: T, context: string) => {
  const parsed = ensureValidResponse(schema, response.data, context)
  ;(response as { data: v.InferOutput<T> }).data = parsed
}

const newsItemSchema = v.object({
  id: v.pipe(v.string(), v.uuid()),
  title: v.string(),
  content: v.string(),
  created_at: v.string(), // datetime as string
  title_en: v.optional(v.nullable(v.string())),
  content_en: v.optional(v.nullable(v.string())),
  image_url: v.optional(v.nullable(v.string())),
  image_url_optimized: v.nullable(v.string()), // computed_field is usually present but can be null
  likes_count: v.optional(v.number(), 0),
  comments_count: v.optional(v.number(), 0),
  is_liked: v.optional(v.boolean(), false),
})

const newsListSchema = v.array(newsItemSchema)

export const parseNewsList = (data: unknown) =>
  ensureValidResponse(newsListSchema, data, "GET /api/v1/news")

export const fetchNews = ({ ifNoneMatch, signal }: FetchNewsOptions = {}) =>
  apiClient.get("/api/v1/news", {
    headers: ifNoneMatch ? { "if-none-match": ifNoneMatch } : undefined,
    signal,
    validateStatus: (status) => status === 304 || (status >= 200 && status < 300),
  })

export const fetchNewsItem = async (
  id: string,
  { ifNoneMatch, signal }: FetchNewsItemOptions = {}
) => {
  const response = await apiClient.get("/api/v1/news/{id}", {
    pathParams: { id },
    headers: ifNoneMatch ? { "if-none-match": ifNoneMatch } : undefined,
    signal,
    validateStatus: (status) => status === 304 || (status >= 200 && status < 300),
  })
  if (response.status !== 304) {
    applyParsedData(response, newsItemSchema, "GET /api/v1/news/{id}")
  }
  return response
}

export const createNews = async (payload: CreateNewsPayload) => {
  const response = await apiClient.post("/api/v1/news", payload)
  applyParsedData(response, newsItemSchema, "POST /api/v1/news")
  return response
}

export const updateNews = async (id: string, payload: UpdateNewsPayload) => {
  const response = await apiClient.patch("/api/v1/news/{id}", payload ?? undefined, {
    pathParams: { id },
  })
  applyParsedData(response, newsItemSchema, "PATCH /api/v1/news/{id}")
  return response
}

export const deleteNews = (id: string) =>
  apiClient.delete("/api/v1/news/{id}", {
    pathParams: { id },
  })

export const uploadNewsImage = async (file: File) => {
  const formData = new FormData()
  formData.append("file", file)
  const response = await apiClient.post("/api/v1/news/upload_image", formData, {
    headers: { "Content-Type": "multipart/form-data" },
  })
  const parsed = ensureValidResponse(
    newsUploadResponseSchema,
    response.data,
    "POST /api/v1/news/upload_image"
  )
  return parsed.url
}
