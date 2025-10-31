import { z } from "zod"

import type { components, paths } from "@/api/generated/schema"
import { apiClient } from "./client"
import { ensureValidResponse } from "./validation"

export type NewsItem = components["schemas"]["NewsOut"]

type NewsListResponse = paths["/news"]["get"]["responses"]["200"]["content"]["application/json"]

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

const applyParsedData = <T>(
  response: { data: unknown },
  schema: z.ZodType<T>,
  context: string
) => {
  const parsed = ensureValidResponse(schema, response.data, context)
  ;(response as { data: T }).data = parsed
}

const newsItemSchema: z.ZodType<NewsItem> = z.object({
  id: z.number(),
  title: z.string(),
  content: z.string(),
  created_at: z.string(),
  title_en: z.string().nullable().optional(),
  content_en: z.string().nullable().optional(),
  image_url: z.string().nullable().optional(),
})

const newsListSchema = z.array(newsItemSchema)

export const parseNewsList = (data: unknown) =>
  ensureValidResponse(newsListSchema, data, "GET /news")

export const fetchNews = ({ ifNoneMatch, signal }: FetchNewsOptions = {}) =>
  apiClient.get("/news", {
    headers: ifNoneMatch ? { "if-none-match": ifNoneMatch } : undefined,
    signal,
    validateStatus: (status) => status === 304 || (status >= 200 && status < 300),
  })

export const fetchNewsItem = async (
  id: number,
  { ifNoneMatch, signal }: FetchNewsItemOptions = {}
) => {
  const response = await apiClient.get("/news/{id}", {
    pathParams: { id },
    headers: ifNoneMatch ? { "if-none-match": ifNoneMatch } : undefined,
    signal,
    validateStatus: (status) => status === 304 || (status >= 200 && status < 300),
  })
  if (response.status !== 304) {
    applyParsedData(response, newsItemSchema, "GET /news/{id}")
  }
  return response
}

export const createNews = async (payload: CreateNewsPayload) => {
  const response = await apiClient.post("/news", payload)
  applyParsedData(response, newsItemSchema, "POST /news")
  return response
}

export const updateNews = async (id: number, payload: UpdateNewsPayload) => {
  const response = await apiClient.patch("/news/{id}", payload ?? undefined, {
    pathParams: { id },
  })
  applyParsedData(response, newsItemSchema, "PATCH /news/{id}")
  return response
}

export const deleteNews = (id: number) =>
  apiClient.delete("/news/{id}", {
    pathParams: { id },
  })

export const uploadNewsImage = async (file: File) => {
  const formData = new FormData()
  formData.append("file", file)
  const response = await apiClient.post("/news/upload_image", formData, {
    headers: { "Content-Type": "multipart/form-data" },
  })
  const parsed = ensureValidResponse(newsUploadResponseSchema, response.data, "POST /news/upload_image")
  return parsed.url
}
