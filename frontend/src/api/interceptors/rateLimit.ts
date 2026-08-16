import type { InternalAxiosRequestConfig } from "axios"

type QueueConfig = InternalAxiosRequestConfig & {
  __clientRateLimitAcquired?: boolean
  signal?: AbortSignal
}

const parsePositiveInteger = (value: unknown, fallback: number): number => {
  const parsed = Number.parseInt(String(value ?? ""), 10)
  if (Number.isFinite(parsed) && parsed > 0) {
    return parsed
  }
  return fallback
}

export const RATE_LIMIT_DEFAULT_DELAY_MS = 2000
export const RATE_LIMIT_MAX_RETRY = 2
const RATE_LIMIT_WINDOW_MS = 60_000

const CLIENT_RATE_LIMIT_REQUESTS_PER_WINDOW = parsePositiveInteger(
  import.meta.env.VITE_API_RATE_LIMIT_PER_MINUTE,
  90
)

const CLIENT_RATE_LIMIT_MAX_CONCURRENT = parsePositiveInteger(
  import.meta.env.VITE_API_RATE_LIMIT_MAX_CONCURRENT,
  6
)

let rateLimitResetAt = 0
let rateLimitTimer: ReturnType<typeof setTimeout> | null = null
const rateLimitWaiters: Array<() => void> = []

let clientQueueInFlight = 0
const clientQueueWaiters: Array<() => void> = []
const clientQueueTimestamps: number[] = []
let clientQueueTimer: ReturnType<typeof setTimeout> | null = null

const pruneClientQueueTimestamps = () => {
  const threshold = Date.now() - RATE_LIMIT_WINDOW_MS
  while (clientQueueTimestamps.length > 0) {
    const oldest = clientQueueTimestamps[0]!
    if (oldest <= threshold) {
      clientQueueTimestamps.shift()
    } else {
      break
    }
  }
}

const scheduleClientQueueWindowReset = () => {
  pruneClientQueueTimestamps()

  if (clientQueueTimestamps.length < CLIENT_RATE_LIMIT_REQUESTS_PER_WINDOW) {
    if (clientQueueTimer) {
      clearTimeout(clientQueueTimer)
      clientQueueTimer = null
    }
    return
  }

  // The length guard above guarantees an oldest timestamp.  A Date.now()
  // fallback would hide state corruption and adds an impossible branch.
  const oldest = clientQueueTimestamps[0]!
  const target = oldest + RATE_LIMIT_WINDOW_MS
  // Timestamps are appended chronologically, so an existing timer always
  // targets this same oldest entry (or an earlier one).  One timer is enough.
  if (clientQueueTimer) {
    return
  }

  clientQueueTimer = setTimeout(
    () => {
      clientQueueTimer = null
      pruneClientQueueTimestamps()
      notifyClientQueue()
    },
    Math.max(0, target - Date.now())
  )
}

const notifyClientQueue = () => {
  if (clientQueueWaiters.length === 0) {
    return
  }

  while (clientQueueWaiters.length > 0) {
    pruneClientQueueTimestamps()

    if (clientQueueInFlight >= CLIENT_RATE_LIMIT_MAX_CONCURRENT) {
      return
    }

    if (clientQueueTimestamps.length >= CLIENT_RATE_LIMIT_REQUESTS_PER_WINDOW) {
      scheduleClientQueueWindowReset()
      return
    }

    // The loop guard and JavaScript's run-to-completion semantics guarantee a
    // waiter here; no other task can mutate the queue between these statements.
    clientQueueWaiters.shift()!()
  }
}

const tryAcquireClientQueueSlot = (): boolean => {
  pruneClientQueueTimestamps()

  if (clientQueueInFlight >= CLIENT_RATE_LIMIT_MAX_CONCURRENT) {
    return false
  }

  if (clientQueueTimestamps.length >= CLIENT_RATE_LIMIT_REQUESTS_PER_WINDOW) {
    scheduleClientQueueWindowReset()
    return false
  }

  clientQueueInFlight += 1
  clientQueueTimestamps.push(Date.now())
  return true
}

