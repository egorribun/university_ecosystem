import { deleteSubscription, getVapidKey, saveSubscription } from "@/api/notifications"

export const PUSH_CONSENT_STORAGE_KEY = "push:consent"

export function hasPushConsent(): boolean {
  try {
    return localStorage.getItem(PUSH_CONSENT_STORAGE_KEY) === "granted"
  } catch {
    return false
  }
}

export function setPushConsent(consented: boolean): void {
  try {
    if (consented) {
      localStorage.setItem(PUSH_CONSENT_STORAGE_KEY, "granted")
    } else {
      localStorage.removeItem(PUSH_CONSENT_STORAGE_KEY)
    }
  } catch {}
}

export async function fetchVapidPublicKey(): Promise<string | null> {
  try {
    const key = await getVapidKey()
    const normalized = key?.trim() || ""
    return normalized || null
  } catch {
    return null
  }
}

export function urlBase64ToUint8Array(base64String: string) {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4)
  const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/")
  const rawData = atob(base64)
  const outputArray = new Uint8Array(rawData.length)
  for (let i = 0; i < rawData.length; i++) outputArray[i] = rawData.charCodeAt(i)
  return outputArray
}

export async function ensurePushSubscription(
  vapidPublicKey?: string,
  registration?: ServiceWorkerRegistration,
  topics?: string[]
) {
  if (
    !("serviceWorker" in navigator) ||
    !("PushManager" in window) ||
    typeof Notification === "undefined"
  ) {
    return null
  }

  const reg = registration ?? (await navigator.serviceWorker.ready)

  if (Notification.permission === "denied") {
    return null
  }

  if (Notification.permission === "default") {
    const perm = await Notification.requestPermission()
    if (perm !== "granted") {
      return null
    }
  }

  const key = (vapidPublicKey || (await fetchVapidPublicKey()) || "").trim()
  if (!key) {
    return null
  }

  const desiredKey = urlBase64ToUint8Array(key)

  let sub = await reg.pushManager.getSubscription()
  if (sub) {
    const existingKey = sub.options?.applicationServerKey
    const existingBytes = existingKey ? new Uint8Array(existingKey) : null
    const matches =
      !!existingBytes &&
      existingBytes.length === desiredKey.length &&
      existingBytes.every((value, index) => value === desiredKey[index])

    if (!matches) {
      try {
        await sub.unsubscribe()
      } catch {}
      sub = null
    }
  }

  if (!sub) {
    sub = await reg.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: desiredKey,
    })
  }

  type Payload = Parameters<typeof saveSubscription>[0]
  try {
    await saveSubscription(sub.toJSON() as Payload, topics)
  } catch (error) {
    console.error("Failed to persist push subscription", error)
  }
  return sub
}

export async function unsubscribePush() {
  if (!("serviceWorker" in navigator)) return false
  const reg = await navigator.serviceWorker.ready
  const sub = await reg.pushManager.getSubscription()
  if (!sub) return true
  const endpoint = sub.endpoint
  let deleted = false
  if (endpoint) {
    try {
      await deleteSubscription(endpoint)
      deleted = true
    } catch (error) {
      console.warn("Failed to delete push subscription on server", error)
    }
  }
  const ok = await sub.unsubscribe()
  try {
    localStorage.removeItem(PUSH_CONSENT_STORAGE_KEY)
  } catch {}
  return ok && (deleted || !endpoint)
}

export function isPushSupported(): boolean {
  return (
    typeof window !== "undefined" &&
    "serviceWorker" in navigator &&
    "PushManager" in window &&
    typeof Notification !== "undefined"
  )
}

export async function getExistingPushSubscription(
  registration?: ServiceWorkerRegistration
): Promise<PushSubscription | null> {
  if (!isPushSupported()) return null
  const reg = registration ?? (await navigator.serviceWorker.ready)
  try {
    const sub = await reg.pushManager.getSubscription()
    return sub
  } catch {
    return null
  }
}
