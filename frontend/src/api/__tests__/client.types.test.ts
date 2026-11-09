import { HttpResponse, http } from "msw"
import { describe, expect, it, expectTypeOf } from "vitest"

import type { NewsOut, PaginatedNews } from "@/api/generated"
import { createEvent, uploadEventImage, type CreateEventPayload } from "@/api/events"
import {
  createNews,
  fetchNews,
  fetchNewsItem,
  uploadNewsImage,
  type CreateNewsPayload,
} from "@/api/news"
import { fetchNotificationsList, type NotificationsListResult } from "@/api/notifications"
import { server } from "@/tests/mocks/server"

describe("typed api client", () => {
  it("fetchNews matches schema", async () => {
    const expectedPage = {
      items: [
        {
          id: "00000000-0000-0000-0000-000000000001",
          title: "Campus news",
          content: "Article content",
          created_at: "2026-01-15T10:00:00.000Z",
        },
      ],
      has_more: false,
      next_cursor: null,
    } satisfies PaginatedNews
    let requests = 0
    server.use(
      http.get("*/api/v1/news", () => {
        requests += 1
        return HttpResponse.json(expectedPage)
      })
    )

    const result = await fetchNews()
    expect(requests).toBe(1)
    expect(result.status).toBe(200)
    expect(result.data).toStrictEqual(expectedPage)
    expectTypeOf(result.data).toEqualTypeOf<PaginatedNews | undefined>()
  })

  it("fetchNewsItem matches schema", async () => {
    const result = await fetchNewsItem("id")
    expectTypeOf(result.data).toMatchTypeOf<NewsOut | undefined>()
  })

  it("createNews payload aligns with schema", () => {
    expectTypeOf<Parameters<typeof createNews>[0]>().toEqualTypeOf<CreateNewsPayload>()
  })

  it("uploadNewsImage returns a string", () => {
    expectTypeOf<ReturnType<typeof uploadNewsImage>>().resolves.toEqualTypeOf<string>()
  })

  it("createEvent payload aligns with schema", () => {
    expectTypeOf<Parameters<typeof createEvent>[0]>().toEqualTypeOf<CreateEventPayload>()
  })

  it("uploadEventImage returns a string", () => {
    expectTypeOf<ReturnType<typeof uploadEventImage>>().resolves.toEqualTypeOf<string>()
  })

  it("notifications list matches schema", () => {
    expectTypeOf<
      ReturnType<typeof fetchNotificationsList>
    >().resolves.toEqualTypeOf<NotificationsListResult>()
  })
})
