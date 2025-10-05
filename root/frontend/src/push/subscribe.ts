import api from "@/api/client"

const VAPID_STORAGE_KEY = "vapid:pub"
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
    const response = await api.get<{ key?: string }>("/push/public-key")
    const key = response.data?.key?.trim() || ""
    return key || null
  } catch {
    return null
  }
}

function urlBase64ToUint8Array(base64String: string) {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4)
  const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/")
  const rawData = atob(base64)
  const outputArray = new Uint8Array(rawData.length)
  for (let i = 0; i < rawData.length; i++) outputArray[i] = rawData.charCodeAt(i)
  return outputArray
}

async function sendSubToServer(sub: PushSubscription) {
  const data = sub.toJSON() as any
  await api.post("/push/subscribe", { endpoint: data.endpoint, keys: data.keys })
}

export async function ensurePushSubscription(
  vapidPublicKey?: string,
  registration?: ServiceWorkerRegistration
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

  const storedKey = (() => {
    try {
      return localStorage.getItem(VAPID_STORAGE_KEY) || ""
    } catch {
      return ""
    }
  })()

  let sub = await reg.pushManager.getSubscription()
  if (sub && storedKey && storedKey !== key) {
    try {
      await sub.unsubscribe()
    } catch {}
    sub = null
  }

  if (!sub) {
    sub = await reg.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(key),
    })
  }

  try {
    localStorage.setItem(VAPID_STORAGE_KEY, key)
  } catch {}

  await sendSubToServer(sub)
  return sub
}

export async function unsubscribePush() {
  if (!("serviceWorker" in navigator)) return false
  const reg = await navigator.serviceWorker.ready
  const sub = await reg.pushManager.getSubscription()
  if (!sub) return true
  const data = sub.toJSON() as any
  try { await api.post("/push/unsubscribe", { endpoint: data.endpoint, keys: data.keys }) } catch {}
  const ok = await sub.unsubscribe()
  try {
    localStorage.removeItem(VAPID_STORAGE_KEY)
    localStorage.removeItem(PUSH_CONSENT_STORAGE_KEY)
  } catch {}
  return ok
}
