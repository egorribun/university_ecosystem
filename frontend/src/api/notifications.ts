import * as v from "valibot"

import api, { apiClient } from "@/api/client"
import type { components } from "@/api/generated/schema"
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
  id: v.string(), // Redis/worker job IDs might still be numbers
  kind: v.string(),
  record_id: v.string(), // This might need verification, is it referencing a DB ID?
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
  const response = await apiClient.get("/api/v1/notifications", {
    params,
  })
  return ensureValidResponse(notificationsListSchema, response.data, "GET /api/v1/notifications")
}

export const markNotificationRead = (notificationId: string) =>
  apiClient.patch("/api/v1/notifications/{notif_id}/read", undefined, {
    pathParams: { notif_id: notificationId },
  })

export const markAllNotificationsRead = () => apiClient.post("/api/v1/notifications/read-all")

export const clearNotifications = () => apiClient.delete("/api/v1/notifications")

export const checkSchedule = (lookaheadMinutes: number = 15) =>
  apiClient.post("/api/v1/notifications/check-schedule", undefined, {
    params: { lookahead_minutes: lookaheadMinutes },
  })

export const fetchDeadLetterQueue = async (params?: { limit?: number; offset?: number }) => {
  const response = await api.get("/notifications/admin/dead-letter", {
    params,
  })
  return ensureValidResponse(
    deadLetterListSchema,
    response.data,
    "GET /notifications/admin/dead-letter"
  )
}

export const retryDeadLetterJobs = (jobIds: string[]) =>
  api.post("/notifications/admin/dead-letter/retry", { job_ids: jobIds })

export const purgeDeadLetterJobs = (jobIds: string[]) =>
  api.post("/notifications/admin/dead-letter/purge", { job_ids: jobIds })

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

  const payload: components["schemas"]["PushSubscriptionIn"] = {
    endpoint,
    keys: { p256dh, auth },
    user_agent: userAgent,
    ...(Array.isArray(topics) ? { topics } : {}),
  }
  const { data } = await apiClient.post("/api/v1/push/subscribe", payload)
  return data
}

export async function deleteSubscription(endpoint: string): Promise<void> {
  const payload: components["schemas"]["PushSubscriptionDelete"] = { endpoint }
  await apiClient.post("/api/v1/push/unsubscribe", payload)
}

export async function sendTest(): Promise<SendTestNotificationResponse> {
  const { data } = await apiClient.post("/api/v1/push/test")
  return data
}

export async function getVapidPublicKey(): Promise<string | null> {
  const { data } = await apiClient.get("/api/v1/push/vapid-public-key")
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
  const { data } = await apiClient.get("/api/v1/push/topics")
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
  const { data } = await apiClient.get("/api/v1/push/admin/topics/{user_id}", {
    pathParams: { user_id: userId as unknown as number }, // Note: apiClient handles string/number path params
  })
  // Cast data if needed, but schema.ts should now define user_id as string/number based on openapi
  return ensureValidResponse(adminTopicsSchema, data, `GET /api/v1/push/admin/topics/${userId}`)
}

export async function updateAdminUserTopics(
  userId: string,
  topics: string[]
): Promise<AdminUserTopicsResponse> {
  const payload = { topics }
  const { data } = await apiClient.put("/api/v1/push/admin/topics/{user_id}", payload, {
    pathParams: { user_id: userId as unknown as number },
  })
  return ensureValidResponse(adminTopicsSchema, data, `PUT /api/v1/push/admin/topics/${userId}`)
}
