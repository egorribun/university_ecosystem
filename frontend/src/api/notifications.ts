import * as v from "valibot"

import {
  adminGetUserTopicsApiV1PushAdminTopicsUserIdGet,
  adminUpdateUserTopicsApiV1PushAdminTopicsUserIdPut,
  checkScheduleAndGenerateApiV1NotificationsCheckSchedulePost,
  clearNotificationsApiV1NotificationsDelete,
  unsubscribeApiV1PushUnsubscribePost,
  getPushTopicsApiV1PushTopicsGet,
  getVapidPublicKeyApiV1PushVapidPublicKeyGet,
  listNotificationsApiV1NotificationsGet,
  markAllReadApiV1NotificationsReadAllPost,
  markReadSingleApiV1NotificationsNotifIdReadPatch,
  subscribeApiV1PushSubscribePost,
  sendTestApiV1PushTestPost,
} from "@/api/generated"
import type {
  AdminUserTopicsResponse,
  PushSubscriptionResponse,
  PushTopicsResponse,
  SendTestNotificationResponse,
} from "@/types/notifications"
import { ensureValidResponse } from "./validation"

const notificationSchema = v.object({
  id: v.pipe(v.string(), v.uuid()),
  title: v.string(),
  body: v.optional(v.nullable(v.string())),
  title_en: v.optional(v.nullable(v.string())),
  body_en: v.optional(v.nullable(v.string())),
  type: v.optional(v.nullable(v.string())),
  url: v.optional(v.nullable(v.string())),
  created_at: v.string(),
  read: v.boolean(),
  read_at: v.optional(v.nullable(v.string())),
})

const notificationsListSchema = v.object({
  items: v.array(notificationSchema),
  unread_count: v.number(),
  has_more: v.boolean(),
  next_cursor: v.optional(v.nullable(v.string())),
})

const deadLetterJobSchema = v.object({
  id: v.string(),
  kind: v.string(),
  record_id: v.string(),
  locale: v.optional(v.nullable(v.string())),
  enqueued_at: v.string(),
  claimed_at: v.optional(v.nullable(v.string())),
  attempts: v.pipe(v.number(), v.integer()),
  last_error: v.optional(v.nullable(v.string())),
  next_retry_at: v.optional(v.nullable(v.string())),
})

const deadLetterListSchema = v.object({
  items: v.array(deadLetterJobSchema),
  total: v.pipe(v.number(), v.integer()),
})

export type NotificationEntry = v.InferOutput<typeof notificationSchema>
export type NotificationsListResult = v.InferOutput<typeof notificationsListSchema>
export type DeadLetterJob = v.InferOutput<typeof deadLetterJobSchema>
export type DeadLetterListResult = v.InferOutput<typeof deadLetterListSchema>

export const fetchNotificationsList = async (params?: {
  cursor?: string | null
  limit?: number
}) => {
  const response = await listNotificationsApiV1NotificationsGet({
    query: {
      cursor: params?.cursor ?? undefined,
      limit: params?.limit,
    },
  })
  return ensureValidResponse(notificationsListSchema, response.data, "GET /api/v1/notifications")
}

export const markNotificationRead = (notificationId: string) =>
  markReadSingleApiV1NotificationsNotifIdReadPatch({
    path: { notif_id: notificationId },
  })

export const markAllNotificationsRead = () => markAllReadApiV1NotificationsReadAllPost()

export const clearNotifications = () => clearNotificationsApiV1NotificationsDelete()

export const checkSchedule = (lookaheadMinutes: number = 15) =>
  checkScheduleAndGenerateApiV1NotificationsCheckSchedulePost({
    query: { lookahead_minutes: lookaheadMinutes },
  })

export const fetchDeadLetterQueue = async (
  params?: { limit?: number; offset?: number },
  signal?: AbortSignal
) => {
  // This endpoint seems to be missing from the generated SDK or has a different name.
  // Using direct import to avoid circular dependency or missing import errors.
  //
  // Wave 164 SW3 (Tier 4) — optional `signal?: AbortSignal` 2nd arg forwarded
  // to the underlying axios call. Closes W163 SW3 NEW caveat (signal
  // propagation polish carry-forward). Callers that don't have a signal pass
  // undefined; axios treats absent `signal` as non-cancellable. The factory
  // queryFn at `@/api/hooks/adminNotifications` now propagates the TanStack
  // Query AbortSignal so route unmounts and refetch-replacement abort the
  // in-flight request.
  const { apiClient } = await import("@/api/client")
  const response = await apiClient.get("/api/v1/notifications/admin/dead-letter", {
    params,
    signal,
  })
  return ensureValidResponse(
    deadLetterListSchema,
    response.data,
    "GET /api/v1/notifications/admin/dead-letter"
  )
}

