import {
  deleteSubscription,
  fetchSessionUserId,
  getVapidPublicKey,
  saveSubscription,
} from "@/api/notifications"
import { logError, logWarning } from "@/app/logger"
import { getConfirmedUserId, waitForConfirmedUserId } from "@/stores/authIdentity"
import { useAuthStore } from "@/stores/useAuthStore"
import { StorageItem, pushConsentStorage } from "@/utils/storage"

const SUBSCRIPTION_EXPIRY_THRESHOLD_MS = 3 * 24 * 60 * 60 * 1000 // 3 days
const PERSIST_MAX_ATTEMPTS = 3
const PERSIST_BASE_DELAY_MS = 500
const PUSH_TOPICS_STORAGE_VERSION = 2
// Logout must not hang on a slow push unbind; the server remains authoritative.
const PUSH_RELEASE_TIMEOUT_MS = 3_000

// Storage Items for Push
const pushSubStorage = new StorageItem<unknown>("push:last_payload")
const pushTopicsStorage = new StorageItem<unknown>("push:last_topics")
const pushOwnerStorage = new StorageItem<string>("push:last_owner")

const SERVICE_WORKER_READY_TIMEOUT_MS = 2000
let cachedVapidPublicKey: string | null | undefined

type NormalizedTopics = string[] | undefined

type MaybeUserId = string | number | null | undefined

function normalizeUserId(input: MaybeUserId): string | null {
  if (typeof input !== "string" && typeof input !== "number") return null
  const normalized = String(input).trim()
  return normalized ? normalized : null
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
  return getConfirmedUserId(useAuthStore.getState())
}

type StoredTopicsPayload = Record<string, unknown>

/** A versioned object payload; a legacy topic array or a primitive is not. */
function storedPayload(value: unknown): StoredTopicsPayload | null {
  return typeof value === "object" && !Array.isArray(value) ? (value as StoredTopicsPayload) : null
}

/** The shared selection of a payload; `topics` is its legacy name. */
function storedSharedTopics(stored: StoredTopicsPayload): string[] | undefined {
  return normalizeTopics(stored.shared !== undefined ? stored.shared : stored.topics)
}

/** The normalized per-account selections of a payload, optionally without one account. */
function storedPerUserTopics(
  stored: StoredTopicsPayload | null,
  withoutUserId?: string | null
): Record<string, string[]> {
  const entries: Record<string, string[]> = {}
  for (const [key, value] of Object.entries(stored?.perUser ?? {})) {
    const topics = normalizeTopics(value)
    if (topics !== undefined && key !== withoutUserId) entries[key] = topics
  }
  return entries
}

export function parseStoredTopics(
  raw: unknown,
  options?: { userId?: MaybeUserId }
): NormalizedTopics {
  const userId = normalizeUserId(options?.userId) ?? readActiveUserId()
  // Legacy writers stored the payload as a JSON string.
  let parsed = raw
  if (typeof raw === "string") {
    try {
      parsed = JSON.parse(raw)
    } catch {
      // Not JSON: unusable like any other non-payload value.
    }
  }

  if (Array.isArray(parsed)) {
    return normalizeTopics(parsed)
  }
  const stored = storedPayload(parsed)
  if (!stored) return undefined

  if (userId) {
    const perUser = stored.perUser as Record<string, unknown> | null | undefined
    const userTopics = normalizeTopics(perUser?.[userId])
    if (userTopics !== undefined) {
      return userTopics
    }
  }
  return storedSharedTopics(stored)
}

export function getPersistedTopics(options?: { userId?: MaybeUserId }): string[] | undefined {
  return parseStoredTopics(pushTopicsStorage.get(), options)
}

function buildTopicsPayload(
  nextTopics: string[] | null | undefined,
  stored: unknown,
  userId: string | null
): StoredTopicsPayload | null {
  const existing = storedPayload(stored)

  if (nextTopics == null) {
    // Clearing keeps the other accounts' selections and, when an account
    // clears its own, the shared selection.
    const perUser = storedPerUserTopics(existing, userId)
    const shared = userId && existing ? storedSharedTopics(existing) : undefined
    const hasPerUser = Object.keys(perUser).length > 0
    if (!hasPerUser && shared === undefined) {
      return null
    }
    // An undefined `shared` is not serialized.
    return {
      version: PUSH_TOPICS_STORAGE_VERSION,
      ...(hasPerUser ? { perUser } : {}),
      shared,
    }
  }

  const normalizedTopics = normalizeTopics(nextTopics) ?? []
  const perUser = storedPerUserTopics(existing)

  if (userId) {
    return {
      version: PUSH_TOPICS_STORAGE_VERSION,
      // A legacy topic array is the shared selection.
      shared: existing ? storedSharedTopics(existing) : normalizeTopics(stored),
      perUser: { ...perUser, [userId]: normalizedTopics },
    }
  }

  return {
    version: PUSH_TOPICS_STORAGE_VERSION,
    ...(Object.keys(perUser).length > 0 ? { perUser } : {}),
    shared: normalizedTopics,
  }
}

