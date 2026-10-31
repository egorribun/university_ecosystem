/** Replay attempts allowed for retryable failures before a record is dead-lettered. */
export const REPLAY_MAX_ATTEMPTS = 5
/** Full-jitter backoff: the ceiling doubles per attempt from the base up to the cap. */
const REPLAY_BASE_DELAY_MS = 1_000
const REPLAY_MAX_DELAY_MS = 300_000
/** Bounds one replay request so a hung connection cannot hold the replay lock forever. */
export const REPLAY_REQUEST_TIMEOUT_MS = 15_000
/** Records bound to another browser session are never sent and expire after this age. */
export const OTHER_SESSION_RECORD_TTL_MS = 7 * 24 * 60 * 60 * 1000

/** Timeouts, throttling and server faults may succeed later; every other status is final. */
export function isRetryableReplayStatus(status: number): boolean {
  return status === 408 || status === 425 || status === 429 || status >= 500
}

/** Full jitter: a uniformly random delay below the capped exponential ceiling. */
export function replayBackoffMs(attempt: number): number {
  const ceiling = Math.min(REPLAY_MAX_DELAY_MS, REPLAY_BASE_DELAY_MS * 2 ** (attempt - 1))
  return Math.floor(Math.random() * ceiling)
}

export function isExpiredOtherSessionRecord(timestamp: number, now: number): boolean {
  return now - timestamp >= OTHER_SESSION_RECORD_TTL_MS
}
