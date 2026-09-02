/**
 * Keeps service-worker push delivery alive while the optional toast UI is
 * being loaded.  The root shell starts this bridge during its first client
 * effect, while the heavier toast implementation subscribes when its lazy
 * chunk is ready.  Without the bridge, a notification arriving in that
 * window is lost because ServiceWorkerContainer does not replay messages.
 */

export type PushMessageSubscriber = (event: MessageEvent<unknown>) => void

const MAX_PENDING_MESSAGES = 20

let attachedContainer: ServiceWorkerContainer | null = null
let bridgeListener: ((event: MessageEvent<unknown>) => void) | null = null
const subscribers = new Set<PushMessageSubscriber>()
const pendingMessages: MessageEvent<unknown>[] = []

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
    if (subscribers.size === 0) {
      pendingMessages.push(event)
      if (pendingMessages.length > MAX_PENDING_MESSAGES) pendingMessages.shift()
      return
    }
    for (const subscriber of [...subscribers]) subscriber(event)
  }
  attachedContainer = container
  bridgeListener = listener
  container.addEventListener("message", listener)
}

/** Start buffering push messages before the lazy toast UI is available. */
export const ensurePushMessageBridge = (): void => {
  attachBridge()
}

/** Subscribe to push messages and replay messages received before subscription. */
export const subscribeToPushMessages = (subscriber: PushMessageSubscriber): (() => void) => {
  attachBridge()
  subscribers.add(subscriber)
  const buffered = pendingMessages.splice(0)
  for (const event of buffered) subscriber(event)
  return () => {
    subscribers.delete(subscriber)
  }
}
