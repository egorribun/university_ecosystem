import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { ApiResponseValidationError } from "../validation"

// Mock the generated SDK + the lazy-imported axios client so the api/notifications
// wrappers run against canned responses (no MSW / contract validator needed).
vi.mock("@/api/generated", () => ({
  adminGetUserTopicsApiV1PushAdminTopicsUserIdGet: vi.fn(),
  adminUpdateUserTopicsApiV1PushAdminTopicsUserIdPut: vi.fn(),
  checkScheduleAndGenerateApiV1NotificationsCheckSchedulePost: vi.fn(),
  clearNotificationsApiV1NotificationsDelete: vi.fn(),
  unsubscribeApiV1PushUnsubscribePost: vi.fn(),
  getPushTopicsApiV1PushTopicsGet: vi.fn(),
  getVapidPublicKeyApiV1PushVapidPublicKeyGet: vi.fn(),
  listNotificationsApiV1NotificationsGet: vi.fn(),
  markAllReadApiV1NotificationsReadAllPost: vi.fn(),
  markReadSingleApiV1NotificationsNotifIdReadPatch: vi.fn(),
  listNotificationDeadLetters: vi.fn(),
  purgeNotificationDeadLetters: vi.fn(),
  retryNotificationDeadLetters: vi.fn(),
  subscribeApiV1PushSubscribePost: vi.fn(),
  sendTestApiV1PushTestPost: vi.fn(),
}))

vi.mock("@/api/client", () => ({
  default: {},
}))

import * as gen from "@/api/generated"
import {
  checkSchedule,
  clearNotifications,
  deleteSubscription,
  fetchAdminUserTopics,
  fetchDeadLetterQueue,
  fetchNotificationsList,
  fetchPushTopics,
  getVapidPublicKey,
  markAllNotificationsRead,
  markNotificationRead,
  purgeDeadLetterJobs,
  retryDeadLetterJobs,
  saveSubscription,
  sendTest,
  updateAdminUserTopics,
} from "../notifications"

const UUID = "11111111-1111-4111-8111-111111111111"

const checkScheduleSuccess = {
  data: { items: [], unread_count: 0, has_more: false, next_cursor: null },
  status: 200,
  statusText: "OK",
  headers: {},
  config: { headers: {} },
  request: {},
  error: undefined,
}

beforeEach(() => {
  vi.clearAllMocks()
})

afterEach(() => {
  vi.clearAllMocks()
})

describe("fetchNotificationsList", () => {
  it("returns the validated list payload", async () => {
    vi.mocked(gen.listNotificationsApiV1NotificationsGet).mockResolvedValue({
      data: {
        items: [{ id: UUID, title: "Hi", created_at: "2026-06-01T00:00:00Z", read: false }],
        unread_count: 1,
        has_more: false,
        next_cursor: null,
      },
    } as never)

    const result = await fetchNotificationsList({ cursor: null, limit: 20 })
    expect(result.unread_count).toBe(1)
    expect(result.items[0]?.title).toBe("Hi")
    expect(gen.listNotificationsApiV1NotificationsGet).toHaveBeenCalledWith({
      query: { cursor: undefined, limit: 20 },
    })
  })

  it("throws on a schema-invalid payload", async () => {
    vi.mocked(gen.listNotificationsApiV1NotificationsGet).mockResolvedValue({
      data: { items: [], unread_count: "nope", has_more: false },
    } as never)
    await expect(fetchNotificationsList()).rejects.toBeInstanceOf(ApiResponseValidationError)
  })

  it("normalizes an omitted cursor while preserving an explicit limit", async () => {
    vi.mocked(gen.listNotificationsApiV1NotificationsGet).mockResolvedValue({
      data: { items: [], unread_count: 0, has_more: false, next_cursor: null },
    } as never)

    await fetchNotificationsList({ limit: 5 })
    expect(gen.listNotificationsApiV1NotificationsGet).toHaveBeenCalledWith({
      query: { cursor: undefined, limit: 5 },
    })
  })
})

