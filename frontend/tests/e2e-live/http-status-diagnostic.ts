// Keep the existing hard output bound as the closed check set grows.
const emittedRecords = new Set<string>()
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
  | "student-users-denied"
  | "teacher-users-denied"
  | "student-feature-flags-denied"
  | "teacher-feature-flags-denied"
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

const LIVE_HTTP_STATUS_PROJECTS = 2 // desktop and mobile
// A check reports at most one status per attempt, so two attempts bound its records.
const LIVE_HTTP_STATUS_ATTEMPTS = 2
const LIVE_HTTP_STATUS_CHECKS: ReadonlySet<LiveHttpStatusCheck> = new Set([
  "student-users-denied",
  "teacher-users-denied",
  "student-feature-flags-denied",
  "teacher-feature-flags-denied",
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
// Derived from the closed check set: projects x checks x attempts (2 x 30 x 2 = 120).
const MAX_RECORDS =
  LIVE_HTTP_STATUS_PROJECTS * LIVE_HTTP_STATUS_CHECKS.size * LIVE_HTTP_STATUS_ATTEMPTS

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

export type LiveLoginFailureStage = "submit" | "navigation"
export type LiveLoginObservationCount = "0" | "1" | "many"
export type LiveLoginFailureRoute = "login" | "dashboard" | "register" | "other" | "unavailable"

const emittedLoginFailureRecords = new Set<string>()
const MAX_LOGIN_FAILURE_RECORDS = 16

export function reportLiveLoginFailure(
  project: string,
  stage: LiveLoginFailureStage,
  requests: LiveLoginObservationCount,
  responses: LiveLoginObservationCount,
  status: number | null,
  route: LiveLoginFailureRoute
): void {
  if (
    (project !== "desktop" && project !== "mobile") ||
    (stage !== "submit" && stage !== "navigation") ||
    (requests !== "0" && requests !== "1" && requests !== "many") ||
    (responses !== "0" && responses !== "1" && responses !== "many") ||
    (status !== null && (!Number.isInteger(status) || status < 100 || status > 599)) ||
    (route !== "login" &&
      route !== "dashboard" &&
      route !== "register" &&
      route !== "other" &&
      route !== "unavailable")
  ) {
    return
  }

  const record =
    `UE_LIVE_LOGIN_FAILURE_V1 project=${project} stage=${stage} ` +
    `requests=${requests} responses=${responses} status=${status ?? "none"} route=${route}\n`
  if (
    emittedLoginFailureRecords.has(record) ||
    emittedLoginFailureRecords.size >= MAX_LOGIN_FAILURE_RECORDS
  ) {
    return
  }
  emittedLoginFailureRecords.add(record)
  try {
    process.stdout.write(record)
  } catch {
    // A closed diagnostic stream must never replace the original login failure.
  }
}

// Stage A: finite declaration coverage; template-expanded cases are not attributed.
const LIVE_OPERATION_DECLARATIONS: Readonly<Record<string, readonly number[]>> = {
  "activity-dashboard.live.spec.ts": [22],
  "activity-summary.live.spec.ts": [148],
  "admin-audit-rbac.live.spec.ts": [3],
  "admin-feature-flags-rbac.live.spec.ts": [3],
  "admin-notifications-rbac.live.spec.ts": [27],
  "admin-stories-smoke.live.spec.ts": [8],
  "admin-users-rbac.live.spec.ts": [55],
  "aud178-reset-referer-csp.live.spec.ts": [124],
  "auth-login-lockout.live.spec.ts": [40],
  "auth-roles.live.spec.ts": [33, 210, 228],
  "avatar-persistence.live.spec.ts": [173],
  "chat-attachment-isolation.live.spec.ts": [229],
  "core-a11y-live.live.spec.ts": [37],
  "email-otp-mfa-login.live.spec.ts": [378],
  "email-otp-verification.live.spec.ts": [102],
  "events-tab-keyboard.live.spec.ts": [3],
  "footer-bottom-navigation.live.spec.ts": [98, 282],
  "map-gesture-isolation.live.spec.ts": [178, 209, 248],
  "map-zoom-longtask.live.spec.ts": [102],
  "messenger-a11y.live.spec.ts": [5],
  "messenger-focus-trap.live.spec.ts": [3],
  "messenger-group-isolation.live.spec.ts": [254],
  "messenger-keyboard-focus.live.spec.ts": [58, 140],
  "messenger-membership-revocation.live.spec.ts": [317],
  "messenger-realtime.live.spec.ts": [260, 417, 864, 1105, 1342, 1669, 2033],
  "messenger-reconnect-ordering.live.spec.ts": [332],
  "messenger-reconnect.live.spec.ts": [261],
  "messenger-unread-read.live.spec.ts": [322],
  "navbar-layout-stability.live.spec.ts": [267, 375, 438, 476],
  "new-chat-hit-targets.live.spec.ts": [3],
  "news-responsive-matrix.live.spec.ts": [336],
  "news-scroll-restoration.live.spec.ts": [304],
  "not-found-i18n.live.spec.ts": [11, 65],
  "notification-in-app.live.spec.ts": [293],
  "notification-preferences.live.spec.ts": [217],
  "notification-topics-delivery.live.spec.ts": [1079],
  "password-reset.live.spec.ts": [129],
  "profile-csrf.live.spec.ts": [99],
  "profile-persistence.live.spec.ts": [102, 302],
  "push-delivery.live.spec.ts": [492, 590, 892],
  "push-permission-default.live.spec.ts": [17],
  "push-permission-denied.live.spec.ts": [44],
  "push-subscription.live.spec.ts": [115],
  "pwa-offline-shell.live.spec.ts": [239, 323],
  "register-double-submit.live.spec.ts": [42],
  "schedule-200-equivalent-reflow.live.spec.ts": [5],
  "schedule-grid-keyboard.live.spec.ts": [5],
  "schedule-hydration-i18n.live.spec.ts": [87, 91],
  "search-dialog-keyboard.live.spec.ts": [9, 62, 212, 219, 226],
  "settings-password-change-rollback.live.spec.ts": [141],
  "settings-radio-focus.live.spec.ts": [20, 371, 444],
  "settings-tabs-keyboard.live.spec.ts": [5],
  "settings-theme-roundtrip.live.spec.ts": [75],
  "ssr-hydration-i18n.live.spec.ts": [442, 454, 468],
  "story-viewer-keyboard.live.spec.ts": [7],
  "story-viewer-reduced-motion.live.spec.ts": [15],
  "totp-recovery.live.spec.ts": [325],
  "zzz-aud174-prehydration-caddy-log.live.spec.ts": [8],
}

export type LiveOperationPhase = "setup" | "body" | "cleanup"
export type LiveMfaOperationKind =
  | "email-mfa-verification-start"
  | "email-mfa-verification-accept"
  | "email-mfa-enable-start"
  | "email-mfa-enable-accept"
  | "email-mfa-enabled-login"
  | "email-mfa-login-accept"
type LiveOperationKind = "auth-login" | "chat-attachment-create" | LiveMfaOperationKind
export type LiveMfaLimiterSignature = "domain-signature" | "other" | "unavailable"
export type LiveMfaRateLimitObservation = {
  retryAfterSeconds: number | null
  limiterSignature: LiveMfaLimiterSignature
}
type LiveOperationIdentity = {
  project: string
  source: string
  line: number
  retry: number
}
export type LiveOperation = {
  finish: (
    status: number | null,
    requests: number,
    responses: number,
    elapsedMs: number,
    rateLimit?: LiveMfaRateLimitObservation
  ) => void
}
export type LiveOperationScope = {
  begin: (operation: LiveOperationKind, phase: LiveOperationPhase) => LiveOperation
}

// These are worker bounds, NOT a run-wide emission guarantee. Python retains globally.
let liveOperationEmissions = 0
const liveOperationMarkers = new Set<string>()
const MAX_OPERATION_WORKER_ROWS = 104
const MAX_OPERATION_ATTEMPT_ROWS = 16
const LIVE_MFA_OPERATIONS: ReadonlySet<string> = new Set([
  "email-mfa-verification-start",
  "email-mfa-verification-accept",
  "email-mfa-enable-start",
  "email-mfa-enable-accept",
  "email-mfa-enabled-login",
  "email-mfa-login-accept",
])
const inertLiveOperation: LiveOperation = Object.freeze({
  finish: () => undefined,
})

export function createLiveOperationScope(
  identity: LiveOperationIdentity,
  emit: (line: string) => unknown = (line) => process.stdout.write(line)
): LiveOperationScope {
  // Copy closed scalar identity once. No asynchronous callback reads an active scope.
  let ordinal = 0
  const safeEmit = (record: string) => {
    try {
      emit(record)
    } catch {
      // A failed diagnostic sink cannot replace an assertion or cleanup failure.
    }
  }
  const marker = (value: "invalid-scope" | "truncated" | "unavailable") => {
    if (liveOperationMarkers.has(value)) return
    liveOperationMarkers.add(value)
    safeEmit(`UE_LIVE_HTTP_OPERATION_V2 completeness=${value}\n`)
  }
  let project = ""
  let source = ""
  let line = 0
  let retry = -1
  try {
    ;({ project, source, line, retry } = identity)
  } catch {
    marker("invalid-scope")
    return Object.freeze({ begin: () => inertLiveOperation })
  }
  const valid =
    (project === "desktop" || project === "mobile") &&
    typeof source === "string" &&
    Object.hasOwn(LIVE_OPERATION_DECLARATIONS, source) &&
    Number.isSafeInteger(line) &&
    LIVE_OPERATION_DECLARATIONS[source]?.includes(line) &&
    (retry === 0 || retry === 1)
  if (!valid) marker("invalid-scope")
  return Object.freeze({
    begin(operation: LiveOperationKind, phase: LiveOperationPhase): LiveOperation {
      if (!valid) return inertLiveOperation
      const isMfa = LIVE_MFA_OPERATIONS.has(operation)
      if (
        (operation !== "auth-login" && operation !== "chat-attachment-create" && !isMfa) ||
        (phase !== "setup" && phase !== "body" && phase !== "cleanup") ||
        (operation === "auth-login" && phase === "body") ||
        (operation === "chat-attachment-create" &&
          (source !== "chat-attachment-isolation.live.spec.ts" || phase !== "body")) ||
        (isMfa &&
          (source !== "email-otp-mfa-login.live.spec.ts" || line !== 378 || phase !== "body"))
      ) {
        marker("invalid-scope")
        return inertLiveOperation
      }
      ordinal += 1
      if (ordinal > MAX_OPERATION_ATTEMPT_ROWS) {
        ordinal = MAX_OPERATION_ATTEMPT_ROWS + 1
        marker("truncated")
        return inertLiveOperation
      }
      const operationOrdinal = ordinal
      let finished = false
      return Object.freeze({
        finish(
          status: number | null,
          requests: number,
          responses: number,
          elapsedMs: number,
          rateLimit?: LiveMfaRateLimitObservation
        ) {
          if (finished) return
          finished = true
          if (
            (status !== null && (!Number.isInteger(status) || status < 100 || status > 599)) ||
            !Number.isSafeInteger(requests) ||
            requests < 0 ||
            !Number.isSafeInteger(responses) ||
            responses < 0 ||
            !Number.isFinite(elapsedMs) ||
            elapsedMs < 0 ||
            (status === null ? responses !== 0 : responses === 0)
          ) {
            marker("unavailable")
            return
          }
          let retryAfter = "none"
          let limiterSignature = "not-applicable"
          if (isMfa && status === 429) {
            try {
              const seconds = rateLimit?.retryAfterSeconds ?? null
              const signature = rateLimit?.limiterSignature ?? "unavailable"
              if (
                (seconds !== null &&
                  (!Number.isSafeInteger(seconds) || seconds < 1 || seconds > 600)) ||
                (signature !== "domain-signature" &&
                  signature !== "other" &&
                  signature !== "unavailable") ||
                (signature === "domain-signature" && operation === "email-mfa-enabled-login")
              ) {
                marker("unavailable")
                return
              }
              retryAfter = seconds === null ? "invalid" : String(seconds)
              limiterSignature = signature
            } catch {
              marker("unavailable")
              return
            }
          } else if (rateLimit !== undefined) {
            marker("unavailable")
            return
          }
          if (liveOperationEmissions >= MAX_OPERATION_WORKER_ROWS) {
            marker("truncated")
            return
          }
          const count = (value: number) => (value > 1 ? "many" : String(value))
          const record =
            `UE_LIVE_HTTP_OPERATION_${isMfa ? "V3" : "V2"} project=${project} source=${source} line=${line} ` +
            `retry=${retry} ordinal=${operationOrdinal} phase=${phase} operation=${operation} ` +
            `outcome=${status === null ? "no-response" : "response"} status=${status ?? "none"} ` +
            `elapsed_ms=${Math.min(120000, Math.floor(elapsedMs))} saturated=${elapsedMs > 120000 ? 1 : 0} ` +
            `requests=${count(requests)} responses=${count(responses)}` +
            (isMfa
              ? ` retry_after_seconds=${retryAfter} limiter_signature=${limiterSignature}\n`
              : "\n")
          if (record.length > 512 || !/^[\x20-\x7e]+\n$/u.test(record)) {
            marker("unavailable")
            return
          }
          liveOperationEmissions += 1
          safeEmit(record)
        },
      })
    },
  })
}
