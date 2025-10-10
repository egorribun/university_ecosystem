import { deleteSubscription, getVapidPublicKey, saveSubscription } from "@/api/notifications"

const SUBSCRIPTION_EXPIRY_THRESHOLD_MS = 3 * 24 * 60 * 60 * 1000 // 3 days
const PERSIST_MAX_ATTEMPTS = 5
const PERSIST_BASE_DELAY_MS = 500
const PUSH_LAST_SYNC_STORAGE_KEY = "push:last_sync"
const PUSH_SUB_STORAGE_KEY = "push:last_payload"
const PUSH_TOPICS_STORAGE_KEY = "push:last_topics"

const ensureLocks = new Map<string, Promise<PushSubscription | null>>()
const SERVICE_WORKER_READY_TIMEOUT_MS = 2000
let cachedVapidPublicKey: string | null | undefined

type NormalizedTopics = string[] | undefined

export function parseStoredTopics(raw: string | null): NormalizedTopics {
  if (!raw) return undefined
  try {
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return undefined
    const topics: string[] = []
    for (const entry of parsed) {
      if (typeof entry !== "string") continue
      const normalized = entry.trim()
      if (!normalized) continue
      topics.push(normalized)
    }
    return topics.length ? topics : []
  } catch {
    return undefined
  }
}

