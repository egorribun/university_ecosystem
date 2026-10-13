/**
 * Keeps service-worker push delivery alive while the optional toast UI is
 * being loaded.  The root shell starts this bridge during its first client
 * effect, while the heavier toast implementation subscribes when its lazy
 * chunk is ready.  Without the bridge, a notification arriving in that
 * window is lost because ServiceWorkerContainer does not replay messages.
 */

import { getConfirmedUserId } from "@/stores/authIdentity"
import { useAuthStore } from "@/stores/useAuthStore"

type PushAuthSnapshot = Parameters<typeof getConfirmedUserId>[0]

export type PushIdentitySnapshot = { userId: string | null; revision: number }

export type PushMessageSubscriber = (event: MessageEvent<unknown>, ownerId: string) => void

const MAX_PENDING_MESSAGES = 20
const SESSION_GENERATION_STORAGE_KEY = "ecosystem.session.generation.v1"
const PUSH_BUFFER_STORAGE_KEY_PREFIX = "livePushToastBuffer:"

export const getPushBufferStorageKey = (userId: string): string =>
  PUSH_BUFFER_STORAGE_KEY_PREFIX + encodeURIComponent(userId)

const clearAccountBuffer = (userId: string): void => {
  if (typeof window === "undefined") return
  try {
    const storage = window.localStorage
    const removeItem = storage?.removeItem
    if (typeof removeItem === "function") removeItem.call(storage, getPushBufferStorageKey(userId))
  } catch {
    // Storage can be unavailable in private or restricted browsing contexts.
  }
}

let attachedContainer: ServiceWorkerContainer | null = null
let bridgeListener: ((event: MessageEvent<unknown>) => void) | null = null
let currentUserId: string | null = null
let currentIdentitySnapshot: PushIdentitySnapshot = { userId: null, revision: 0 }
let unsubscribeAuth: (() => void) | null = null
const subscribers = new Set<PushMessageSubscriber>()
const identitySubscribers = new Set<() => void>()
let sessionStorageListener: ((event: StorageEvent) => void) | null = null
const pendingMessages: Array<{ event: MessageEvent<unknown>; ownerId: string }> = []

/**
 * Keep an already-confirmed identity through a transient loading state only
 * while the same real browser session and user id remain present. A new
 * identity is never trusted until getConfirmedUserId accepts the settled
 * store snapshot.
 */
export function resolvePushUserId(
  snapshot: PushAuthSnapshot,
  previousUserId: string | null
): string | null {
  const confirmedUserId = getConfirmedUserId(snapshot)
  if (confirmedUserId !== null) return confirmedUserId
  if (!snapshot.loading || previousUserId === null) return null

  const rawId: unknown = snapshot.user?.id
  if (
    (typeof rawId !== "string" && typeof rawId !== "number") ||
    String(rawId).trim() !== previousUserId
  ) {
    return null
  }
  return getConfirmedUserId({ user: snapshot.user, loading: false }) === previousUserId
    ? previousUserId
    : null
}

const syncCurrentUserId = (notifySubscribers = false): string | null => {
  const nextUserId = resolvePushUserId(useAuthStore.getState(), currentUserId)
  if (nextUserId !== currentUserId) {
    const previousUserId = currentUserId
    currentUserId = nextUserId
    currentIdentitySnapshot = {
      userId: nextUserId,
      revision: currentIdentitySnapshot.revision + 1,
    }
    pendingMessages.length = 0
    if (previousUserId !== null) clearAccountBuffer(previousUserId)
    if (notifySubscribers) {
      for (const subscriber of [...identitySubscribers]) subscriber()
    }
  }
  return currentUserId
}

const ensureSessionGenerationTracking = (): void => {
  if (typeof window === "undefined" || sessionStorageListener !== null) return
  const listener = (event: StorageEvent) => {
    if (event.key !== SESSION_GENERATION_STORAGE_KEY && event.key !== null) return
    syncCurrentUserId(true)
  }
  sessionStorageListener = listener
  window.addEventListener("storage", listener)
}

const ensureIdentityTracking = (): void => {
  if (unsubscribeAuth === null) {
    syncCurrentUserId()
    unsubscribeAuth = useAuthStore.subscribe(() => {
      syncCurrentUserId(true)
    })
  }
  ensureSessionGenerationTracking()
}

/** Subscribe to confirmed identity transitions from auth state or another tab. */
export const subscribeToPushIdentity = (subscriber: () => void): (() => void) => {
  ensureIdentityTracking()
  identitySubscribers.add(subscriber)
  return () => {
    identitySubscribers.delete(subscriber)
  }
}

/** Read the current confirmed identity and its transition revision. */
export const getCurrentPushIdentitySnapshot = (): PushIdentitySnapshot => {
  ensureIdentityTracking()
  syncCurrentUserId()
  return currentIdentitySnapshot
}

/** Read the account currently permitted to receive service-worker messages. */
export const getCurrentPushUserId = (): string | null => getCurrentPushIdentitySnapshot().userId

const resolveServiceWorker = (): ServiceWorkerContainer | null => {
  if (typeof navigator === "undefined") return null
  const container = navigator.serviceWorker
  if (!container || typeof container.addEventListener !== "function") return null
  return container
}

const detachBridge = () => {
  if (attachedContainer && bridgeListener) {
    attachedContainer.removeEventListener("message", bridgeListener)
  }
  attachedContainer = null
  bridgeListener = null
}

const isPushMessage = (event: MessageEvent<unknown>): boolean => {
  if (!event.data || typeof event.data !== "object") return false
  const type = (event.data as { type?: unknown }).type
  return type === "PUSH_NOTIFICATION" || type === "SYNC_COMPLETE"
}

const attachBridge = () => {
  ensureIdentityTracking()
  const container = resolveServiceWorker()
  if (!container) {
    detachBridge()
    pendingMessages.length = 0
    return
  }
  if (attachedContainer === container && bridgeListener) return

  if (attachedContainer && attachedContainer !== container) pendingMessages.length = 0
  detachBridge()
  const listener = (event: MessageEvent<unknown>) => {
    if (!isPushMessage(event)) return
    const ownerId = getCurrentPushUserId()
    if (ownerId === null) return
    if (event.data && typeof event.data === "object") {
      const message = event.data as { type?: unknown; recipientUserId?: unknown }
      if (message.type === "PUSH_NOTIFICATION") {
        if (
          typeof message.recipientUserId !== "string" ||
          message.recipientUserId.length === 0 ||
          message.recipientUserId !== ownerId
        ) {
          return
        }
      }
    }
    if (subscribers.size === 0) {
      pendingMessages.push({ event, ownerId })
      if (pendingMessages.length > MAX_PENDING_MESSAGES) pendingMessages.shift()
      return
    }
    for (const subscriber of [...subscribers]) subscriber(event, ownerId)
  }
  attachedContainer = container
  bridgeListener = listener
  container.addEventListener("message", listener)
}

/** Start buffering push messages before the lazy toast UI is available. */
export const ensurePushMessageBridge = (): void => {
  attachBridge()
}

/** Subscribe to push messages and replay only messages owned by the current account. */
export const subscribeToPushMessages = (subscriber: PushMessageSubscriber): (() => void) => {
  attachBridge()
  subscribers.add(subscriber)
  const ownerId = getCurrentPushUserId()
  const buffered = pendingMessages.splice(0)
  if (ownerId !== null) {
    for (const item of buffered) {
      if (item.ownerId === ownerId) subscriber(item.event, item.ownerId)
    }
  }
  return () => {
    subscribers.delete(subscriber)
  }
}