const shouldThrottleRequest = (config: InternalAxiosRequestConfig) => {
  const method = (config.method ?? "get").toString().toLowerCase()
  return method === "get"
}

const throwIfAborted = (signal?: AbortSignal) => {
  if (!signal?.aborted) {
    return
  }

  const reason = signal.reason
  if (reason instanceof Error) {
    throw reason
  }

  throw new DOMException("Aborted", "AbortError")
}

export const waitForClientQueueSlot = async (config: QueueConfig) => {
  if (!shouldThrottleRequest(config as InternalAxiosRequestConfig)) {
    return
  }

  while (true) {
    throwIfAborted(config.signal)
    if (tryAcquireClientQueueSlot()) {
      config.__clientRateLimitAcquired = true
      return
    }

    await new Promise<void>((resolve) => {
      clientQueueWaiters.push(resolve)
    })
  }
}

export const releaseClientQueueSlot = (config?: QueueConfig) => {
  if (!config?.__clientRateLimitAcquired) {
    return
  }

  config.__clientRateLimitAcquired = false

  if (!shouldThrottleRequest(config as InternalAxiosRequestConfig)) {
    return
  }

  if (clientQueueInFlight > 0) {
    clientQueueInFlight -= 1
  }

  pruneClientQueueTimestamps()
  notifyClientQueue()
}

export const scheduleRateLimitWindow = (delayMs: number) => {
  const target = Date.now() + Math.max(delayMs, 0)
  if (rateLimitTimer && target <= rateLimitResetAt) {
    return
  }

  rateLimitResetAt = target

  if (rateLimitTimer) {
    clearTimeout(rateLimitTimer)
    rateLimitTimer = null
  }

  rateLimitTimer = setTimeout(
    () => {
      rateLimitTimer = null
      rateLimitResetAt = 0
      while (rateLimitWaiters.length > 0) {
        const resolve = rateLimitWaiters.shift()
        resolve?.()
      }
    },
    Math.max(0, target - Date.now())
  )
}

// RZ-31-04: Accept optional AbortSignal so callers (e.g. 429 retry in client.ts)
// can cancel the wait when the user navigates away or the component unmounts.
// Follows the same pattern established by TD-26-02/03 in the WS ticket fetch.
export const waitForRateLimitWindow = async (signal?: AbortSignal) => {
  if (rateLimitResetAt <= Date.now()) {
    return
  }
  if (signal?.aborted) {
    throw new DOMException("Aborted", "AbortError")
  }

  await new Promise<void>((resolve, reject) => {
    const onAbort = () => reject(new DOMException("Aborted", "AbortError"))
    signal?.addEventListener("abort", onAbort, { once: true })
    rateLimitWaiters.push(() => {
      signal?.removeEventListener("abort", onAbort)
      resolve()
    })
  })
}

export const isRateLimited = () => rateLimitResetAt > Date.now()

// DEBT-03 (audit Wave 11): Reset the server-side 429 rate-limit window when the
// network recovers.  Without this, a user who goes offline mid-window returns to
// find the client still blocked — even though the server's window expired while they
// were offline (e.g., 60s window, 30s offline = 30s of unnecessary client blocking).
if (typeof window !== "undefined") {
  window.addEventListener("online", () => {
    if (rateLimitResetAt !== 0 && Date.now() >= rateLimitResetAt) {
      // Window has already expired — unblock queued requests immediately
      if (rateLimitTimer !== null) {
        clearTimeout(rateLimitTimer)
        rateLimitTimer = null
      }
      rateLimitResetAt = 0
      while (rateLimitWaiters.length > 0) {
        rateLimitWaiters.shift()?.()
      }
    }
    // If the window is still active, leave it — the server-side limit is still valid.
  })
}
