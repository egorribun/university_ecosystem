import { beforeEach, describe, expect, it, vi } from "vitest"

const { createNews, deleteNews, getNews, listNews, updateNews, uploadNewsImage } = vi.hoisted(
  () => ({
    createNews: vi.fn(),
    deleteNews: vi.fn(),
    getNews: vi.fn(),
    listNews: vi.fn(),
    updateNews: vi.fn(),
    uploadNewsImage: vi.fn(),
  })
)

vi.mock("@/api/generated", () => ({
  createNewsApiV1NewsPost: createNews,
  deleteNewsApiV1NewsIdDelete: deleteNews,
  getNewsApiV1NewsIdGet: getNews,
  newsListApiV1NewsGet: listNews,
  updateNewsApiV1NewsIdPatch: updateNews,
  uploadNewsImageApiV1NewsUploadImagePost: uploadNewsImage,
}))

import {
  createNews as createNewsItem,
  deleteNews as deleteNewsItem,
  fetchNews,
  fetchNewsItem,
  parseNewsList,
  updateNews as updateNewsItem,
  uploadNewsImage as uploadNewsImageItem,
} from "@/api/news"

const news = {
  id: "00000000-0000-0000-0000-000000000001",
  title: "News",
  content: "Content",
  created_at: "2026-01-15T10:00:00.000Z",
  title_en: null,
  content_en: null,
  image_url: null,
  image_url_optimized: null,
  likes_count: 0,
  comments_count: 0,
  is_liked: false,
}

beforeEach(() => {
  listNews.mockReset()
  getNews.mockReset()
  createNews.mockReset()
  updateNews.mockReset()
  deleteNews.mockReset()
  uploadNewsImage.mockReset()
})

describe("api/news closure", () => {
  it("parses valid lists and rejects invalid response data", () => {
    expect(parseNewsList([news])).toEqual([news])
    expect(() => parseNewsList([{ id: "not-a-uuid" }])).toThrow()
  })

  it("passes conditional headers/signals and validates the fetch status branches", async () => {
    const signal = new AbortController().signal
    listNews.mockResolvedValue({ status: 200, data: [news] })
    await expect(fetchNews({ ifNoneMatch: "etag-1", signal })).resolves.toEqual({
      status: 200,
      data: [news],
    })
    const request = listNews.mock.calls[0]?.[0] as {
      headers: Record<string, string>
      signal: AbortSignal
      validateStatus: (status: number) => boolean
    }
    expect(request.headers).toEqual({ "if-none-match": "etag-1" })
    expect(request.signal).toBe(signal)
    expect(request.validateStatus(304)).toBe(true)
    expect(request.validateStatus(200)).toBe(true)
    expect(request.validateStatus(299)).toBe(true)
    expect(request.validateStatus(199)).toBe(false)
    expect(request.validateStatus(300)).toBe(false)

    listNews.mockResolvedValue({ status: 304, data: undefined })
    await expect(fetchNews()).resolves.toEqual({ status: 304, data: undefined })
    expect(listNews.mock.calls[1]?.[0]).toEqual(
      expect.objectContaining({ headers: undefined, signal: undefined })
    )
  })

  it("parses non-304 item responses and skips parsing for 304 responses", async () => {
    const signal = new AbortController().signal
    getNews.mockResolvedValueOnce({ status: 200, data: { ...news } })
    const item = await fetchNewsItem("00000000-0000-0000-0000-000000000001", {
      ifNoneMatch: "etag-2",
      signal,
    })
    expect(item.data).toEqual(news)
    expect(getNews).toHaveBeenCalledWith(
      expect.objectContaining({
        path: { id: "00000000-0000-0000-0000-000000000001" },
        headers: { "if-none-match": "etag-2" },
        signal,
        throwOnError: true,
      })
    )
    const itemRequest = getNews.mock.calls[0]?.[0] as {
      validateStatus: (status: number) => boolean
    }
    expect(itemRequest.validateStatus(304)).toBe(true)
    expect(itemRequest.validateStatus(200)).toBe(true)
    expect(itemRequest.validateStatus(500)).toBe(false)

    getNews.mockResolvedValueOnce({ status: 304, data: "cached" })
    await expect(fetchNewsItem("news-304")).resolves.toEqual({ status: 304, data: "cached" })
  })

  it("validates create/update payloads and exposes delete responses", async () => {
    createNews.mockResolvedValue({ status: 201, data: { ...news } })
    updateNews.mockResolvedValue({ status: 200, data: { ...news } })
    deleteNews.mockResolvedValue({ status: 204, data: undefined })

    await expect(createNewsItem({ title: "News", content: "Content" } as never)).resolves.toEqual(
      expect.objectContaining({ status: 201, data: news })
    )
    await expect(updateNewsItem(news.id, null)).resolves.toEqual(
      expect.objectContaining({ status: 200, data: news })
    )
    await expect(deleteNewsItem(news.id)).resolves.toEqual({ status: 204, data: undefined })

    expect(createNews).toHaveBeenCalledWith(
      expect.objectContaining({ body: { title: "News", content: "Content" }, throwOnError: true })
    )
    expect(updateNews).toHaveBeenCalledWith(
      expect.objectContaining({ path: { id: news.id }, body: undefined, throwOnError: true })
    )
    expect(deleteNews).toHaveBeenCalledWith({ path: { id: news.id } })
  })

  it("keeps endpoint context in invalid mutation response errors", async () => {
    createNews.mockResolvedValue({ status: 201, data: { ...news, id: "not-a-uuid" } })
    await expect(createNewsItem({ title: "News", content: "Content" } as never)).rejects.toThrow(
      "Invalid API response for POST /api/v1/news"
    )

    updateNews.mockResolvedValue({ status: 200, data: { ...news, id: "not-a-uuid" } })
    await expect(updateNewsItem(news.id, null)).rejects.toThrow(
      "Invalid API response for PATCH /api/v1/news/{id}"
    )

    uploadNewsImage.mockResolvedValue({ data: { url: "   " } })
    await expect(uploadNewsImageItem(new File(["image"], "empty.png"))).rejects.toThrow(
      "Invalid API response for POST /api/v1/news/upload_image"
    )
  })

  it("trims valid upload URLs and rejects invalid upload payloads", async () => {
    uploadNewsImage.mockResolvedValueOnce({ data: { url: "  https://cdn.test/image.png  " } })
    await expect(uploadNewsImageItem(new File(["image"], "image.png"))).resolves.toBe(
      "https://cdn.test/image.png"
    )
    expect(uploadNewsImage).toHaveBeenCalledWith({ body: { file: expect.any(File) } })

    uploadNewsImage.mockResolvedValueOnce({ data: { url: "   " } })
    await expect(uploadNewsImageItem(new File(["image"], "empty.png"))).rejects.toThrow()
  })
})