describe("simple notification passthroughs", () => {
  it("markNotificationRead targets the path param", async () => {
    await markNotificationRead(UUID)
    expect(gen.markReadSingleApiV1NotificationsNotifIdReadPatch).toHaveBeenCalledWith({
      path: { notif_id: UUID },
    })
  })

  it("markAllNotificationsRead + clearNotifications delegate", async () => {
    await markAllNotificationsRead()
    await clearNotifications()
    expect(gen.markAllReadApiV1NotificationsReadAllPost).toHaveBeenCalledOnce()
    expect(gen.clearNotificationsApiV1NotificationsDelete).toHaveBeenCalledOnce()
  })

  it("checkSchedule forwards the lookahead default + override", async () => {
    vi.mocked(gen.checkScheduleAndGenerateApiV1NotificationsCheckSchedulePost).mockResolvedValue(
      checkScheduleSuccess as never
    )

    await expect(checkSchedule()).resolves.toBe(checkScheduleSuccess)
    expect(
      gen.checkScheduleAndGenerateApiV1NotificationsCheckSchedulePost
    ).toHaveBeenLastCalledWith({
      query: { lookahead_minutes: 15 },
    })
    await expect(checkSchedule(30)).resolves.toBe(checkScheduleSuccess)
    expect(
      gen.checkScheduleAndGenerateApiV1NotificationsCheckSchedulePost
    ).toHaveBeenLastCalledWith({
      query: { lookahead_minutes: 30 },
    })
  })

  it("checkSchedule rejects the error from a fulfilled SDK result", async () => {
    const error = {
      detail: [
        {
          loc: ["query", "lookahead_minutes"],
          msg: "Input should be greater than zero",
          type: "greater_than",
          input: 0,
        },
      ],
    }
    vi.mocked(gen.checkScheduleAndGenerateApiV1NotificationsCheckSchedulePost).mockResolvedValue({
      data: undefined,
      error,
      name: "AxiosError",
      message: "Request failed with status code 422",
      code: "ERR_BAD_REQUEST",
      config: { headers: {} },
      request: {},
      response: {
        data: error,
        status: 422,
        statusText: "Unprocessable Entity",
        headers: {},
        config: { headers: {} },
      },
      status: 422,
      isAxiosError: true,
      toJSON: () => ({}),
    } as never)

    await expect(checkSchedule()).rejects.toBe(error)
  })
})

describe("saveSubscription", () => {
  const goodSub = {
    endpoint: " https://push.example/x ",
    keys: { p256dh: " p ", auth: " a " },
  } as unknown as PushSubscriptionJSON

  it("trims fields, attaches topics, returns server data", async () => {
    vi.mocked(gen.subscribeApiV1PushSubscribePost).mockResolvedValue({
      data: { id: UUID, endpoint: "https://push.example/x" },
    } as never)
    const result = await saveSubscription(goodSub, ["system"])
    expect(result).toEqual({ id: UUID, endpoint: "https://push.example/x" })
    const body = vi.mocked(gen.subscribeApiV1PushSubscribePost).mock.calls[0]?.[0]?.body
    expect(body).toMatchObject({
      endpoint: "https://push.example/x",
      keys: { p256dh: "p", auth: "a" },
      topics: ["system"],
    })
  })

  it("passes an undefined user agent when the browser reports an empty value", async () => {
    const userAgent = vi.spyOn(navigator, "userAgent", "get").mockReturnValue("")
    vi.mocked(gen.subscribeApiV1PushSubscribePost).mockResolvedValue({
      data: { id: UUID, endpoint: "https://push.example/x" },
    } as never)

    try {
      await saveSubscription(goodSub)
      const body = vi.mocked(gen.subscribeApiV1PushSubscribePost).mock.calls[0]?.[0]?.body
      expect(body).toHaveProperty("user_agent", undefined)
    } finally {
      userAgent.mockRestore()
    }
  })

  it("throws on an incomplete payload (no network call)", async () => {
    await expect(
      saveSubscription({
        endpoint: "",
        keys: { p256dh: "", auth: "" },
      } as unknown as PushSubscriptionJSON)
    ).rejects.toThrow("Invalid push subscription payload")
    expect(gen.subscribeApiV1PushSubscribePost).not.toHaveBeenCalled()
  })

  it.each([
    ["missing endpoint", { keys: { p256dh: "p", auth: "a" } }],
    ["missing p256dh", { endpoint: "https://push.example/x", keys: { auth: "a" } }],
    ["missing auth", { endpoint: "https://push.example/x", keys: { p256dh: "p" } }],
  ])("rejects a subscription with %s", async (_label, value) => {
    await expect(saveSubscription(value as unknown as PushSubscriptionJSON)).rejects.toThrow(
      "Invalid push subscription payload"
    )
    expect(gen.subscribeApiV1PushSubscribePost).not.toHaveBeenCalled()
  })

  it("omits topics when the optional value is not an array", async () => {
    vi.mocked(gen.subscribeApiV1PushSubscribePost).mockResolvedValue({
      data: { id: UUID, endpoint: "https://push.example/x" },
    } as never)

    await saveSubscription(goodSub, "system" as unknown as string[])
    const body = vi.mocked(gen.subscribeApiV1PushSubscribePost).mock.calls[0]?.[0]?.body
    expect(body).not.toHaveProperty("topics")
  })

  it("throws when the server returns no data", async () => {
    vi.mocked(gen.subscribeApiV1PushSubscribePost).mockResolvedValue({ data: undefined } as never)
    await expect(saveSubscription(goodSub)).rejects.toThrow("Failed to save subscription")
  })
})

