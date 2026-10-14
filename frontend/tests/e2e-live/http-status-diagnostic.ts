// Bound both projects x twenty-six checks x two attempts (CI retries once).
const emittedRecords = new Set<string>()
const MAX_RECORDS = 104
const emittedRetryRecords = new Set<string>()
const emittedRateLimitRecords = new Set<string>()
// Bound retry decisions across both projects and all E2E retries.
const MAX_RETRY_RECORDS = 32
const MAX_RATE_LIMIT_RECORDS = 32

export type LiveRateLimitRetryCheck =
  | "auth-logout"
  | "password-reset-replay"
  | "email-otp-verification-wrong-code"
  | "email-otp-verification-stale-code"
  | "email-mfa-enabled-login"
export type LiveRateLimitRetryDecision =
  "retry" | "declined-header" | "declined-deadline" | "not-retried"

export type LiveHttpStatusCheck =
  | "admin-users"
  | "admin-feature-flags"
  | "admin-feature-flags-ui"
  | "password-reset-replay"
  | "auth-login"
  | "auth-session-cap"
  | "auth-logout"
  | "auth-session-preflight"
  | "messenger-message-send"
  | "chat-attachment-create"
  | "email-otp-register"
  | "email-otp-verification-start"
  | "email-otp-verification-wrong-code"
  | "email-otp-verification-resend"
  | "email-otp-verification-stale-code"
  | "email-otp-verification-accept"
  | "email-mfa-register"
  | "email-mfa-initial-login"
  | "email-mfa-sibling-login"
  | "email-mfa-verification-start"
  | "email-mfa-verification-accept"
  | "email-mfa-enable-start"
  | "email-mfa-enable-accept"
  | "email-mfa-enabled-login"
  | "email-mfa-login-resend-early"
  | "email-mfa-login-accept"