export const retryDeadLetterJobs = async (jobIds: string[]) => {
  const { apiClient } = await import("@/api/client")
  return apiClient.post("/api/v1/notifications/admin/dead-letter/retry", { job_ids: jobIds })
}

export const purgeDeadLetterJobs = async (jobIds: string[]) => {
  const { apiClient } = await import("@/api/client")
  return apiClient.post("/api/v1/notifications/admin/dead-letter/purge", { job_ids: jobIds })
}

export async function saveSubscription(
  sub: PushSubscriptionJSON,
  topics?: string[]
): Promise<PushSubscriptionResponse> {
  const endpoint = sub.endpoint?.trim()
  const p256dh = sub.keys?.p256dh?.trim()
  const auth = sub.keys?.auth?.trim()
  if (!endpoint || !p256dh || !auth) {
    throw new Error("Invalid push subscription payload")
  }

  const userAgent =
    typeof navigator !== "undefined" && navigator.userAgent ? navigator.userAgent : undefined

  const payload = {
    endpoint,
    keys: { p256dh, auth },
    user_agent: userAgent,
    ...(Array.isArray(topics) ? { topics } : {}),
  }
  const { data } = await subscribeApiV1PushSubscribePost({ body: payload })
  if (!data) {
    throw new Error("Failed to save subscription")
  }
  return data
}

export async function deleteSubscription(endpoint: string): Promise<void> {
  await unsubscribeApiV1PushUnsubscribePost({ body: { endpoint } })
}

export async function sendTest(): Promise<SendTestNotificationResponse> {
  const { data } = await sendTestApiV1PushTestPost()
  if (!data) {
    throw new Error("Failed to send test notification")
  }
  return data
}

export async function getVapidPublicKey(): Promise<string | null> {
  const { data } = await getVapidPublicKeyApiV1PushVapidPublicKeyGet()
  const schema = v.object({ publicKey: v.optional(v.nullable(v.string())) })
  const parsed = ensureValidResponse(schema, data, "GET /api/v1/push/vapid-public-key")
  const normalized = parsed.publicKey?.trim()
  return normalized && normalized.length > 0 ? normalized : null
}

const pushTopicsSchema = v.object({
  allowed: v.array(v.pipe(v.string(), v.trim(), v.minLength(1))),
  topics: v.optional(v.array(v.pipe(v.string(), v.trim())), []),
  has_preferences: v.optional(v.boolean()),
  updated_at: v.optional(v.nullable(v.string())),
})

export async function fetchPushTopics(): Promise<PushTopicsResponse> {
  const { data } = await getPushTopicsApiV1PushTopicsGet()
  const parsed = ensureValidResponse(pushTopicsSchema, data, "GET /api/v1/push/topics")
  return {
    allowed: parsed.allowed,
    topics: parsed.topics,
    has_preferences: parsed.has_preferences ?? false,
    updated_at: parsed.updated_at ?? null,
  }
}

const adminTopicsSchema = v.object({
  user_id: v.pipe(v.string(), v.uuid()),
  email: v.pipe(v.string(), v.trim(), v.minLength(1)),
  topics: v.array(v.pipe(v.string(), v.trim())),
  allowed_topics: v.array(v.pipe(v.string(), v.trim(), v.minLength(1))),
  updated_at: v.optional(v.nullable(v.string())),
})

export async function fetchAdminUserTopics(userId: string): Promise<AdminUserTopicsResponse> {
  // RZ-14-03: user_id is a UUID string — backend path param is now uuid.UUID, not int.
  const { data } = await adminGetUserTopicsApiV1PushAdminTopicsUserIdGet({
    path: { user_id: userId },
  })
  return ensureValidResponse(adminTopicsSchema, data, `GET /api/v1/push/admin/topics/${userId}`)
}

export async function updateAdminUserTopics(
  userId: string,
  topics: string[]
): Promise<AdminUserTopicsResponse> {
  // RZ-14-03: user_id is a UUID string — backend path param is now uuid.UUID, not int.
  const { data } = await adminUpdateUserTopicsApiV1PushAdminTopicsUserIdPut({
    path: { user_id: userId },
    body: { topics },
  })
  return ensureValidResponse(adminTopicsSchema, data, `PUT /api/v1/push/admin/topics/${userId}`)
}
