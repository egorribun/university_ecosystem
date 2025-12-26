import { isAxiosError } from "axios"
import { deleteSubscription, getVapidPublicKey, saveSubscription } from "@/api/notifications"
import { logError, logWarning } from "@/app/logger"

const SUBSCRIPTION_EXPIRY_THRESHOLD_MS = 3 * 24 * 60 * 60 * 1000 // 3 days
const PERSIST_MAX_ATTEMPTS = 3
const PERSIST_BASE_DELAY_MS = 500
const PUSH_LAST_SYNC_STORAGE_KEY = "push:last_sync"
const PUSH_SUB_STORAGE_KEY = "push:last_payload"
const PUSH_TOPICS_STORAGE_KEY = "push:last_topics"
const PUSH_TOPICS_STORAGE_VERSION = 2
const PROFILE_CACHE_STORAGE_KEY = "ecosystem.profile.cache.v1"

// Global lock to prevent ANY concurrent ensurePushSubscription calls
let globalEnsureLock: Promise<PushSubscription | null> | null = null
const SERVICE_WORKER_READY_TIMEOUT_MS = 2000
let cachedVapidPublicKey: string | null | undefined

type NormalizedTopics = string[] | undefined

type MaybeUserId = string | number | null | undefined

function normalizeUserId(input: MaybeUserId): string | null {
  if (input == null) return null
  if (typeof input === "string" || typeof input === "number") {
    const normalized = String(input).trim()
    return normalized ? normalized : null
  }
  return null
}

function normalizeTopics(input: unknown): string[] | undefined {
  if (!Array.isArray(input)) return undefined
  const normalized: string[] = []
  const seen = new Set<string>()
  for (const entry of input) {
    if (entry == null) continue
    const trimmed = entry.toString().trim()
    if (!trimmed || seen.has(trimmed)) continue
    seen.add(trimmed)
    normalized.push(trimmed)
  }
  normalized.sort()
  return normalized
}

function readActiveUserId(): string | null {
  if (typeof localStorage === "undefined") return null
  try {
    const rawProfile = localStorage.getItem(PROFILE_CACHE_STORAGE_KEY)
    if (!rawProfile) return null
    const parsed = JSON.parse(rawProfile)
    const data =
      parsed && typeof parsed === "object" && "data" in parsed
        ? (parsed as { data?: unknown }).data
        : parsed
    if (!data || typeof data !== "object") return null
    const id = (data as Record<string, unknown>).id as MaybeUserId
    return normalizeUserId(id)
  } catch {
    return null
  }
}

function parseTopicsPayload(
  raw: string | null,
  options?: { userId?: MaybeUserId }
): string[] | undefined {
  if (!raw) return undefined
  const userId = normalizeUserId(options?.userId) ?? readActiveUserId()
  try {
    const parsed = JSON.parse(raw)
    if (Array.isArray(parsed)) {
      return normalizeTopics(parsed)
    }
    if (!parsed || typeof parsed !== "object") return undefined

    const payload = parsed as {
      version?: unknown
      topics?: unknown
      shared?: unknown
      perUser?: unknown
    }

    if (userId) {
      const perUser = payload.perUser
      if (perUser && typeof perUser === "object") {
        const userTopics = normalizeTopics((perUser as Record<string, unknown>)[userId])
        if (userTopics !== undefined) {
          return userTopics
        }
      }
    }

    const shared =
      "shared" in payload && payload.shared !== undefined
        ? payload.shared
        : (payload as { topics?: unknown }).topics
    const sharedTopics = normalizeTopics(shared)
    if (sharedTopics !== undefined) {
      return sharedTopics
    }

    return undefined
  } catch {
    return undefined
  }
}

export function parseStoredTopics(
  raw: string | null,
  options?: { userId?: MaybeUserId }
): NormalizedTopics {
  return parseTopicsPayload(raw, options)
}

export function getPersistedTopics(options?: { userId?: MaybeUserId }): string[] | undefined {
  return parseTopicsPayload(getStoredValue(PUSH_TOPICS_STORAGE_KEY), options) ?? undefined
}

