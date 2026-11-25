import {
  discardSessionRecords,
  storePendingMutation,
  type PendingMutationRecord,
} from "@/sw/offline"
import { currentReplaySessionNonce } from "@/sw/replayCredentialResponder"
import { SERVICE_WORKER_MESSAGE_TYPES } from "@/constants/serviceWorkerMessages"

export async function enqueueOfflineMutation(mutation: {
  url: string
  method: "POST" | "PUT" | "PATCH" | "DELETE"
  payload: unknown
  headers?: Record<string, string>
  category?: "events" | "news" | "messenger" | "profile" | "schedule" | "general"
}) {
  const record: Omit<
    PendingMutationRecord,
    "mutationId" | "idempotencyKey" | "timestamp" | "retryCount"
  > = {
    url: mutation.url,
    method: mutation.method,
    payload: mutation.payload,
    headers: mutation.headers,
    category: mutation.category ?? "general",
    // Bind to the verified session now; an unverifiable session leaves the record held.
    sessionNonce: currentReplaySessionNonce(),
  }

  await storePendingMutation(record)

  if (typeof navigator === "undefined") return
  if (!("serviceWorker" in navigator)) return
  const controller = navigator.serviceWorker.controller
  if (!controller) return

  try {
    const reg = await navigator.serviceWorker.ready
    if ("sync" in reg) {
      await (
        reg as unknown as {
          sync: { register: (tag: string) => Promise<void> }
        }
      ).sync.register("sync-offline-mutations")
    } else {
      controller.postMessage({
        type: SERVICE_WORKER_MESSAGE_TYPES.PROCESS_OFFLINE_QUEUES,
      })
    }
  } catch {
    controller.postMessage({
      type: SERVICE_WORKER_MESSAGE_TYPES.PROCESS_OFFLINE_QUEUES,
    })
  }
}

/** The verified session that queued records are bound to, or null when unverified. */
export const captureOfflineSession = currentReplaySessionNonce

/** Bounded so an unavailable or busy queue never delays sign-out. */
const DISCARD_TIMEOUT_MS = 3_000

/**
 * Removes the offline changes queued by an ending session so they are never sent later.
 * Resolves true only when at least one queued change was removed in time.
 */
export async function discardOfflineSession(sessionNonce: string): Promise<boolean> {
  let timer: ReturnType<typeof setTimeout> | undefined
  try {
    const discarded = await Promise.race([
      discardSessionRecords(sessionNonce),
      new Promise<number>((resolve) => {
        timer = setTimeout(() => resolve(0), DISCARD_TIMEOUT_MS)
      }),
    ])
    return discarded > 0
  } catch {
    return false
  } finally {
    clearTimeout(timer)
  }
}
