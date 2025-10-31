import type { AxiosResponse } from "axios"
import { describe, it, expectTypeOf } from "vitest"

import type { paths } from "@/api/generated/schema"
import { createEvent, uploadEventImage, type CreateEventPayload } from "@/api/events"
import { createNews, fetchNews, uploadNewsImage, type CreateNewsPayload } from "@/api/news"
import { fetchNotificationsList, type NotificationsListResult } from "@/api/notifications"

describe("typed api client", () => {
  it("fetchNews matches schema", () => {
    type Expected = AxiosResponse<
      paths["/news"]["get"]["responses"]["200"]["content"]["application/json"]
    >
    expectTypeOf<ReturnType<typeof fetchNews>>().toEqualTypeOf<Promise<Expected>>()
  })

  it("createNews payload aligns with schema", () => {
    expectTypeOf<Parameters<typeof createNews>[0]>().toEqualTypeOf<CreateNewsPayload>()
  })

  it("uploadNewsImage returns a string", () => {
    expectTypeOf<ReturnType<typeof uploadNewsImage>>().toEqualTypeOf<Promise<string>>()
  })

  it("createEvent payload aligns with schema", () => {
    expectTypeOf<Parameters<typeof createEvent>[0]>().toEqualTypeOf<CreateEventPayload>()
  })

  it("uploadEventImage returns a string", () => {
    expectTypeOf<ReturnType<typeof uploadEventImage>>().toEqualTypeOf<Promise<string>>()
  })

  it("notifications list matches schema", () => {
    expectTypeOf<ReturnType<typeof fetchNotificationsList>>().toEqualTypeOf<
      Promise<NotificationsListResult>
    >()
  })
})
