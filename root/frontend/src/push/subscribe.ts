import { deleteSubscription, getVapidKey, saveSubscription } from "@/api/notifications"

const SUBSCRIPTION_EXPIRY_THRESHOLD_MS = 3 * 24 * 60 * 60 * 1000 // 3 days
const PERSIST_MAX_ATTEMPTS = 5
const PERSIST_BASE_DELAY_MS = 500
const PUSH_LAST_SYNC_STORAGE_KEY = "push:last_sync"
const PUSH_SUB_STORAGE_KEY = "push:last_payload"
const PUSH_TOPICS_STORAGE_KEY = "push:last_topics"

const ensureLocks = new Map<string, Promise<PushSubscription | null>>()

function sleep(ms: number) {
  return new Promise<void>(resolve => setTimeout(resolve, ms))
}

function getStoredValue(key: string): string | null {
  try {
    return localStorage.getItem(key)
  } catch {
    return null
  }
}

function setStoredValue(key: string, value: string) {
  try {
    localStorage.setItem(key, value)
  } catch {}
}

function removeStoredValue(key: string) {
  try {
    localStorage.removeItem(key)
  } catch {}
}

async function persistSubscriptionWithBackoff(
  payload: Parameters<typeof saveSubscription>[0],
  topics?: string[]
) {
  let attempt = 0
  // Add jitter to reduce the probability of thundering herd
  const jitter = () => Math.random() * PERSIST_BASE_DELAY_MS

  // eslint-disable-next-line no-constant-condition
  while (true) {
    try {
      await saveSubscription(payload, topics)
      setStoredValue(PUSH_SUB_STORAGE_KEY, JSON.stringify(payload))
      setStoredValue(PUSH_LAST_SYNC_STORAGE_KEY, Date.now().toString())
      setStoredValue(PUSH_TOPICS_STORAGE_KEY, JSON.stringify(topics ? [...topics].sort() : []))
      return
    } catch (error) {
      attempt += 1
      if (attempt >= PERSIST_MAX_ATTEMPTS) {
        console.error("Failed to persist push subscription", error)
        throw error
      }
      const delay = Math.min(30000, 2 ** (attempt - 1) * PERSIST_BASE_DELAY_MS) + jitter()
      await sleep(delay)
    }
  }
}

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
  const lockKey = JSON.stringify({
    key: vapidPublicKey || null,
    topics: topics ? [...topics].sort() : [],
  })

  const existingLock = ensureLocks.get(lockKey)
  if (existingLock) {
    return existingLock
  }

  const task = (async () => {
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

      const isExpiringSoon =
        typeof sub.expirationTime === "number" &&
        sub.expirationTime > 0 &&
        sub.expirationTime - Date.now() < SUBSCRIPTION_EXPIRY_THRESHOLD_MS

      if (!matches || isExpiringSoon) {
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
    const payload = sub.toJSON() as Payload
    const serialized = JSON.stringify(payload)
    const previous = getStoredValue(PUSH_SUB_STORAGE_KEY)
    const currentTopics = JSON.stringify(topics ? [...topics].sort() : [])
    const storedTopics = getStoredValue(PUSH_TOPICS_STORAGE_KEY)
    const shouldPersist = !previous || previous !== serialized || currentTopics !== storedTopics

    if (shouldPersist) {
      try {
        await persistSubscriptionWithBackoff(payload, topics)
      } catch (error) {
        console.error("Failed to persist push subscription", error)
      }
    } else {
      setStoredValue(PUSH_LAST_SYNC_STORAGE_KEY, Date.now().toString())
    }

    return sub
  })()

  ensureLocks.set(lockKey, task)

  try {
    return await task
  } finally {
    ensureLocks.delete(lockKey)
  }
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
  removeStoredValue(PUSH_LAST_SYNC_STORAGE_KEY)
  removeStoredValue(PUSH_SUB_STORAGE_KEY)
  removeStoredValue(PUSH_TOPICS_STORAGE_KEY)
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
