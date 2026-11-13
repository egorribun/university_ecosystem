import { generateKeyPairSync } from "node:crypto"
import process from "node:process"
import type { Page } from "@playwright/test"

type Permission = "default" | "granted" | "denied" | "unsupported"
type Ready = "resolved" | "timeout" | "error"
type WorkerState =
  "missing" | "installing" | "installed" | "activating" | "activated" | "redundant" | "error"
type Probe =
  | "skipped"
  | "subscribed"
  | "permission-denied"
  | "push-service-unavailable"
  | "push-service-error"
  | "not-allowed"
  | "abort"
  | "invalid-state"
  | "not-supported"
  | "other"
  | "timeout"

interface Observation {
  permission: Permission
  ready: Ready
  state: WorkerState
  controller: boolean
  subscription: boolean
  matches: 0 | 1
  probe: Probe
}

const BROWSER_OBSERVATION_BUDGET_MS = 1_200
const HOST_CAPTURE_DEADLINE_MS = 1_600
const PROBE_BUDGET_MS = 15_000
const MAX_RECORDS = 4
const PROBE_VALUES: readonly Probe[] = [
  "skipped",
  "subscribed",
  "permission-denied",
  "push-service-unavailable",
  "push-service-error",
  "not-allowed",
  "abort",
  "invalid-state",
  "not-supported",
  "other",
  "timeout",
]
const emittedRecords = new Set<string>()

