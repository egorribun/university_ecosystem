import { reportOfflineDeadLetter } from "@/app/webVitals"
import { OFFLINE_DEAD_LETTER_MESSAGE_TYPE } from "@/constants/serviceWorkerMessages"

/** Queue names are the `pending-*` store names; anything else is not a dead-letter notice. */
const STORE_NAME_PATTERN = /^pending-[a-z-]{1,40}$/u
/** Reasons are enumerated by the worker (`status-NNN`, `network`, `retries-exhausted:...`). */
const REASON_PATTERN = /^[a-z0-9:-]{1,64}$/u

interface OfflineDeadLetter {
  store: string
  reason: string
}

/** Accepts only the PII-free dead-letter shape; every other message yields null. */
function parseOfflineDeadLetter(data: unknown): OfflineDeadLetter | null {
  if (!data || typeof data !== "object") return null
  const { type, store, reason } = data as Record<string, unknown>
  if (type !== OFFLINE_DEAD_LETTER_MESSAGE_TYPE) return null
  if (typeof store !== "string" || !STORE_NAME_PATTERN.test(store)) return null
  if (typeof reason !== "string" || !REASON_PATTERN.test(reason)) return null
  return { store, reason }
}

const installedContainers = new WeakSet<ServiceWorkerContainer>()

/**
 * Records dead-lettered offline records for the page. This listener is deliberately separate
 * from the account-scoped push bus: a dead-letter notice is not an account message, and it must
 * be observable even while no user is signed in. It accepts only the controlling worker.
 */
export function installOfflineDeadLetterListener(container: ServiceWorkerContainer): void {
  if (installedContainers.has(container)) return
  installedContainers.add(container)
  container.addEventListener("message", (event: MessageEvent) => {
    const controller = container.controller
    if (!controller || event.source !== controller) return
    const deadLetter = parseOfflineDeadLetter(event.data)
    if (deadLetter) reportOfflineDeadLetter(deadLetter)
  })
}
