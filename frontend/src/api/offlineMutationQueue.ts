import { storePendingMutation, type PendingMutationRecord } from "@/sw/offline"
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