export function setPersistedTopics(
  topics: string[] | null | undefined,
  options?: { userId?: MaybeUserId }
): void {
  const userId = normalizeUserId(options?.userId) ?? readActiveUserId()
  const payload = buildTopicsPayload(topics, pushTopicsStorage.get(), userId)

  if (payload === null) {
    pushTopicsStorage.remove()
    return
  }
  try {
    pushTopicsStorage.set(payload)
  } catch {
    // A failed write only loses the local mirror of the server preference.
  }
}

function sleep(ms: number) {
  return new Promise<void>((resolve) => setTimeout(resolve, ms))
}

function pushIdentityError(): Error {
  const error = new Error("Push identity is not confirmed for this account")
  error.name = "PushIdentityUnconfirmedError"
  return error
}

// saveSubscription rethrows a sanitized error that keeps only the HTTP status.
function httpStatus(error: unknown): unknown {
  return (error as { response?: { status?: unknown } } | null)?.response?.status
}

async function persistSubscriptionWithBackoff(
  payload: Parameters<typeof saveSubscription>[0],
  owner: string,
  topics?: string[]
): Promise<void> {
  // Add jitter to reduce the probability of thundering herd
  const jitter = () => Math.random() * PERSIST_BASE_DELAY_MS
  // Keep retry cardinality finite even if a mutation removes a branch body:
  // at most PERSIST_MAX_ATTEMPTS server writes are ever attempted.
  const attempts = Array.from({ length: PERSIST_MAX_ATTEMPTS }, (_, index) => index + 1)

  for (const attempt of attempts) {
    // Queued or retried writes may start after the account changed.
    if (readActiveUserId() !== owner) throw pushIdentityError()
    let response: Awaited<ReturnType<typeof saveSubscription>>
    try {
      response = await saveSubscription(payload, topics)
    } catch (error) {
      const status = httpStatus(error)
      if (status === 409) {
        // The API returns 409 only after its own recovery attempts fail.
        // It does not establish ownership of this endpoint for this user.
        logWarning("Subscription conflict (409), server state unconfirmed")
        throw error
      }
      if (status === 429) {
        // 429 means too many requests - stop immediately, don't retry
        logWarning("Rate limited (429), stopping retries")
        throw error
      }
      if (attempt >= PERSIST_MAX_ATTEMPTS) {
        logError("Failed to persist push subscription", error)
        throw error
      }
      const delay = Math.min(30000, 2 ** (attempt - 1) * PERSIST_BASE_DELAY_MS) + jitter()
      await sleep(delay)
      continue
    }
    // The response is only meaningful for the account that sent it.
    if (readActiveUserId() !== owner) throw pushIdentityError()
    pushSubStorage.set(payload)
    pushOwnerStorage.set(owner)
    // Implicit writes follow the server-side canonical preference and must
    // not overwrite the local mirror of an explicit choice.
    if (topics) {
      setPersistedTopics(response.topics ?? topics)
    }
    return
  }
}

// Re-exported for compatibility if needed, but preferable to use storage directly
export const PUSH_CONSENT_STORAGE_KEY = "push-notification-consent"

export function hasPushConsent(): boolean {
  return pushConsentStorage.get() === "granted"
}

export function setPushConsent(consented: boolean): void {
  if (consented) {
    pushConsentStorage.set("granted")
  } else {
    pushConsentStorage.remove()
  }
}

/**
 * Recovers push consent from browser state when localStorage was cleared.
 * If Notification.permission is 'granted' and the browser still has an active
 * push subscription, re-binds it to the confirmed account (without choosing
 * topics) and restores the consent flag only after the server accepted it.
 *
 * @returns true if consent was recovered
 */
export async function recoverPushConsentFromBrowser(
  registration?: ServiceWorkerRegistration,
  owner?: string
): Promise<boolean> {
  if (!isPushSupported()) return false

  // Already have consent, nothing to recover
  if (hasPushConsent()) return false

  // Browser permission not granted, can't recover
  if (Notification.permission !== "granted") return false

  // Check if browser still has an active push subscription
  const reg = await resolveServiceWorkerRegistration(registration)
  if (!reg) return false

  try {
    if (!(await reg.pushManager.getSubscription())) return false
    // A browser subscription alone does not prove that the authenticated
    // account owns it on the server. Recover consent only after persistence.
    if (!(await ensurePushSubscription({ registration: reg, owner }))) return false
  } catch (error) {
    logWarning("Failed to re-sync recovered push subscription", error)
    return false
  }

  setPushConsent(true)
  return true
}

