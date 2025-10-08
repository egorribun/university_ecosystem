import api from "@/api/client"
import type { PushSubscriptionResponse, SendTestNotificationResponse } from "@/types/notifications"

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

  const { data } = await api.post<PushSubscriptionResponse>("/push/subscribe", payload)
  return data
}

export async function deleteSubscription(endpoint: string): Promise<void> {
  await api.post("/push/unsubscribe", { endpoint })
}

export async function sendTest(): Promise<SendTestNotificationResponse> {
  const { data } = await api.post<SendTestNotificationResponse>("/push/test")
  return data
}