describe("deleteSubscription + sendTest", () => {
  it("deleteSubscription posts the endpoint", async () => {
    await deleteSubscription("https://push.example/y")
    expect(gen.unsubscribeApiV1PushUnsubscribePost).toHaveBeenCalledWith({
      body: { endpoint: "https://push.example/y" },
    })
  })

  it("sendTest returns data + throws when empty", async () => {
    vi.mocked(gen.sendTestApiV1PushTestPost).mockResolvedValue({ data: { sent: 2 } } as never)
    expect(await sendTest()).toEqual({ sent: 2 })
    vi.mocked(gen.sendTestApiV1PushTestPost).mockResolvedValue({ data: undefined } as never)
    await expect(sendTest()).rejects.toThrow("Failed to send test notification")
  })
})

describe("getVapidPublicKey null-normalization", () => {
  it("returns a trimmed non-empty key", async () => {
    vi.mocked(gen.getVapidPublicKeyApiV1PushVapidPublicKeyGet).mockResolvedValue({
      data: { publicKey: "  BJ_key  " },
    } as never)
    expect(await getVapidPublicKey()).toBe("BJ_key")
  })

  it("normalizes blank/missing to null", async () => {
    vi.mocked(gen.getVapidPublicKeyApiV1PushVapidPublicKeyGet).mockResolvedValue({
      data: { publicKey: "   " },
    } as never)
    expect(await getVapidPublicKey()).toBeNull()
    vi.mocked(gen.getVapidPublicKeyApiV1PushVapidPublicKeyGet).mockResolvedValue({
      data: { publicKey: null },
    } as never)
    expect(await getVapidPublicKey()).toBeNull()
  })

  it("rejects a malformed VAPID response with the endpoint context", async () => {
    vi.mocked(gen.getVapidPublicKeyApiV1PushVapidPublicKeyGet).mockResolvedValue({
      data: { publicKey: 42 },
    } as never)
    await expect(getVapidPublicKey()).rejects.toMatchObject({
      name: "ApiResponseValidationError",
      message: expect.stringContaining("GET /api/v1/push/vapid-public-key"),
    })
  })
})

describe("fetchPushTopics defaults", () => {
  it("fills has_preferences + updated_at defaults", async () => {
    vi.mocked(gen.getPushTopicsApiV1PushTopicsGet).mockResolvedValue({
      data: { allowed: ["system"], topics: ["system"] },
    } as never)
    const result = await fetchPushTopics()
    expect(result).toEqual({
      allowed: ["system"],
      topics: ["system"],
      has_preferences: false,
      updated_at: null,
    })
  })

  it("defaults an omitted topics array and optional preference metadata", async () => {
    vi.mocked(gen.getPushTopicsApiV1PushTopicsGet).mockResolvedValue({
      data: { allowed: ["system"] },
    } as never)
    await expect(fetchPushTopics()).resolves.toEqual({
      allowed: ["system"],
      topics: [],
      has_preferences: false,
      updated_at: null,
    })
  })
})