export async function resolveServiceWorkerRegistration(
  registration?: ServiceWorkerRegistration
): Promise<ServiceWorkerRegistration | null> {
  if (registration) return registration
  // Lighthouse uses a synthetic authenticated build and deliberately skips
  // the normal service-worker bootstrap in `main.tsx`.  Push preferences are
  // mounted by a deferred overlay, however, and their subscription probe can
  // otherwise fall through to `registerServiceWorker()` after the readiness
  // timeout.  Registering a worker in an audit profile triggers a
  // controllerchange reload, so Lighthouse measures a second document and
  // spends the navigation budget on a reload instead of the requested route.
  // Keep the audit profile side-effect free; this literal is tree-shaken from
  // normal production/development bundles, which retain the full push flow.
  if (import.meta.env.VITE_LHCI === "true") return null
  if (typeof navigator === "undefined" || !("serviceWorker" in navigator)) {
    return null
  }

  try {
    const existing = await navigator.serviceWorker.getRegistration()
    if (existing) return existing
  } catch (error) {
    logWarning("Failed to get existing service worker registration", error)
  }

  let readinessTimeoutId: ReturnType<typeof setTimeout> | undefined
  try {
    const readyPromise = navigator.serviceWorker.ready
      .then((reg) => reg)
      .catch((error) => {
        logWarning("Service worker ready promise rejected", error)
        return null
      })

    const timeout = new Promise<ServiceWorkerRegistration | null>((resolve) => {
      readinessTimeoutId = setTimeout(() => resolve(null), SERVICE_WORKER_READY_TIMEOUT_MS)
    })

    const resolved = await Promise.race([readyPromise, timeout])
    if (resolved) return resolved
  } catch (error) {
    logWarning("Failed to await service worker readiness", error)
  } finally {
    clearTimeout(readinessTimeoutId)
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
  // atob() implements forgiving-base64, which accepts unpadded input, so only
  // the URL-safe alphabet needs mapping.
  const rawData = atob(base64String.replace(/-/g, "+").replace(/_/g, "/"))
  return Uint8Array.from([...rawData], (character) => character.charCodeAt(0))
}

type EnsurePushSubscriptionOptions = {
  registration?: ServiceWorkerRegistration
  vapidPublicKey?: string
  topics?: string[]
  requestPermission?: boolean
  /** Abort unless this account is still the confirmed one. */
  owner?: string
}

type EnsureTask = {
  owner: string
  explicit: boolean
  promise: Promise<PushSubscription | null>
}

// Tail of the serialized sync queue. Only implicit syncs for the same owner
// may share one run; explicit topic updates and other accounts always wait for
// the previous run to settle and then perform their own.
let ensureTail: EnsureTask | null = null

export async function ensurePushSubscription(
  options?: EnsurePushSubscriptionOptions
): Promise<PushSubscription | null> {
  if (!isPushSupported()) return null

  // Fail closed: never persist without a confirmed authenticated identity,
  // nor for a different account than the caller verified.
  const owner = readActiveUserId()
  if (!owner || (options?.owner !== undefined && options.owner !== owner)) return null

  const explicit = options?.topics !== undefined
  const previous = ensureTail
  if (previous?.owner === owner && !previous.explicit && !explicit) {
    return previous.promise
  }

  const task: EnsureTask = {
    owner,
    explicit,
    // Wait for the previous run to settle, whatever its outcome.
    promise: Promise.allSettled([previous?.promise]).then(() =>
      runEnsurePushSubscription(owner, options)
    ),
  }
  ensureTail = task
  const release = () => {
    if (ensureTail === task) ensureTail = null
  }
  task.promise.then(release, release)
  return task.promise
}

async function runEnsurePushSubscription(
  owner: string,
  options?: EnsurePushSubscriptionOptions
): Promise<PushSubscription | null> {
  const topics = options?.topics
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

    // Number(null) is 0: a subscription without an expiry never expires.
    const expiresAt = Number(sub.expirationTime)
    const isExpiringSoon =
      expiresAt > 0 && expiresAt - Date.now() < SUBSCRIPTION_EXPIRY_THRESHOLD_MS

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

  // The owner marker keeps the unchanged-payload shortcut from skipping the
  // POST that re-binds an endpoint after an account change.
  const shouldPersist =
    topics !== undefined ||
    pushOwnerStorage.get() !== owner ||
    JSON.stringify(pushSubStorage.get()) !== JSON.stringify(payload)

  if (shouldPersist) {
    try {
      await persistSubscriptionWithBackoff(payload, owner, topics)
    } catch (error) {
      logError("Failed to persist push subscription", error)
      throw error
    }
  }

  return sub
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
    pushConsentStorage.remove()
  }
  pushSubStorage.remove()
  pushOwnerStorage.remove()
  if (!options?.preserveTopics) {
    pushTopicsStorage.remove()
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
    return await reg.pushManager.getSubscription()
  } catch {
    return null
  }
}

