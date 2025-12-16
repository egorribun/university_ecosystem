import { z } from "zod"

import api, { apiClient } from "@/api/client"
import type { components } from "@/api/generated/schema"
import type {
  AdminUserTopicsResponse,
  PushSubscriptionResponse,
  PushTopicsResponse,
  SendTestNotificationResponse,
} from "@/types/notifications"
import { ensureValidResponse } from "./validation"

const notificationSchema = z.object({
  id: z.number().int(),
  title: z.string(),
  body: z.string().nullable().optional(),
  title_en: z.string().nullable().optional(),
  body_en: z.string().nullable().optional(),
  type: z.string().nullable().optional(),
  url: z.string().nullable().optional(),
  created_at: z.string(),
  read: z.boolean(),
  read_at: z.string().nullable().optional(),
})

const notificationsListSchema = z.object({
  items: z.array(notificationSchema),
  unread_count: z.number(),
  has_more: z.boolean(),
  next_cursor: z.string().nullable().optional(),
})

const deadLetterJobSchema = z.object({
  id: z.number().int(),
  kind: z.string(),
  record_id: z.number().int(),
  locale: z.string().nullable().optional(),
  enqueued_at: z.string(),
  claimed_at: z.string().nullable().optional(),
  attempts: z.number().int(),
  last_error: z.string().nullable().optional(),
  next_retry_at: z.string().nullable().optional(),
})

const deadLetterListSchema = z.object({
  items: z.array(deadLetterJobSchema),
  total: z.number().int(),
})

export type NotificationEntry = z.infer<typeof notificationSchema>
export type NotificationsListResult = z.infer<typeof notificationsListSchema>
export type DeadLetterJob = z.infer<typeof deadLetterJobSchema>
export type DeadLetterListResult = z.infer<typeof deadLetterListSchema>

export const fetchNotificationsList = async (params?: {
  cursor?: string | null
  limit?: number
}) => {
  const response = await apiClient.get("/api/v1/notifications", {
    params,
  })
  return ensureValidResponse(notificationsListSchema, response.data, "GET /api/v1/notifications")
}

export const markNotificationRead = (notificationId: number) =>
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
  const response = await api.get("/api/v1/notifications/admin/dead-letter", {
    params,
  })
  return ensureValidResponse(
    deadLetterListSchema,
    response.data,
    "GET /api/v1/notifications/admin/dead-letter"
  )
}

export const retryDeadLetterJobs = (jobIds: number[]) =>
  api.post("/api/v1/notifications/admin/dead-letter/retry", { job_ids: jobIds })

export const purgeDeadLetterJobs = (jobIds: number[]) =>
  api.post("/api/v1/notifications/admin/dead-letter/purge", { job_ids: jobIds })

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
  const schema = z.object({ publicKey: z.string().trim().min(1).optional() })
  const parsed = ensureValidResponse(schema, data, "GET /api/v1/push/vapid-public-key")
  const normalized = parsed.publicKey?.trim()
  return normalized && normalized.length > 0 ? normalized : null
}

const pushTopicsSchema = z.object({
  allowed: z.array(z.string().trim().min(1)),
  topics: z.array(z.string().trim()).default([]),
  has_preferences: z.boolean().optional(),
  updated_at: z.string().datetime().nullable().optional(),
})

export async function fetchPushTopics(): Promise<PushTopicsResponse> {
  const { data } = await apiClient.get("/api/v1/push/topics")
  const parsed = ensureValidResponse(pushTopicsSchema, data, "GET /api/v1/push/topics")
  return {
    allowed: parsed.allowed,
    topics: parsed.topics ?? [],
    has_preferences: parsed.has_preferences ?? false,
    updated_at: parsed.updated_at ?? null,
  }
}

const adminTopicsSchema = z.object({
  user_id: z.number().int().positive(),
  email: z.string().trim().min(1),
  topics: z.array(z.string().trim()),
  allowed_topics: z.array(z.string().trim().min(1)),
  updated_at: z.string().datetime().nullable().optional(),
})

export async function fetchAdminUserTopics(userId: number): Promise<AdminUserTopicsResponse> {
  const { data } = await apiClient.get("/api/v1/push/admin/topics/{user_id}", {
    pathParams: { user_id: userId },
  })
  return ensureValidResponse(adminTopicsSchema, data, `GET /api/v1/push/admin/topics/${userId}`)
}

export async function updateAdminUserTopics(
  userId: number,
  topics: string[]
): Promise<AdminUserTopicsResponse> {
  const payload = { topics }
  const { data } = await apiClient.put("/api/v1/push/admin/topics/{user_id}", payload, {
    pathParams: { user_id: userId },
  })
  return ensureValidResponse(adminTopicsSchema, data, `PUT /api/v1/push/admin/topics/${userId}`)
}
