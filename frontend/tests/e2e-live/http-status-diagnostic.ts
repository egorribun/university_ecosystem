// Bound both projects × eight checks × two attempts (CI retries once).
const emittedRecords = new Set<string>()
const MAX_RECORDS = 32
const emittedRetryRecords = new Set<string>()
// Bound retry decisions across both projects and all E2E retries.
const MAX_RETRY_RECORDS = 32

export type LiveRateLimitRetryCheck = "auth-logout" | "password-reset-replay"
export type LiveRateLimitRetryDecision = "retry" | "declined-header" | "declined-deadline"

export type LiveHttpStatusCheck =
  | "admin-users"
  | "admin-feature-flags"
  | "admin-feature-flags-ui"
  | "password-reset-replay"
  | "auth-login"
  | "auth-session-cap"
  | "auth-logout"
  | "auth-session-preflight"

const LIVE_HTTP_STATUS_CHECKS: ReadonlySet<LiveHttpStatusCheck> = new Set([
  "admin-users",
  "admin-feature-flags",
  "admin-feature-flags-ui",
  "password-reset-replay",
  "auth-login",
  "auth-session-cap",
  "auth-logout",
  "auth-session-preflight",
])

export function reportLiveHttpStatus(
  project: string,
  check: LiveHttpStatusCheck,
  status: number
): void {
  if (
    (project !== "desktop" && project !== "mobile") ||
    !LIVE_HTTP_STATUS_CHECKS.has(check) ||
    !Number.isInteger(status) ||
    status < 100 ||
    status > 599 ||
    (check === "auth-session-cap" && status !== 403) ||
    emittedRecords.size >= MAX_RECORDS
  ) {
    return
  }

  const record = `UE_LIVE_HTTP_STATUS_V1 project=${project} check=${check} status=${status}\n`
  if (emittedRecords.has(record)) return
  emittedRecords.add(record)
  try {
    process.stdout.write(record)
  } catch {
    // Diagnostics must not replace the scenario's hard assertion.
  }
}

export function reportLiveRateLimitRetry(
  project: string,
  check: LiveRateLimitRetryCheck,
  retryAfterSeconds: number | null,
  decision: LiveRateLimitRetryDecision,
  remainingMs: number
): void {
  const validRetryAfter =
    retryAfterSeconds === null ||
    (Number.isSafeInteger(retryAfterSeconds) && retryAfterSeconds >= 1 && retryAfterSeconds <= 60)
  if (
    (project !== "desktop" && project !== "mobile") ||
    (check !== "auth-logout" && check !== "password-reset-replay") ||
    !validRetryAfter ||
    (decision !== "retry" && decision !== "declined-header" && decision !== "declined-deadline") ||
    (decision === "retry" && retryAfterSeconds === null) ||
    (decision === "retry" && remainingMs === 0) ||
    (decision === "declined-header" && retryAfterSeconds !== null) ||
    (decision === "declined-deadline" && retryAfterSeconds === null) ||
    !Number.isSafeInteger(remainingMs) ||
    remainingMs < 0 ||
    remainingMs > 60_000 ||
    emittedRetryRecords.size >= MAX_RETRY_RECORDS
  ) {
    return
  }

  const record =
    `UE_LIVE_RETRY_V1 project=${project} check=${check} ` +
    `retry_after_seconds=${retryAfterSeconds ?? "invalid"} decision=${decision} ` +
    `remaining_ms=${remainingMs}\n`
  if (emittedRetryRecords.has(record)) return
  emittedRetryRecords.add(record)
  try {
    process.stdout.write(record)
  } catch {
    // Retry diagnostics must not replace the live result.
  }
}