/**
 * Returns this browser's push subscription only for the account that enabled
 * push here (the owner marker). Another account signed in on the same browser
 * sees push as disabled and must opt in itself (ADR-041).
 */
export async function getOwnedPushSubscription(
  userId: string | null,
  registration?: ServiceWorkerRegistration
): Promise<PushSubscription | null> {
  if (userId === null || pushOwnerStorage.get() !== userId) return null
  return getExistingPushSubscription(registration)
}

type SoftSyncOptions = {
  registration?: ServiceWorkerRegistration
  vapidPublicKey?: string
  topics?: string[]
  owner?: string
}

export async function softSyncPushSubscription(
  options?: SoftSyncOptions
): Promise<PushSubscription | null> {
  if (!isPushSupported()) return null
  if (Notification.permission !== "granted") return null

  try {
    // Permission is already granted, so this never prompts.
    return await ensurePushSubscription(options)
  } catch (error) {
    logError("Failed to soft sync push subscription", error)
    return null
  }
}

type ConfirmedIdentitySyncOptions = {
  registration?: ServiceWorkerRegistration
  expectedUserId?: string
  timeoutMs?: number
}

/**
 * Re-binds this browser's push subscription once auth has confirmed a real
 * account (optionally a specific one). Never sends topics: the server applies
 * the account's canonical preference. Resolves null when nothing was synced.
 *
 * Browser permission and local consent belong to the account that enabled
 * push here (the owner marker). Another account signing in on this browser
 * must opt in explicitly; it never inherits the endpoint or the consent.
 */
export async function syncPushForConfirmedIdentity({
  registration,
  expectedUserId,
  timeoutMs,
}: ConfirmedIdentitySyncOptions = {}): Promise<PushSubscription | null> {
  const owner = await waitForConfirmedUserId({ expectedUserId, timeoutMs })
  if (!owner) return null
  const browserOwner = pushOwnerStorage.get()
  if (browserOwner !== owner) {
    if (browserOwner !== null) await retireForeignSubscription(registration)
    return null
  }
  // A cached profile does not prove which account the session cookie
  // belongs to; ids from authenticated responses (expectedUserId) do.
  if (expectedUserId === undefined) {
    const sessionOwner = await fetchSessionUserId().catch((error: unknown) => {
      logWarning("Push session check failed", error)
      return null
    })
    if (sessionOwner !== owner) return null
  }
  await recoverPushConsentFromBrowser(registration, owner)
  if (!hasPushConsent()) return null
  return softSyncPushSubscription({ registration, owner })
}

/**
 * Another account enabled push on this browser and may still be bound to
 * this endpoint on the server (e.g. its session expired without logout).
 * Revoke the endpoint itself so its notifications stop arriving here.
 */
async function retireForeignSubscription(registration?: ServiceWorkerRegistration) {
  pushOwnerStorage.remove()
  pushSubStorage.remove()
  setPushConsent(false)
  const subscription = await getExistingPushSubscription(registration)
  await subscription?.unsubscribe().catch((error: unknown) => {
    logWarning("Failed to retire another account's push subscription", error)
  })
}

/**
 * Best-effort logout hook: detaches this browser endpoint from the current
 * account on the server while keeping the browser subscription, the owner
 * marker and the local topic mirror, so only the same account's next
 * confirmed login re-binds it. Never rejects and never blocks longer than
 * PUSH_RELEASE_TIMEOUT_MS.
 */
export async function releasePushServerBinding(): Promise<void> {
  // Forget the persisted payload so the next sync re-creates the server row.
  pushSubStorage.remove()
  if (!isPushSupported()) return

  const release = navigator.serviceWorker
    .getRegistration()
    .then((registration) => registration?.pushManager.getSubscription())
    .then(async (subscription) => {
      if (!subscription) return
      try {
        await deleteSubscription(subscription.endpoint)
      } catch (error) {
        logWarning("Failed to release push subscription binding", error)
        // The server may still route this account's notifications here:
        // revoke the endpoint itself and require an explicit re-enable.
        pushOwnerStorage.remove()
        await subscription.unsubscribe()
      }
    })
    .catch((error: unknown) => {
      logWarning("Failed to release push subscription binding", error)
    })
  let timer: ReturnType<typeof setTimeout> | undefined
  const guard = new Promise<void>((resolve) => {
    timer = setTimeout(resolve, PUSH_RELEASE_TIMEOUT_MS)
  })
  await Promise.race([release, guard])
  clearTimeout(timer)
}
