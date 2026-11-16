import type { Response } from "@playwright/test"
import type {
  LiveMfaLimiterSignature,
  LiveMfaOperationKind,
  LiveOperation,
} from "./http-status-diagnostic"

const OBSERVATION_TIMEOUT_MS = 500

/** Observe an existing response without awaiting diagnostics on the test path. */
export function observeEmailMfaOperation(
  operation: LiveOperation | undefined,
  observed: Pick<Response, "status" | "headers" | "json">,
  elapsedMs: number,
  kind: LiveMfaOperationKind,
  parseRetryAfter: (value: string | undefined) => number | null
): void {
  if (!operation) return

  let status: number
  try {
    status = observed.status()
  } catch {
    return
  }
  if (status !== 429) {
    try {
      operation.finish(status, 0, 1, elapsedMs)
    } catch {
      // Diagnostics must not change the test result.
    }
    return
  }

  let retryAfterSeconds: number | null = null
  try {
    retryAfterSeconds = parseRetryAfter(observed.headers()["retry-after"])
  } catch {
    // An inaccessible or malformed header remains unavailable.
  }
  const expectedDetail =
    kind === "email-mfa-verification-start" || kind === "email-mfa-enable-start"
      ? "MFA request rejected"
      : kind === "email-mfa-enabled-login"
        ? null
        : "MFA verification failed"

  let completed = false
  let timer: ReturnType<typeof setTimeout> | undefined
  const finish = (limiterSignature: LiveMfaLimiterSignature) => {
    if (completed) return
    completed = true
    if (timer !== undefined) clearTimeout(timer)
    try {
      operation.finish(status, 0, 1, elapsedMs, { retryAfterSeconds, limiterSignature })
    } catch {
      // A failing diagnostic sink cannot change the test result.
    }
  }

  if (expectedDetail === null) {
    finish("unavailable")
    return
  }
  try {
    timer = setTimeout(() => finish("unavailable"), OBSERVATION_TIMEOUT_MS)
    timer.unref()
    void observed.json().then(
      (value: unknown) => {
        try {
          if (typeof value !== "object" || value === null) {
            finish("unavailable")
            return
          }
          const detail: unknown = Reflect.get(value, "detail")
          finish(
            typeof detail !== "string"
              ? "unavailable"
              : detail === expectedDetail
                ? "domain-signature"
                : "other"
          )
        } catch {
          finish("unavailable")
        }
      },
      () => finish("unavailable")
    )
  } catch {
    finish("unavailable")
  }
}