function buildTopicsPayload(
  nextTopics: string[] | null | undefined,
  existingRaw: string | null,
  userId: string | null
): string | null {
  if (nextTopics == null) {
    if (!userId) {
      if (!existingRaw) {
        return null
      }

      try {
        const parsed = JSON.parse(existingRaw)
        if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
          return null
        }

        const payload = parsed as {
          perUser?: unknown
        }

        if (!payload.perUser || typeof payload.perUser !== "object") {
          return null
        }

        const perUserEntries: Record<string, string[]> = {}
        for (const [key, value] of Object.entries(payload.perUser as Record<string, unknown>)) {
          const normalizedEntry = normalizeTopics(value)
          if (normalizedEntry !== undefined) {
            perUserEntries[key] = normalizedEntry
          }
        }

        if (Object.keys(perUserEntries).length === 0) {
          return null
        }

        return JSON.stringify({
          version: PUSH_TOPICS_STORAGE_VERSION,
          perUser: perUserEntries,
        })
      } catch {
        return null
      }
    }

    if (!existingRaw) {
      return null
    }

    try {
      const parsed = JSON.parse(existingRaw)
      if (Array.isArray(parsed)) {
        return null
      }
      if (!parsed || typeof parsed !== "object") {
        return null
      }

      const payload = parsed as {
        version?: unknown
        shared?: unknown
        topics?: unknown
        perUser?: unknown
      }

      const sharedTopics = normalizeTopics(
        "shared" in payload && payload.shared !== undefined
          ? payload.shared
          : (payload as { topics?: unknown }).topics
      )

      const perUserEntries: Record<string, string[]> = {}
      if (payload.perUser && typeof payload.perUser === "object") {
        for (const [key, value] of Object.entries(payload.perUser as Record<string, unknown>)) {
          if (key === userId) continue
          const normalizedEntry = normalizeTopics(value)
          if (normalizedEntry !== undefined) {
            perUserEntries[key] = normalizedEntry
          }
        }
      }

      const hasPerUser = Object.keys(perUserEntries).length > 0

      if (!hasPerUser && sharedTopics === undefined) {
        return null
      }

      const normalizedPayload: Record<string, unknown> = {
        version: PUSH_TOPICS_STORAGE_VERSION,
      }

      if (hasPerUser) {
        normalizedPayload.perUser = perUserEntries
      }

      if (sharedTopics !== undefined) {
        normalizedPayload.shared = sharedTopics
      }

      return JSON.stringify(normalizedPayload)
    } catch {
      return null
    }
  }

  const normalizedTopics = normalizeTopics(nextTopics) ?? []

  const payload: Record<string, unknown> = {
    version: PUSH_TOPICS_STORAGE_VERSION,
  }

  if (userId) {
    const perUser: Record<string, string[]> = {}

    if (existingRaw) {
      try {
        const parsed = JSON.parse(existingRaw)
        if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
          if (parsed.perUser && typeof parsed.perUser === "object") {
            for (const [key, value] of Object.entries(parsed.perUser as Record<string, unknown>)) {
              const normalizedEntry = normalizeTopics(value)
              if (normalizedEntry !== undefined) {
                perUser[key] = normalizedEntry
              }
            }
          }
          const sharedTopics = normalizeTopics(
            "shared" in parsed && parsed.shared !== undefined
              ? parsed.shared
              : (parsed as { topics?: unknown }).topics
          )
          if (sharedTopics !== undefined) {
            payload.shared = sharedTopics
          }
        } else if (Array.isArray(parsed)) {
          const sharedTopics = normalizeTopics(parsed)
          if (sharedTopics !== undefined) {
            payload.shared = sharedTopics
          }
        }
      } catch {
        /* ignore malformed data */
      }
    }

    perUser[userId] = normalizedTopics

    if (Object.keys(perUser).length > 0) {
      payload.perUser = perUser
    }
  } else {
    const perUserEntries: Record<string, string[]> = {}

    if (existingRaw) {
      try {
        const parsed = JSON.parse(existingRaw)
        if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
          if (parsed.perUser && typeof parsed.perUser === "object") {
            for (const [key, value] of Object.entries(parsed.perUser as Record<string, unknown>)) {
              const normalizedEntry = normalizeTopics(value)
              if (normalizedEntry !== undefined) {
                perUserEntries[key] = normalizedEntry
              }
            }
          }
        }
      } catch {
        /* ignore malformed data */
      }
    }

    if (Object.keys(perUserEntries).length > 0) {
      payload.perUser = perUserEntries
    }

    payload.shared = normalizedTopics
  }

  return JSON.stringify(payload)
}

