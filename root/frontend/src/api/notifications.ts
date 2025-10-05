import api from "@/api/client"
import type {
  PushSubscriptionResponse,
  SendTestNotificationResponse,
  VapidPublicKeyResponse,
} from "@/types/notifications"

export async function fetchNotifications(limit = 20, offset = 0) {
  const r = await api.get("/notifications", { params: { limit, offset } })
  return r.data
}

export async function markRead(id: number) {
  await api.post("/notifications/mark-read", { id })
}

export async function markAllRead() {
  await api.post("/notifications/mark-all-read", {})
}

export async function getVapidKey(): Promise<string> {
  const { data } = await api.get<VapidPublicKeyResponse>("/webpush/vapid-public-key")
  return data.publicKey
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
    topics,
    user_agent: userAgent,
  }

  const { data } = await api.post<PushSubscriptionResponse>("/webpush/subscribe", payload)
  return data
}

export async function deleteSubscription(endpoint: string): Promise<void> {
  await api.delete("/webpush/subscribe", { data: { endpoint } })
}

export async function sendTest(): Promise<SendTestNotificationResponse> {
  const { data } = await api.post<SendTestNotificationResponse>("/webpush/send-test")
  return data
}