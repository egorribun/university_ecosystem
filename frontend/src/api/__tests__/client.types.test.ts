import { describe, it, expectTypeOf } from "vitest"

import type {
  NewsOut,
} from "@/api/generated"
import { createEvent, uploadEventImage, type CreateEventPayload } from "@/api/events"
import { createNews, fetchNews, fetchNewsItem, uploadNewsImage, type CreateNewsPayload } from "@/api/news"
import { fetchNotificationsList, type NotificationsListResult } from "@/api/notifications"

describe("typed api client", () => {
  it("fetchNews matches schema", async () => {
    const result = await fetchNews()
    expectTypeOf(result.data).toMatchTypeOf<unknown>()
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
    expectTypeOf<ReturnType<typeof fetchNotificationsList>>().resolves.toEqualTypeOf<
      NotificationsListResult
    >()
  })
})
