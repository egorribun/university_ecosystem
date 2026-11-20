import process from "node:process"
import { clearTimeout, setTimeout } from "node:timers"
import { URL } from "node:url"

// Observe only the existing service-worker recipient check. Never print its URL,
// response, recipient, or subscription; the protocol contains fixed classes only.
// The check is scoped to a scenario's time window, not a particular push. A
// missing check does not prove no push arrived. Session-owner comparisons
// do not inspect the push payload or establish the worker's recipient decision.
const scenarios = new Set(["chat", "reply", "news", "events", "schedule", "release"])
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/iu
const MAX_RECORDS = 32
let emitted = 0
const cleanupCases = new Set(["topics", "chat", "reply"])
const emittedCleanup = new Set()

// A cleanup result is scoped to the account authenticated for that request.
// It never establishes the original recipient, provider acceptance, or arrival.
export function reportPushCleanupObservation(
  context,
  removed,
  emit = (line) => process.stdout.write(line)
) {
  try {
    if (
      !context ||
      (context.project !== "desktop" && context.project !== "mobile") ||
      (context.retry !== 0 && context.retry !== 1) ||
      !cleanupCases.has(context.case) ||
      context.bound !== true
    )
      return
    const identity = `${context.project}:${context.retry}:${context.case}`
    if (emittedCleanup.has(identity)) return
    const row = removed === true ? "removed" : removed === false ? "not-found" : "unknown"
    emittedCleanup.add(identity)
    emit(
      `UE_LIVE_PUSH_CLEANUP_V1 project=${context.project} retry=${context.retry} case=${context.case} current-user-row=${row} original-recipient=unknown\n`
    )
  } catch {
    // Diagnostics never alter cleanup or expose their inputs.
  }
}

export async function observePushCleanup(context, cleanup, emit) {
  let removed = null
  try {
    removed = await cleanup()
  } finally {
    reportPushCleanupObservation(context, removed, emit)
  }
}

export function createPushRecipientObservation(
  page,
  origin,
  project,
  retry,
  emit = (line) => process.stdout.write(line)
) {
  let expectedOrigin
  try {
    expectedOrigin = new URL(origin).origin
  } catch {
    expectedOrigin = null
  }
  const context = page.context()
  const tracked = new WeakMap()
  let scope = null

  const finish = (recorded) => {
    const complete = recorded.complete
    recorded.complete = null
    complete?.()
  }

  const onRequest = (request) => {
    try {
      if (!scope || !expectedOrigin || !request.serviceWorker() || request.method() !== "GET")
        return
      const url = new URL(request.url())
      if (url.origin !== expectedOrigin || url.pathname !== "/api/v1/users/me" || url.search) return
      scope.count = Math.min(2, scope.count + 1)
      if (scope.count === 1) {
        scope.check = "pending"
        scope.pending = new Promise((resolve) => {
          scope.complete = resolve
        })
        tracked.set(request, scope)
      } else {
        scope.check = "multiple"
        finish(scope)
      }
    } catch {
      // Diagnostic failures do not affect the test or expose request details.
    }
  }
  const onResponse = (response) => {
    let recorded
    try {
      recorded = tracked.get(response.request())
      if (!recorded || recorded.count !== 1) return
      const status = response.status()
      if (status === 401 || status === 403) {
        recorded.check = "auth"
        finish(recorded)
      } else if (status < 200 || status >= 300) {
        recorded.check = "other"
        finish(recorded)
      } else {
        void Promise.resolve()
          .then(() => response.json())
          .then((profile) => {
            if (recorded.count !== 1 || recorded.check !== "pending") return
            const id = profile && typeof profile === "object" ? profile.id : null
            recorded.check =
              typeof id !== "string" || !uuid.test(id) || !recorded.owner
                ? "invalid"
                : id === recorded.owner
                  ? "session-owner-match"
                  : "session-owner-mismatch"
          })
          .catch(() => {
            if (recorded.count === 1 && recorded.check === "pending") {
              recorded.check = "unreadable"
            }
          })
          .finally(() => finish(recorded))
      }
    } catch {
      if (recorded?.count === 1) finish(recorded)
      // Ignore malformed observation objects without recording their contents.
    }
  }
  const onFailed = (request) => {
    const recorded = tracked.get(request)
    if (recorded?.count === 1 && recorded.check === "pending") {
      recorded.check = "network"
      finish(recorded)
    }
  }
  context.on("request", onRequest)
  context.on("response", onResponse)
  context.on("requestfailed", onFailed)

  return {
    arm(scenario, owner) {
      scope = scenarios.has(scenario)
        ? {
            scenario,
            owner: typeof owner === "string" && uuid.test(owner) ? owner : null,
            count: 0,
            check: "none",
            pending: null,
            complete: null,
            reported: false,
          }
        : null
    },
    async report(expectedEndpoint, timeoutMs = 1200) {
      const current = scope
      if (
        !current ||
        current.reported ||
        emitted >= MAX_RECORDS ||
        (project !== "desktop" && project !== "mobile") ||
        (retry !== 0 && retry !== 1)
      )
        return
      current.reported = true
      let timer
      let subscription = "unavailable"
      try {
        const waitMs = Number.isFinite(timeoutMs)
          ? Math.max(0, Math.min(1200, Math.floor(timeoutMs)))
          : 0
        if (waitMs > 0) {
          let subscriptionTask = Promise.resolve()
          if (typeof expectedEndpoint === "string" && expectedEndpoint.length > 0) {
            subscriptionTask = Promise.resolve()
              .then(() =>
                page.evaluate(async (expected) => {
                  try {
                    const registration = await globalThis.navigator.serviceWorker.getRegistration()
                    if (!registration) return "unavailable"
                    const value = await registration.pushManager.getSubscription()
                    if (!value) return "missing"
                    return value.endpoint === expected ? "same" : "changed"
                  } catch {
                    return "unavailable"
                  }
                }, expectedEndpoint)
              )
              .then((value) => {
                if (["same", "changed", "missing", "unavailable"].includes(value))
                  subscription = value
              })
              .catch(() => {})
          }
          await Promise.race([
            Promise.allSettled([subscriptionTask, current.pending]),
            new Promise((resolve) => {
              timer = setTimeout(resolve, waitMs)
            }),
          ])
        }
        const line = `UE_LIVE_PUSH_RECIPIENT_V1 project=${project} retry=${retry} scenario=${current.scenario} check=${current.check} subscription=${subscription}\n`
        emitted += 1
        emit(line)
      } catch {
        // Observation and its sink must never replace a delivery failure.
      } finally {
        clearTimeout(timer)
      }
    },
    dispose() {
      context.off("request", onRequest)
      context.off("response", onResponse)
      context.off("requestfailed", onFailed)
      scope = null
    },
  }
}
