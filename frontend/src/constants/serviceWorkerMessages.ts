export const SERVICE_WORKER_MESSAGE_TYPES = {
  SKIP_WAITING: "SKIP_WAITING",
  PROCESS_NOTIFICATION_CLICK_QUEUE: "PROCESS_NOTIFICATION_CLICK_QUEUE",
  SET_API_SESSION_CACHE_KEY: "SET_API_SESSION_CACHE_KEY",
  CLEAR_API_CACHE: "CLEAR_API_CACHE",
} as const

export type ServiceWorkerMessageType =
  (typeof SERVICE_WORKER_MESSAGE_TYPES)[keyof typeof SERVICE_WORKER_MESSAGE_TYPES]

export type ApiCacheControlMessage =
  | {
      type: typeof SERVICE_WORKER_MESSAGE_TYPES.SET_API_SESSION_CACHE_KEY
      sessionHash?: string | null
    }
  | {
      type: typeof SERVICE_WORKER_MESSAGE_TYPES.CLEAR_API_CACHE
    }

export type ServiceWorkerMessage =
  | { type: typeof SERVICE_WORKER_MESSAGE_TYPES.SKIP_WAITING }
  | { type: typeof SERVICE_WORKER_MESSAGE_TYPES.PROCESS_NOTIFICATION_CLICK_QUEUE }
  | ApiCacheControlMessage




