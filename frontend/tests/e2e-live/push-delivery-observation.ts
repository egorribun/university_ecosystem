import type { Page } from "@playwright/test"

type Permission = "default" | "granted" | "denied" | "unsupported"
type Ready = "resolved" | "timeout" | "error"
type WorkerState =
  "missing" | "installing" | "installed" | "activating" | "activated" | "redundant" | "error"

interface Observation {
  permission: Permission
  ready: Ready
  state: WorkerState
  controller: boolean
  subscription: boolean
  matches: 0 | 1
}

const BROWSER_OBSERVATION_BUDGET_MS = 1_200
const HOST_CAPTURE_DEADLINE_MS = 1_600
const MAX_RECORDS = 4
const emittedRecords = new Set<string>()
const FALLBACK: Observation = {
  permission: "unsupported",
  ready: "timeout",
  state: "error",
  controller: false,
  subscription: false,
  matches: 0,
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
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
      (matches !== 0 && matches !== 1)
    ) {
      return null
    }
    return { permission, ready, state, controller, subscription, matches }
  } catch {
    return null
  }
}

async function observe(page: Page, expectedNotificationId: string): Promise<Observation> {
  let timer: ReturnType<typeof setTimeout> | undefined
  const evaluation = Promise.resolve()
    .then(() =>
      page.evaluate(
        async ({
          expectedTag,
          budgetMs,
        }: {
          expectedTag: string
          budgetMs: number
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

          let permission: Permission = "unsupported"
          try {
            if (typeof Notification !== "undefined") {
              switch (Notification.permission) {
                case "default":
                case "granted":
                case "denied":
                  permission = Notification.permission
                  break
              }
            }
          } catch {
            permission = "unsupported"
          }

          if (!("serviceWorker" in navigator)) {
            return {
              permission,
              ready: "error",
              state: "missing",
              controller: false,
              subscription: false,
              matches: 0,
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

          return { permission, ready, state, controller, subscription, matches }
        },
        { expectedTag: expectedNotificationId, budgetMs: BROWSER_OBSERVATION_BUDGET_MS }
      )
    )
    .catch(() => FALLBACK)
  const deadline = new Promise<Observation>((resolve) => {
    timer = setTimeout(() => resolve(FALLBACK), HOST_CAPTURE_DEADLINE_MS)
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
  expectedNotificationId: unknown
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
    const observed = normalizeObservation(await observe(page, expectedNotificationId))
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
