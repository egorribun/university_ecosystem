import { z } from "zod"

import api from "@/api/client"
import type { components, paths } from "@/api/generated/schema"
import type {
  AdminUserTopicsResponse,
  PushSubscriptionResponse,
  PushTopicsResponse,
  SendTestNotificationResponse,
} from "@/types/notifications"
import { ensureValidResponse } from "./validation"

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

  const { data } = await api.post<PushSubscriptionResponse>("/push/subscribe", payload)
  return data
}

export async function deleteSubscription(endpoint: string): Promise<void> {
  const payload: components["schemas"]["PushSubscriptionDelete"] = { endpoint }
  await api.post("/push/unsubscribe", payload)
}

export async function sendTest(): Promise<SendTestNotificationResponse> {
  const { data } = await api.post<SendTestNotificationResponse>("/push/test")
  return data
}

export async function getVapidPublicKey(): Promise<string | null> {
  const { data } =
    await api.get<
      paths["/push/vapid-public-key"]["get"]["responses"]["200"]["content"]["application/json"]
    >("/push/vapid-public-key")
  const schema = z.object({ publicKey: z.string().trim().min(1).optional() })
  const parsed = ensureValidResponse(schema, data, "GET /push/vapid-public-key")
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
  const { data } = await api.get<PushTopicsResponse>("/push/topics")
  const parsed = ensureValidResponse(pushTopicsSchema, data, "GET /push/topics")
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
  const { data } = await api.get<AdminUserTopicsResponse>(`/push/admin/topics/${userId}`)
  return ensureValidResponse(adminTopicsSchema, data, `GET /push/admin/topics/${userId}`)
}

export async function updateAdminUserTopics(
  userId: number,
  topics: string[]
): Promise<AdminUserTopicsResponse> {
  const payload = { topics }
  const { data } = await api.put<AdminUserTopicsResponse>(`/push/admin/topics/${userId}`, payload)
  return ensureValidResponse(adminTopicsSchema, data, `PUT /push/admin/topics/${userId}`)
}