function fallbackObservation(permission: Permission): Observation {
  return {
    permission,
    ready: "timeout",
    state: "error",
    controller: false,
    subscription: false,
    matches: 0,
    probe: "skipped",
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
}

function normalizePermission(value: unknown): Permission | null {
  return value === "default" || value === "granted" || value === "denied" || value === "unsupported"
    ? value
    : null
}

function normalizeProbe(value: unknown): Probe | null {
  return PROBE_VALUES.find((candidate) => candidate === value) ?? null
}

function normalizeObservation(value: unknown): Observation | null {
  if (!isRecord(value)) return null
  try {
    const permission = value.permission
    const ready = value.ready
    const state = value.state
    const controller = value.controller
    const subscription = value.subscription
    const matches = value.matches
    const probe = normalizeProbe(value.probe)
    if (
      (permission !== "default" &&
        permission !== "granted" &&
        permission !== "denied" &&
        permission !== "unsupported") ||
      (ready !== "resolved" && ready !== "timeout" && ready !== "error") ||
      (state !== "missing" &&
        state !== "installing" &&
        state !== "installed" &&
        state !== "activating" &&
        state !== "activated" &&
        state !== "redundant" &&
        state !== "error") ||
      typeof controller !== "boolean" ||
      typeof subscription !== "boolean" ||
      (matches !== 0 && matches !== 1) ||
      probe === null
    ) {
      return null
    }
    return { permission, ready, state, controller, subscription, matches, probe }
  } catch {
    return null
  }
}

/**
 * Builds a fresh, unused P-256 application server key as the 65-byte uncompressed
 * point (0x04 || x || y) in base64url. The key is never logged or returned to callers.
 */
function createProbeApplicationServerKey(): string | null {
  try {
    const { publicKey } = generateKeyPairSync("ec", { namedCurve: "prime256v1" })
    const jwk = publicKey.export({ format: "jwk" })
    const x = Buffer.from(jwk.x ?? "", "base64url")
    const y = Buffer.from(jwk.y ?? "", "base64url")
    if (x.length !== 32 || y.length !== 32) return null
    return Buffer.concat([Buffer.from([0x04]), x, y]).toString("base64url")
  } catch {
    // A failed key build only skips the probe; the observation is still reported.
    return null
  }
}

async function observe(
  page: Page,
  expectedNotificationId: string,
  probeSubscribe: boolean
): Promise<Observation | null> {
  let timer: ReturnType<typeof setTimeout> | undefined
  let permission: Permission | null = null
  const evaluation = Promise.resolve()
    .then(async () => {
      const capturedPermission = normalizePermission(
        await page.evaluate(() => {
          try {
            if (typeof Notification === "undefined") return "unsupported"
            const currentPermission = Notification.permission
            return currentPermission === "default" ||
              currentPermission === "granted" ||
              currentPermission === "denied"
              ? currentPermission
              : null
          } catch {
            return null
          }
        })
      )
      // API absence alone means unsupported; an unreadable permission is inconclusive.
      if (capturedPermission === null) return null
      permission = capturedPermission
      // The page decides whether the probe applies; the host only supplies a fresh key.
      const probeKey =
        probeSubscribe && capturedPermission === "granted"
          ? createProbeApplicationServerKey()
          : null
      return page.evaluate(
        async ({
          expectedTag,
          budgetMs,
          permission,
          probeKey,
          probeBudgetMs,
        }: {
          expectedTag: string
          budgetMs: number
          permission: Permission
          probeKey: string | null
          probeBudgetMs: number
        }): Promise<Observation> => {
          type Wait<T> = { kind: "resolved"; value: T } | { kind: "timeout" } | { kind: "error" }
          const deadline = Date.now() + budgetMs
          const withinBudget = <T>(operation: Promise<T>): Promise<Wait<T>> => {
            const remaining = deadline - Date.now()
            if (remaining <= 0) return Promise.resolve({ kind: "timeout" })
            return new Promise((resolve) => {
              const timeout = window.setTimeout(() => resolve({ kind: "timeout" }), remaining)
              Promise.resolve(operation).then(
                (value) => {
                  window.clearTimeout(timeout)
                  resolve({ kind: "resolved", value })
                },
                () => {
                  window.clearTimeout(timeout)
                  resolve({ kind: "error" })
                }
              )
            })
          }
          const decodeBase64Url = (value: string) => {
            const base64 = value.replace(/-/gu, "+").replace(/_/gu, "/")
            const binary = atob(base64.padEnd(Math.ceil(base64.length / 4) * 4, "="))
            const bytes = new Uint8Array(new ArrayBuffer(binary.length))
            for (let index = 0; index < binary.length; index += 1) {
              bytes[index] = binary.charCodeAt(index)
            }
            return bytes
          }
          // Classifies the rejection from its name and message only; the text is never returned.
          const classifySubscribeError = (error: unknown): Probe => {
            let name = ""
            let message = ""
            try {
              if (typeof error === "object" && error !== null) {
                name = String((error as { name?: unknown }).name ?? "")
                message = String((error as { message?: unknown }).message ?? "").toLowerCase()
              }
            } catch {
              name = ""
              message = ""
            }
            if (message.includes("permission denied")) return "permission-denied"
            if (message.includes("push service not available")) return "push-service-unavailable"
            if (message.includes("push service error")) return "push-service-error"
            switch (name) {
              case "NotAllowedError":
                return "not-allowed"
              case "AbortError":
                return "abort"
              case "InvalidStateError":
                return "invalid-state"
              case "NotSupportedError":
                return "not-supported"
              default:
                return "other"
            }
          }
          // Runs one subscribe attempt on its own budget. A late success is still unsubscribed.
          const runSubscribeProbe = (
            registration: ServiceWorkerRegistration,
            key: string,
            budget: number
          ): Promise<Probe> =>
            new Promise<Probe>((resolve) => {
              const budgetTimer = window.setTimeout(() => resolve("timeout"), budget)
              Promise.resolve()
                .then(() =>
                  registration.pushManager.subscribe({
                    userVisibleOnly: true,
                    applicationServerKey: decodeBase64Url(key),
                  })
                )
                .then(
                  async (subscription) => {
                    try {
                      await subscription.unsubscribe()
                    } catch {
                      // Best-effort cleanup of the probe subscription only.
                    }
                    window.clearTimeout(budgetTimer)
                    resolve("subscribed")
                  },
                  (error: unknown) => {
                    window.clearTimeout(budgetTimer)
                    resolve(classifySubscribeError(error))
                  }
                )
            })

          if (!("serviceWorker" in navigator)) {
            return {
              permission,
              ready: "error",
              state: "missing",
              controller: false,
              subscription: false,
              matches: 0,
              probe: "skipped",
            }
          }

          let controller: boolean
          try {
            controller = navigator.serviceWorker.controller !== null
          } catch {
            controller = false
          }

          let readyResult: Wait<ServiceWorkerRegistration>
          let registrationResult: Wait<ServiceWorkerRegistration | undefined>
          try {
            ;[readyResult, registrationResult] = await Promise.all([
              withinBudget(Promise.resolve(navigator.serviceWorker.ready)),
              withinBudget(Promise.resolve(navigator.serviceWorker.getRegistration())),
            ])
          } catch {
            readyResult = { kind: "error" }
            registrationResult = { kind: "error" }
          }

          const ready: Ready =
            readyResult.kind === "resolved"
              ? "resolved"
              : readyResult.kind === "timeout"
                ? "timeout"
                : "error"
          const registration =
            readyResult.kind === "resolved"
              ? readyResult.value
              : registrationResult.kind === "resolved"
                ? registrationResult.value
                : undefined
          const worker =
            registration?.active ?? registration?.installing ?? registration?.waiting ?? null
          let state: WorkerState = registration ? "error" : "missing"
          if (worker) {
            switch (worker.state) {
              case "installing":
              case "installed":
              case "activating":
              case "activated":
              case "redundant":
                state = worker.state
                break
              default:
                state = "error"
            }
          }

          let subscription = false
          let subscriptionAbsent = false
          let matches: 0 | 1 = 0
          if (registration) {
            const [subscriptionResult, notificationsResult] = await Promise.all([
              withinBudget(
                Promise.resolve().then(() => registration.pushManager.getSubscription())
              ),
              withinBudget(Promise.resolve().then(() => registration.getNotifications())),
            ])
            if (subscriptionResult.kind === "resolved") {
              subscription = subscriptionResult.value !== null
              subscriptionAbsent = subscriptionResult.value === null
            }
            if (notificationsResult.kind === "resolved") {
              try {
                matches = notificationsResult.value.some(
                  (notification) => notification.tag === expectedTag
                )
                  ? 1
                  : 0
              } catch {
                matches = 0
              }
            }
          }

          let probe: Probe = "skipped"
          if (registration && subscriptionAbsent && probeKey !== null && permission === "granted") {
            probe = await runSubscribeProbe(registration, probeKey, probeBudgetMs)
          }

          return { permission, ready, state, controller, subscription, matches, probe }
        },
        {
          expectedTag: expectedNotificationId,
          budgetMs: BROWSER_OBSERVATION_BUDGET_MS,
          permission: capturedPermission,
          probeKey,
          probeBudgetMs: PROBE_BUDGET_MS,
        }
      )
    })
    .catch(() => (permission === null ? null : fallbackObservation(permission)))
  const deadline = new Promise<Observation | null>((resolve) => {
    timer = setTimeout(
      () => resolve(permission === null ? null : fallbackObservation(permission)),
      HOST_CAPTURE_DEADLINE_MS + (probeSubscribe ? PROBE_BUDGET_MS : 0)
    )
  })
  try {
    return await Promise.race([evaluation, deadline])
  } finally {
    if (timer !== undefined) clearTimeout(timer)
  }
}

export async function reportLivePushDeliveryObservation(
  page: Page,
  project: unknown,
  expectedNotificationId: unknown,
  options?: { probeSubscribe?: boolean }
): Promise<void> {
  try {
    if (
      (project !== "desktop" && project !== "mobile") ||
      typeof expectedNotificationId !== "string" ||
      expectedNotificationId.length === 0 ||
      expectedNotificationId.length > 512
    ) {
      return
    }
    const probeSubscribe = options?.probeSubscribe === true
    const observed = normalizeObservation(
      await observe(page, expectedNotificationId, probeSubscribe)
    )
    if (!observed) return
    const record =
      "UE_LIVE_PUSH_OBS_V1 project=" +
      project +
      " permission=" +
      observed.permission +
      " ready=" +
      observed.ready +
      " state=" +
      observed.state +
      " controller=" +
      (observed.controller ? "1" : "0") +
      " subscription=" +
      (observed.subscription ? "1" : "0") +
      " matches=" +
      observed.matches +
      " probe=" +
      observed.probe +
      "\n"
    if (emittedRecords.has(record) || emittedRecords.size >= MAX_RECORDS) return
    emittedRecords.add(record)
    try {
      process.stdout.write(record)
    } catch {
      // Diagnostics must not replace the original delivery failure.
    }
  } catch {
    // Observation failures never replace the original delivery failure.
  }
}

/**
 * Awaits the subscription save that follows an explicit push opt-in. If it does
 * not arrive, emits the bounded push observation for the subscribe phase before
 * rethrowing the original failure, so a hosted run shows whether the browser
 * held a permission, an active worker and a native subscription at that point.
 * This is the only caller that also runs the subscribe probe: it attempts
 * `pushManager.subscribe` once with a fresh key and records only the closed
 * `probe` outcome, then unsubscribes any successful probe subscription.
 */
export async function awaitPushSubscribeWithObservation<T>(
  subscribeResponse: Promise<T>,
  page: Page,
  project: unknown
): Promise<T> {
  try {
    return await subscribeResponse
  } catch (error) {
    await reportLivePushDeliveryObservation(page, project, "subscribe-phase", {
      probeSubscribe: true,
    })
    throw error
  }
}