describe("admin topics", () => {
  it("fetchAdminUserTopics validates the response", async () => {
    vi.mocked(gen.adminGetUserTopicsApiV1PushAdminTopicsUserIdGet).mockResolvedValue({
      data: {
        user_id: UUID,
        email: "a@b.c",
        topics: ["system"],
        allowed_topics: ["system"],
        updated_at: null,
      },
    } as never)
    const result = await fetchAdminUserTopics(UUID)
    expect(result.email).toBe("a@b.c")
    expect(gen.adminGetUserTopicsApiV1PushAdminTopicsUserIdGet).toHaveBeenCalledWith({
      path: { user_id: UUID },
    })
  })

  it("reports the fetch endpoint when admin topic data is invalid", async () => {
    vi.mocked(gen.adminGetUserTopicsApiV1PushAdminTopicsUserIdGet).mockResolvedValue({
      data: { user_id: "not-a-uuid", email: "", topics: [], allowed_topics: [] },
    } as never)
    await expect(fetchAdminUserTopics(UUID)).rejects.toMatchObject({
      name: "ApiResponseValidationError",
      message: expect.stringContaining(`/api/v1/push/admin/topics/${UUID}`),
    })
  })

  it("updateAdminUserTopics sends the body + validates", async () => {
    vi.mocked(gen.adminUpdateUserTopicsApiV1PushAdminTopicsUserIdPut).mockResolvedValue({
      data: {
        user_id: UUID,
        email: "a@b.c",
        topics: ["events"],
        allowed_topics: ["events", "system"],
      },
    } as never)
    const result = await updateAdminUserTopics(UUID, ["events"])
    expect(result.topics).toEqual(["events"])
    expect(gen.adminUpdateUserTopicsApiV1PushAdminTopicsUserIdPut).toHaveBeenCalledWith({
      path: { user_id: UUID },
      body: { topics: ["events"] },
    })
  })

  it("reports the update endpoint when admin topic data is invalid", async () => {
    vi.mocked(gen.adminUpdateUserTopicsApiV1PushAdminTopicsUserIdPut).mockResolvedValue({
      data: { user_id: "not-a-uuid", email: "", topics: [], allowed_topics: [] },
    } as never)
    await expect(updateAdminUserTopics(UUID, ["events"])).rejects.toMatchObject({
      name: "ApiResponseValidationError",
      message: expect.stringContaining(`/api/v1/push/admin/topics/${UUID}`),
    })
  })
})

describe("dead-letter queue (generated client)", () => {
  it("fetchDeadLetterQueue validates + forwards params/signal", async () => {
    vi.mocked(gen.listNotificationDeadLetters).mockResolvedValue({
      data: { items: [], total: 0 },
    } as never)
    const controller = new AbortController()
    const result = await fetchDeadLetterQueue({ limit: 10, offset: 0 }, controller.signal)
    expect(result).toEqual({ items: [], total: 0 })
    expect(gen.listNotificationDeadLetters).toHaveBeenCalledWith({
      query: { limit: 10, offset: 0 },
      signal: controller.signal,
      throwOnError: true,
    })
  })

  it("retry + purge post the job ids", async () => {
    vi.mocked(gen.retryNotificationDeadLetters).mockResolvedValue({ data: {} } as never)
    vi.mocked(gen.purgeNotificationDeadLetters).mockResolvedValue({ data: {} } as never)
    await retryDeadLetterJobs(["j1"])
    await purgeDeadLetterJobs(["j2"])
    expect(gen.retryNotificationDeadLetters).toHaveBeenCalledWith({
      body: { job_ids: ["j1"] },
      throwOnError: true,
    })
    expect(gen.purgeNotificationDeadLetters).toHaveBeenCalledWith({
      body: { job_ids: ["j2"] },
      throwOnError: true,
    })
  })
})