export function getPersistedTopics(): string[] | undefined {
  return parseStoredTopics(getStoredValue(PUSH_TOPICS_STORAGE_KEY)) ?? undefined
}

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
  topics?: string[],
): Promise<Awaited<ReturnType<typeof saveSubscription>> | null> {
  let attempt = 0
  // Add jitter to reduce the probability of thundering herd
  const jitter = () => Math.random() * PERSIST_BASE_DELAY_MS

  // eslint-disable-next-line no-constant-condition
  while (true) {
    try {
      const response = await saveSubscription(payload, topics)
      const normalizedTopics = response?.topics ?? (topics ? [...topics].sort() : [])
      setStoredValue(PUSH_SUB_STORAGE_KEY, JSON.stringify(payload))
      setStoredValue(PUSH_LAST_SYNC_STORAGE_KEY, Date.now().toString())
      setStoredValue(PUSH_TOPICS_STORAGE_KEY, JSON.stringify(normalizedTopics))
      return response
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

export async function resolveServiceWorkerRegistration(
  registration?: ServiceWorkerRegistration,
): Promise<ServiceWorkerRegistration | null> {
  if (registration) return registration
  if (typeof navigator === "undefined" || !("serviceWorker" in navigator)) {
    return null
  }

  try {
    const existing = await navigator.serviceWorker.getRegistration()
    if (existing) return existing
  } catch (error) {
    console.warn("Failed to get existing service worker registration", error)
  }

  try {
    const readyPromise = navigator.serviceWorker.ready
      .then(reg => reg)
      .catch(error => {
        console.warn("Service worker ready promise rejected", error)
        return null
      })

    const timeout = new Promise<ServiceWorkerRegistration | null>(resolve => {
      setTimeout(() => resolve(null), SERVICE_WORKER_READY_TIMEOUT_MS)
    })

    const resolved = await Promise.race([readyPromise, timeout])
    if (resolved) return resolved
  } catch (error) {
    console.warn("Failed to await service worker readiness", error)
  }

  try {
    const { registerServiceWorker } = await import("./register-sw")
    const registered = await registerServiceWorker()
    if (registered) return registered
  } catch (error) {
    console.warn("Failed to auto-register service worker", error)
  }

  try {
    return (await navigator.serviceWorker.getRegistration()) ?? null
  } catch (error) {
    console.warn("Failed to get service worker registration after timeout", error)
    return null
  }
}

export async function resolveVapidPublicKey(): Promise<string | null> {
  if (cachedVapidPublicKey !== undefined) {
    return cachedVapidPublicKey
  }

  const rawKey = import.meta.env.VITE_VAPID_PUBLIC_KEY
  if (typeof rawKey === "string") {
    const normalized = rawKey.trim()
    if (normalized) {
      cachedVapidPublicKey = normalized
      return cachedVapidPublicKey
    }
  }

  try {
    const serverKey = await getVapidPublicKey()
    cachedVapidPublicKey = serverKey ?? null
    if (!cachedVapidPublicKey && import.meta.env.DEV) {
      console.warn("VAPID public key is not configured on the server")
    }
    return cachedVapidPublicKey
  } catch (error) {
    console.warn("Failed to fetch VAPID public key", error)
    cachedVapidPublicKey = null
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

type EnsurePushSubscriptionOptions = {
  registration?: ServiceWorkerRegistration
  vapidPublicKey?: string
  topics?: string[]
  requestPermission?: boolean
}

export async function ensurePushSubscription(
  options?: EnsurePushSubscriptionOptions,
): Promise<PushSubscription | null> {
  if (
    !("serviceWorker" in navigator) ||
    !("PushManager" in window) ||
    typeof Notification === "undefined"
  ) {
    return null
  }

  const topics = options?.topics
  const lockKey = JSON.stringify({
    key: options?.vapidPublicKey || null,
    topics: topics ? [...topics].sort() : [],
    requestPermission: Boolean(options?.requestPermission),
  })

  const existingLock = ensureLocks.get(lockKey)
  if (existingLock) {
    return existingLock
  }

  const task = (async () => {
    const reg = await resolveServiceWorkerRegistration(options?.registration)

    if (!reg) {
      console.warn("Cannot ensure push subscription without service worker registration")
      return null
    }

    if (Notification.permission === "denied") {
      return null
    }

    if (Notification.permission === "default") {
      if (!options?.requestPermission) {
        return null
      }
      const perm = await Notification.requestPermission()
      if (perm !== "granted") {
        return null
      }
    }

    const resolvedKey = options?.vapidPublicKey ?? (await resolveVapidPublicKey())
    const key = (resolvedKey ?? "").trim()
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
        } catch (error) {
          if (import.meta.env.DEV) {
            console.warn("Failed to unsubscribe push subscription", error)
          }
        }
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

type UnsubscribePushOptions = {
  registration?: ServiceWorkerRegistration
  preserveConsent?: boolean
}

function clearPushLocals(preserveConsent?: boolean) {
  if (!preserveConsent) {
    try {
      localStorage.removeItem(PUSH_CONSENT_STORAGE_KEY)
    } catch {}
  }
  removeStoredValue(PUSH_LAST_SYNC_STORAGE_KEY)
  removeStoredValue(PUSH_SUB_STORAGE_KEY)
  removeStoredValue(PUSH_TOPICS_STORAGE_KEY)
}

export async function unsubscribePush(options?: UnsubscribePushOptions) {
  if (!("serviceWorker" in navigator)) {
    clearPushLocals(options?.preserveConsent)
    return false
  }

  const registration = await resolveServiceWorkerRegistration(
    options?.registration,
  )

  if (!registration) {
    clearPushLocals(options?.preserveConsent)
    return false
  }

  const subscription = await registration.pushManager.getSubscription()
  if (!subscription) {
    clearPushLocals(options?.preserveConsent)
    return true
  }

  const endpoint = subscription.endpoint
  let deleted = false
  if (endpoint) {
    try {
      await deleteSubscription(endpoint)
      deleted = true
    } catch (error) {
      console.warn("Failed to delete push subscription on server", error)
    }
  }

  const ok = await subscription.unsubscribe()

  clearPushLocals(options?.preserveConsent)

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
  const reg = await resolveServiceWorkerRegistration(registration)
  if (!reg) return null
  try {
    const sub = await reg.pushManager.getSubscription()
    return sub
  } catch {
    return null
  }
}

type SoftSyncOptions = {
  registration?: ServiceWorkerRegistration
  vapidPublicKey?: string
  topics?: string[]
}

export async function softSyncPushSubscription(
  options?: SoftSyncOptions
): Promise<PushSubscription | null> {
  if (!isPushSupported()) return null
  if (typeof Notification === "undefined") return null
  if (Notification.permission !== "granted") return null

  const storedTopics = options?.topics ?? parseStoredTopics(getStoredValue(PUSH_TOPICS_STORAGE_KEY))
  try {
    const subscription = await ensurePushSubscription({
      vapidPublicKey: options?.vapidPublicKey,
      registration: options?.registration,
      topics: storedTopics,
      requestPermission: false,
    })
    return subscription
  } catch (error) {
    console.error("Failed to soft sync push subscription", error)
    return null
  }
}
