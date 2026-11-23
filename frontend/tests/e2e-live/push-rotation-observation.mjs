import process from "node:process"
import { clearTimeout, setTimeout } from "node:timers"

// Prefixes are correlation hints, not proof of delivery, timing, or identity.
// Never return a browser endpoint, key, request, or error to the runner.
const scenarios = new Set(["news", "events", "schedule", "release"])
const MAX_RECORDS = 8
const MAX_WAIT_MS = 1_200

export function createPushRotationObservation(
  page,
  project,
  retry,
  emit = (line) => process.stdout.write(line),
  scope = "topics"
) {
  const validScope =
    (project === "desktop" || project === "mobile") &&
    (retry === 0 || retry === 1) &&
    (scope === "topics" || scope === "chat" || (scope === "reply" && project === "mobile"))
  const snapshots = []
  let scenario = scope === "topics" ? "unknown" : scope
  let reported = false
  let reportTask

  const capture = async (phase, timeoutMs) => {
    if (!validScope || reported || snapshots.length >= MAX_RECORDS) return
    let timer
    let fingerprint = "unavailable"
    try {
      const budget = Number.isFinite(timeoutMs)
        ? Math.max(0, Math.min(MAX_WAIT_MS, Math.floor(timeoutMs)))
        : 0
      if (budget > 0) {
        const evaluation = Promise.resolve()
          .then(() =>
            page.evaluate(async () => {
              try {
                const registration = await globalThis.navigator.serviceWorker.getRegistration()
                if (!registration) return "unavailable"
                const subscription = await registration.pushManager.getSubscription()
                if (!subscription) return "missing"
                const data = new globalThis.TextEncoder().encode(subscription.endpoint)
                const digest = await globalThis.crypto.subtle.digest("SHA-256", data)
                return Array.from(new Uint8Array(digest).slice(0, 6), (byte) =>
                  byte.toString(16).padStart(2, "0")
                ).join("")
              } catch {
                return "unavailable"
              }
            })
          )
          .catch(() => "unavailable")
        const result = await Promise.race([
          evaluation,
          new Promise((resolve) => {
            timer = setTimeout(() => resolve("unavailable"), budget)
          }),
        ])
        if (
          typeof result === "string" &&
          (/^[0-9a-f]{12}$/u.test(result) || result === "missing")
        ) {
          fingerprint = result
        }
      }
    } catch {
      // A diagnostic failure must not replace the original acceptance result.
    } finally {
      clearTimeout(timer)
    }
    snapshots.push({
      phase,
      scenario: phase === "opt-in" && scope === "topics" ? "setup" : scenario,
      fingerprint,
    })
  }

  return {
    arm(value) {
      if (scope !== "topics" && value !== scope) return
      if (scope !== "topics") {
        scenario = scope
        return
      }
      scenario = scenarios.has(value) ? value : "unknown"
    },
    async optIn(timeoutMs) {
      await capture("opt-in", timeoutMs)
    },
    async beforeWait(value, timeoutMs) {
      if (scope !== "topics" && value !== scope) return
      if (scope !== "topics") {
        scenario = scope
        await capture("before-wait", timeoutMs)
        return
      }
      scenario = scenarios.has(value) ? value : "unknown"
      await capture("before-wait", timeoutMs)
    },
    async reportFailure(timeoutMs) {
      if (reportTask) return reportTask
      if (reported || !validScope) return
      reportTask = (async () => {
        // Reserve the final slot for the failure snapshot.
        if (snapshots.length >= MAX_RECORDS) snapshots.length = MAX_RECORDS - 1
        await capture("failure", timeoutMs)
        reported = true
        for (const [index, row] of snapshots.entries()) {
          try {
            emit(
              `UE_LIVE_PUSH_ROTATION_V1 project=${project} retry=${retry} scenario=${row.scenario} phase=${row.phase} ordinal=${index + 1} endpoint_sha256=${row.fingerprint}\n`
            )
          } catch {
            // Sink failures cannot change acceptance or cleanup.
          }
        }
      })()
      await reportTask
    },
  }
}