const LIVE_HTTP_STATUS_CHECKS: ReadonlySet<LiveHttpStatusCheck> = new Set([
  "admin-users",
  "admin-feature-flags",
  "admin-feature-flags-ui",
  "password-reset-replay",
  "auth-login",
  "auth-session-cap",
  "auth-logout",
  "auth-session-preflight",
  "messenger-message-send",
  "chat-attachment-create",
  "email-otp-register",
  "email-otp-verification-start",
  "email-otp-verification-wrong-code",
  "email-otp-verification-resend",
  "email-otp-verification-stale-code",
  "email-otp-verification-accept",
  "email-mfa-register",
  "email-mfa-initial-login",
  "email-mfa-sibling-login",
  "email-mfa-verification-start",
  "email-mfa-verification-accept",
  "email-mfa-enable-start",
  "email-mfa-enable-accept",
  "email-mfa-enabled-login",
  "email-mfa-login-resend-early",
  "email-mfa-login-accept",
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

export type LiveRateLimitHeaderKind = "limit" | "remaining"

const MAX_LIVE_RATE_LIMIT_HEADER = 100_000

export function parseLiveRateLimitHeader(
  value: string | undefined,
  kind: LiveRateLimitHeaderKind
): number | null {
  if (
    typeof value !== "string" ||
    (kind !== "limit" && kind !== "remaining") ||
    !/^(?:0|[1-9][0-9]{0,5})$/u.test(value)
  ) {
    return null
  }
  const parsed = Number(value)
  if (
    !Number.isSafeInteger(parsed) ||
    parsed > MAX_LIVE_RATE_LIMIT_HEADER ||
    (kind === "limit" && parsed === 0)
  ) {
    return null
  }
  return parsed
}

const MAX_DIAGNOSTIC_RETRY_AFTER_SECONDS = 600

export function parseLiveRateLimitRetryAfterForDiagnostic(
  value: string | undefined
): number | null {
  if (typeof value !== "string" || !/^[1-9][0-9]{0,2}$/u.test(value)) return null
  const parsed = Number(value)
  return Number.isSafeInteger(parsed) && parsed <= MAX_DIAGNOSTIC_RETRY_AFTER_SECONDS
    ? parsed
    : null
}

function formatLiveRateLimitHeader(value: unknown, minimum: number): string {
  if (
    typeof value !== "number" ||
    !Number.isSafeInteger(value) ||
    value < minimum ||
    value > MAX_LIVE_RATE_LIMIT_HEADER
  ) {
    return "invalid"
  }
  return String(value)
}

export function reportLiveRateLimitRetry(
  project: string,
  check: LiveRateLimitRetryCheck,
  retryAfterSeconds: number | null,
  decision: LiveRateLimitRetryDecision,
  remainingMs: number,
  xRateLimitLimit?: number | null,
  xRateLimitRemaining?: number | null
): void {
  const validRetryAfter =
    retryAfterSeconds === null ||
    (Number.isSafeInteger(retryAfterSeconds) &&
      retryAfterSeconds >= 1 &&
      retryAfterSeconds <=
        (check === "email-otp-verification-stale-code" ? MAX_DIAGNOSTIC_RETRY_AFTER_SECONDS : 60))
  if (
    (project !== "desktop" && project !== "mobile") ||
    (check !== "auth-logout" &&
      check !== "password-reset-replay" &&
      check !== "email-otp-verification-wrong-code" &&
      check !== "email-otp-verification-stale-code" &&
      check !== "email-mfa-enabled-login") ||
    !validRetryAfter ||
    (decision !== "retry" &&
      decision !== "declined-header" &&
      decision !== "declined-deadline" &&
      decision !== "not-retried") ||
    (decision === "not-retried" && check !== "email-otp-verification-stale-code") ||
    (check === "email-otp-verification-stale-code" && decision !== "not-retried") ||
    (decision === "retry" && retryAfterSeconds === null) ||
    (decision === "retry" && remainingMs === 0) ||
    (decision === "declined-header" && retryAfterSeconds !== null) ||
    (decision === "declined-deadline" && retryAfterSeconds === null) ||
    !Number.isSafeInteger(remainingMs) ||
    remainingMs < 0 ||
    remainingMs > 60_000
  ) {
    return
  }

  let rateLimitRecord: string | null = null
  if (check === "auth-logout") {
    const limitText = formatLiveRateLimitHeader(xRateLimitLimit, 1)
    let remainingText = formatLiveRateLimitHeader(xRateLimitRemaining, 0)
    if (
      limitText !== "invalid" &&
      remainingText !== "invalid" &&
      Number(remainingText) > Number(limitText)
    ) {
      remainingText = "invalid"
    }
    rateLimitRecord =
      "UE_LIVE_RATE_LIMIT_V1 project=" +
      project +
      " check=auth-logout x_ratelimit_limit=" +
      limitText +
      " x_ratelimit_remaining=" +
      remainingText +
      "\n"
  }

  const record =
    `UE_LIVE_RETRY_V1 project=${project} check=${check} ` +
    `retry_after_seconds=${retryAfterSeconds ?? "invalid"} decision=${decision} ` +
    `remaining_ms=${remainingMs}\n`
  const emitRetryRecord =
    !emittedRetryRecords.has(record) && emittedRetryRecords.size < MAX_RETRY_RECORDS
  const emitRateLimitRecord =
    rateLimitRecord !== null &&
    !emittedRateLimitRecords.has(rateLimitRecord) &&
    emittedRateLimitRecords.size < MAX_RATE_LIMIT_RECORDS
  if (!emitRetryRecord && !emitRateLimitRecord) return
  if (emitRetryRecord) emittedRetryRecords.add(record)
  if (rateLimitRecord !== null && emitRateLimitRecord) {
    emittedRateLimitRecords.add(rateLimitRecord)
  }
  try {
    if (emitRetryRecord) process.stdout.write(record)
    if (rateLimitRecord !== null && emitRateLimitRecord) {
      process.stdout.write(rateLimitRecord)
    }
  } catch {
    // Retry diagnostics must not replace the live result.
  }
}
