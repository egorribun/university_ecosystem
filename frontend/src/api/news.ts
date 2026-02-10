import { z } from "zod"

import type { components, paths } from "@/api/generated/schema"
import { apiClient } from "./client"
import { ensureValidResponse } from "./validation"

export type NewsItem = components["schemas"]["NewsOut"]

type NewsListResponse =
  paths["/api/v1/news"]["get"]["responses"]["200"]["content"]["application/json"]

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

const newsUploadResponseSchema = z.object({ url: z.string().trim().min(1) })

const applyParsedData = <T>(response: { data: unknown }, schema: z.ZodType<T>, context: string) => {
  const parsed = ensureValidResponse(schema, response.data, context)
  ;(response as { data: T }).data = parsed
}

const newsItemSchema = z.object({
  id: z.string().uuid(),
  title: z.string(),
  content: z.string(),
  created_at: z.string(),
  title_en: z.string().nullable().optional(),
  content_en: z.string().nullable().optional(),
  image_url: z.string().nullable().optional(),
  image_url_optimized: z.string().nullable(),
  likes_count: z.number().default(0),
  comments_count: z.number().default(0),
  is_liked: z.boolean().default(false),
})

const newsListSchema = z.array(newsItemSchema)

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
