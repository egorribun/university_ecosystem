import { z } from "zod"

import type { components, paths } from "@/api/generated/schema"
import api from "./client"
import { ensureValidResponse } from "./validation"

export type NewsItem = components["schemas"]["NewsOut"]

type NewsListResponse = paths["/news"]["get"]["responses"]["200"]["content"]["application/json"]

type FetchNewsOptions = {
  ifNoneMatch?: string | null
  signal?: AbortSignal
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

export const parseNewsList = (data: unknown) => ensureValidResponse(newsListSchema, data, "GET /news")

export const fetchNews = ({ ifNoneMatch, signal }: FetchNewsOptions = {}) =>
  api.get<NewsListResponse>("/news", {
    headers: ifNoneMatch ? { "If-None-Match": ifNoneMatch } : undefined,
    signal,
    validateStatus: (status) => status === 304 || (status >= 200 && status < 300),
  })
