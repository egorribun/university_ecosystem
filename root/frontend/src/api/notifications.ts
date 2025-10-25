import { z } from "zod"

import api from "@/api/client"
import type { components, paths } from "@/api/generated/schema"
import type { PushSubscriptionResponse, SendTestNotificationResponse } from "@/types/notifications"
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
    topics,
    user_agent: userAgent,
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
  const { data } = await api.get<
    paths["/push/vapid-public-key"]["get"]["responses"]["200"]["content"]["application/json"]
  >("/push/vapid-public-key")
  const schema = z.object({ publicKey: z.string().trim().min(1).optional() })
  const parsed = ensureValidResponse(schema, data, "GET /push/vapid-public-key")
  const normalized = parsed.publicKey?.trim()
  return normalized && normalized.length > 0 ? normalized : null
}