export function setPersistedTopics(
  topics: string[] | null | undefined,
  options?: { userId?: MaybeUserId }
): void {
  const normalizedUserId = normalizeUserId(options?.userId)
  const userId = normalizedUserId ?? readActiveUserId()
  const currentRaw = getStoredValue(PUSH_TOPICS_STORAGE_KEY)
  const payload = buildTopicsPayload(topics, currentRaw, userId)
  if (payload === null) {
    removeStoredValue(PUSH_TOPICS_STORAGE_KEY)
    return
  }
  setStoredValue(PUSH_TOPICS_STORAGE_KEY, payload)
}

function sleep(ms: number) {
  return new Promise<void>((resolve) => setTimeout(resolve, ms))
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

let syncInProgress = false
let globalSyncLock: Promise<PushSubscription | null> | null = null

async function persistSubscriptionWithBackoff(
  payload: Parameters<typeof saveSubscription>[0],
  topics?: string[]
): Promise<Awaited<ReturnType<typeof saveSubscription>> | null> {
  if (syncInProgress) {
    logWarning("Push subscription sync already in progress, skipping redundant attempt")
    return null
  }

  syncInProgress = true
  let attempt = 0
  // Add jitter to reduce the probability of thundering herd
  const jitter = () => Math.random() * PERSIST_BASE_DELAY_MS

  try {
    for (;;) {
      try {
        const response = await saveSubscription(payload, topics)
        const normalizedTopics = response?.topics ?? (topics ? [...topics].sort() : [])
        setStoredValue(PUSH_SUB_STORAGE_KEY, JSON.stringify(payload))
        setStoredValue(PUSH_LAST_SYNC_STORAGE_KEY, Date.now().toString())
        setPersistedTopics(normalizedTopics)
        return response
      } catch (error) {
        const isConflict =
          (isAxiosError(error) && error.response?.status === 409) ||
          (error &&
            typeof error === "object" &&
            "response" in error &&
            (error as any).response?.status === 409) ||
          (error instanceof Error && error.message.includes("409"))

        if (isConflict) {
          // 409 means the subscription already exists on the server - treat as success
          logWarning("Subscription already exists (409), treating as success")
          setStoredValue(PUSH_SUB_STORAGE_KEY, JSON.stringify(payload))
          setStoredValue(PUSH_LAST_SYNC_STORAGE_KEY, Date.now().toString())
          if (topics) {
            setPersistedTopics(topics)
          }
          return null
        }

        const isRateLimited =
          (isAxiosError(error) && error.response?.status === 429) ||
          (error &&
            typeof error === "object" &&
            "response" in error &&
            (error as any).response?.status === 429)

        if (isRateLimited) {
          // 429 means too many requests - stop immediately, don't retry
          logWarning("Rate limited (429), stopping retries")
          return null
        }

        attempt += 1
        if (attempt >= PERSIST_MAX_ATTEMPTS) {
          logError("Failed to persist push subscription", error)
          throw error
        }
        const delay = Math.min(30000, 2 ** (attempt - 1) * PERSIST_BASE_DELAY_MS) + jitter()
        await sleep(delay)
      }
    }
  } finally {
    syncInProgress = false
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
  registration?: ServiceWorkerRegistration
): Promise<ServiceWorkerRegistration | null> {
  if (registration) return registration
  if (typeof navigator === "undefined" || !("serviceWorker" in navigator)) {
    return null
  }

  try {
    const existing = await navigator.serviceWorker.getRegistration()
    if (existing) return existing
  } catch (error) {
    logWarning("Failed to get existing service worker registration", error)
  }

  try {
    const readyPromise = navigator.serviceWorker.ready
      .then((reg) => reg)
      .catch((error) => {
        logWarning("Service worker ready promise rejected", error)
        return null
      })

    const timeout = new Promise<ServiceWorkerRegistration | null>((resolve) => {
      setTimeout(() => resolve(null), SERVICE_WORKER_READY_TIMEOUT_MS)
    })

    const resolved = await Promise.race([readyPromise, timeout])
    if (resolved) return resolved
  } catch (error) {
    logWarning("Failed to await service worker readiness", error)
  }

  try {
    const { registerServiceWorker } = await import("./register-sw")
    const registered = await registerServiceWorker()
    if (registered) return registered
  } catch (error) {
    logWarning("Failed to auto-register service worker", error)
  }

  try {
    return (await navigator.serviceWorker.getRegistration()) ?? null
  } catch (error) {
    logWarning("Failed to get service worker registration after timeout", error)
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
      logWarning("VAPID public key is not configured on the server")
    }
    return cachedVapidPublicKey
  } catch (error) {
    logWarning("Failed to fetch VAPID public key", error)
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
  options?: EnsurePushSubscriptionOptions
): Promise<PushSubscription | null> {
  if (
    !("serviceWorker" in navigator) ||
    !("PushManager" in window) ||
    typeof Notification === "undefined"
  ) {
    return null
  }

  // Use global lock to prevent ANY concurrent calls, regardless of parameters
  if (globalEnsureLock) {
    logWarning("ensurePushSubscription already in progress, awaiting existing lock")
    return globalEnsureLock
  }

  const topics = options?.topics

  const task = (async () => {
    const reg = await resolveServiceWorkerRegistration(options?.registration)

    if (!reg) {
      logWarning("Cannot ensure push subscription without service worker registration")
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
            logWarning("Failed to unsubscribe push subscription", error)
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
        logError("Failed to persist push subscription", error)
      }
    } else {
      setStoredValue(PUSH_LAST_SYNC_STORAGE_KEY, Date.now().toString())
    }

    return sub
  })()

  globalEnsureLock = task

  try {
    return await task
  } finally {
    globalEnsureLock = null
  }
}


type UnsubscribePushOptions = {
  registration?: ServiceWorkerRegistration
  preserveConsent?: boolean
  preserveTopics?: boolean
}

function clearPushLocals(
  options?: Pick<UnsubscribePushOptions, "preserveConsent" | "preserveTopics">
) {
  if (!options?.preserveConsent) {
    try {
      localStorage.removeItem(PUSH_CONSENT_STORAGE_KEY)
    } catch {}
  }
  removeStoredValue(PUSH_LAST_SYNC_STORAGE_KEY)
  removeStoredValue(PUSH_SUB_STORAGE_KEY)
  if (!options?.preserveTopics) {
    removeStoredValue(PUSH_TOPICS_STORAGE_KEY)
  }
}

export async function unsubscribePush(options?: UnsubscribePushOptions) {
  if (!("serviceWorker" in navigator)) {
    clearPushLocals(options)
    return false
  }

  const registration = await resolveServiceWorkerRegistration(options?.registration)

  if (!registration) {
    clearPushLocals(options)
    return false
  }

  const subscription = await registration.pushManager.getSubscription()
  if (!subscription) {
    clearPushLocals(options)
    return true
  }

  const endpoint = subscription.endpoint
  let deleted = false
  if (endpoint) {
    try {
      await deleteSubscription(endpoint)
      deleted = true
    } catch (error) {
      logWarning("Failed to delete push subscription on server", error)
    }
  }

  const ok = await subscription.unsubscribe()

  clearPushLocals(options)

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

  // Prevent parallel sync attempts by reusing existing sync
  if (globalSyncLock) {
    logWarning("Push sync already in progress, awaiting existing lock")
    return globalSyncLock
  }

  const storedTopics = options?.topics ?? parseStoredTopics(getStoredValue(PUSH_TOPICS_STORAGE_KEY))

  globalSyncLock = (async () => {
    try {
      const subscription = await ensurePushSubscription({
        vapidPublicKey: options?.vapidPublicKey,
        registration: options?.registration,
        topics: storedTopics,
        requestPermission: false,
      })
      return subscription
    } catch (error) {
      logError("Failed to soft sync push subscription", error)
      return null
    }
  })()

  try {
    return await globalSyncLock
  } finally {
    globalSyncLock = null
  }
}
