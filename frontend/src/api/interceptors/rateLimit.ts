import type { InternalAxiosRequestConfig } from "axios"

type QueueConfig = InternalAxiosRequestConfig & {
  __clientRateLimitAcquired?: boolean
  signal?: AbortSignal
}

type ClientQueueWaiter = {
  resolve: () => void
}

export const parsePositiveInteger = (value: unknown, fallback: number): number => {
  const parsed = Number.parseInt(String(value ?? 0), 10)
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
const rateLimitWaiters: Array<() => void> = new Array<() => void>()

let clientQueueInFlight = 0
const clientQueueWaiters: ClientQueueWaiter[] = new Array<ClientQueueWaiter>()
const clientQueueTimestamps: number[] = new Array<number>()
let clientQueueTimer: ReturnType<typeof setTimeout> | null = null

const pruneClientQueueTimestamps = () => {
  const threshold = Date.now() - RATE_LIMIT_WINDOW_MS
  // Timestamps are appended in chronological order. Remove the expired
  // prefix in one bounded operation instead of a loop: a mutation that drops
  // a loop body must never be able to leave a request promise pending forever.
  const firstFreshIndex = clientQueueTimestamps.findIndex((timestamp) => timestamp > threshold)
  if (firstFreshIndex < 0) {
    clientQueueTimestamps.splice(0)
    return
  }
  if (firstFreshIndex > 0) clientQueueTimestamps.splice(0, firstFreshIndex)
}

const scheduleClientQueueWindowReset = () => {
  pruneClientQueueTimestamps()

  if (clientQueueTimestamps.length < CLIENT_RATE_LIMIT_REQUESTS_PER_WINDOW) {
    // Clearing an absent timer is a platform-defined no-op. Keeping this
    // unconditional avoids encoding a second state invariant ("below the
    // window limit implies a timer exists") that callers do not need.
    clearTimeout(clientQueueTimer as ReturnType<typeof setTimeout>)
    clientQueueTimer = null
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

  pruneClientQueueTimestamps()

  if (clientQueueInFlight >= CLIENT_RATE_LIMIT_MAX_CONCURRENT) {
    return
  }

  if (clientQueueTimestamps.length >= CLIENT_RATE_LIMIT_REQUESTS_PER_WINDOW) {
    scheduleClientQueueWindowReset()
    return
  }

  // Resolve at most the currently available concurrency/window capacity. The
  // waiters reacquire asynchronously, so this batch size is calculated before
  // any of them can mutate the counters.
  const grantCount = Math.max(
    0,
    Math.min(
      clientQueueWaiters.length,
      CLIENT_RATE_LIMIT_MAX_CONCURRENT - clientQueueInFlight,
      CLIENT_RATE_LIMIT_REQUESTS_PER_WINDOW - clientQueueTimestamps.length
    )
  )
  clientQueueWaiters.splice(0, grantCount).forEach(({ resolve }) => resolve())
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

const abortError = (signal?: AbortSignal): Error => {
  const reason = (Object(signal) as { reason?: unknown }).reason
  return reason instanceof Error ? reason : new DOMException("Aborted", "AbortError")
}

const throwIfAborted = (signal?: AbortSignal) => {
  if (Object(signal).aborted !== true) return
  throw abortError(signal)
}

const waitForClientQueueSlotInternal = async (config: QueueConfig): Promise<void> => {
  throwIfAborted(config.signal)
  if (tryAcquireClientQueueSlot()) {
    config.__clientRateLimitAcquired = true
    return
  }

  let removeAbortListener: (() => void) | undefined
  try {
    await new Promise<void>((resolve, reject) => {
      let granted = false
      const waiter: ClientQueueWaiter = {
        resolve: () => {
          granted = true
          resolve()
        },
      }
      const onAbort = () => {
        const index = clientQueueWaiters.indexOf(waiter)
        if (index >= 0) clientQueueWaiters.splice(index, 1)
        if (!granted) reject(abortError(config.signal))
        // If the waiter was granted just before its signal aborted, its
        // recursive reacquire will fail. Wake the next queued request rather
        // than leaving it blocked behind the cancelled request.
        notifyClientQueue()
      }
      removeAbortListener = config.signal
        ? () => config.signal?.removeEventListener("abort", onAbort)
        : undefined
      config.signal?.addEventListener("abort", onAbort, { once: true })
      clientQueueWaiters.push(waiter)
    })
  } finally {
    removeAbortListener?.()
  }

  try {
    await waitForClientQueueSlotInternal(config)
  } catch (error) {
    // A signal can abort after the waiter is resolved but before the
    // recursive acquire runs. Make sure another waiter can use the slot.
    notifyClientQueue()
    throw error
  }
}

export const waitForClientQueueSlot = async (config: QueueConfig) => {
  if (!shouldThrottleRequest(config as InternalAxiosRequestConfig)) {
    return
  }

  await waitForClientQueueSlotInternal(config)
}

export const releaseClientQueueSlot = (config?: QueueConfig) => {
  if (!config?.__clientRateLimitAcquired) {
    return
  }

  config.__clientRateLimitAcquired = false

  if (!shouldThrottleRequest(config as InternalAxiosRequestConfig)) {
    return
  }

  clientQueueInFlight = Math.max(0, clientQueueInFlight - 1)

  pruneClientQueueTimestamps()
  notifyClientQueue()
}

export const scheduleRateLimitWindow = (delayMs: number) => {
  const target = Date.now() + Math.max(delayMs, 0)
  if (rateLimitTimer && target <= rateLimitResetAt) {
    return
  }

  rateLimitResetAt = target

  clearTimeout(rateLimitTimer as ReturnType<typeof setTimeout>)
  rateLimitTimer = null

  rateLimitTimer = setTimeout(
    () => {
      rateLimitTimer = null
      rateLimitResetAt = 0
      rateLimitWaiters.splice(0).forEach((resolve) => resolve())
    },
    getClientQueueResetDelay(target, Date.now())
  )
}

export const getClientQueueResetDelay = (target: number, now: number): number =>
  Math.max(0, target - now)

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
    if (signal) signal.addEventListener("abort", onAbort, { once: true })
    rateLimitWaiters.push(() => {
      if (signal) signal.removeEventListener("abort", onAbort)
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
      clearTimeout(rateLimitTimer as ReturnType<typeof setTimeout>)
      rateLimitTimer = null
      rateLimitResetAt = 0
      rateLimitWaiters.splice(0).forEach((resolve) => resolve?.())
    }
    // If the window is still active, leave it — the server-side limit is still valid.
  })
}
