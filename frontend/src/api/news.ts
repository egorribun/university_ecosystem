import * as v from "valibot"

import {
  createNewsApiV1NewsPost,
  deleteNewsApiV1NewsIdDelete,
  getNewsApiV1NewsIdGet,
  newsListApiV1NewsGet,
  updateNewsApiV1NewsIdPatch,
  uploadNewsImageApiV1NewsUploadImagePost,
} from "@/api/generated"
import type { NewsCreate, NewsOut, NewsUpdate } from "@/api/generated"
import { ensureValidResponse } from "./validation"

export type NewsItem = NewsOut

type FetchNewsOptions = {
  ifNoneMatch?: string | null
  signal?: AbortSignal
}

type FetchNewsItemOptions = {
  ifNoneMatch?: string | null
  signal?: AbortSignal
}

export type CreateNewsPayload = NewsCreate
export type UpdateNewsPayload = NewsUpdate | null

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
  newsListApiV1NewsGet({
    headers: ifNoneMatch ? { "if-none-match": ifNoneMatch } : undefined,
    signal,
    // @ts-ignore - axios config extension
    validateStatus: (status: number) => status === 304 || (status >= 200 && status < 300),
  })

export const fetchNewsItem = async (
  id: string,
  { ifNoneMatch, signal }: FetchNewsItemOptions = {}
) => {
  const response = await getNewsApiV1NewsIdGet({
    path: { id },
    headers: ifNoneMatch ? { "if-none-match": ifNoneMatch } : undefined,
    signal,
    // @ts-ignore - axios config extension
    validateStatus: (status: number) => status === 304 || (status >= 200 && status < 300),
  })
  if (response.status !== 304) {
    applyParsedData(response, newsItemSchema, "GET /api/v1/news/{id}")
  }
  return response
}

export const createNews = async (payload: CreateNewsPayload) => {
  const response = await createNewsApiV1NewsPost({
    body: payload,
  })
  applyParsedData(response, newsItemSchema, "POST /api/v1/news")
  return response
}

export const updateNews = async (id: string, payload: UpdateNewsPayload) => {
  const response = await updateNewsApiV1NewsIdPatch({
    path: { id },
    body: payload ?? undefined,
  })
  applyParsedData(response, newsItemSchema, "PATCH /api/v1/news/{id}")
  return response
}

export const deleteNews = (id: string) =>
  deleteNewsApiV1NewsIdDelete({
    path: { id },
  })

export const uploadNewsImage = async (file: File) => {
  const response = await uploadNewsImageApiV1NewsUploadImagePost({
    body: { file },
  })
  const parsed = ensureValidResponse(
    newsUploadResponseSchema,
    response.data,
    "POST /api/v1/news/upload_image"
  )
  return parsed.url
}
