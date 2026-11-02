import type { Frame, Page, Request, Response } from "@playwright/test"

type Phase = "navigate" | "fill" | "click" | "success"
type Count = "0" | "1" | "many"
type Status =
  | "none"
  | "2xx"
  | "401"
  | "403"
  | "429"
  | "4xx"
  | "5xx"
  | "other"
  | "mixed"
  | "unavailable"
type ResponsePhase = "none" | "before-click" | "after-click" | "mixed"
type Route = "auth" | "csrf" | "forgot"
type Stat = {
  requests: Count
  responses: Count
  completed: Count
  failed: Count
  status: Status
  responsePhase: ResponsePhase
}
type Snapshot = {
  forgotRoute: boolean
  hydrated: boolean
  formPresent: boolean
  formInvalid: boolean
  formAlert: boolean
  submitPresent: boolean
  submitDisabled: boolean
  submitBusy: boolean
  successMarkerVisible: boolean
}
type RecordValue = {
  scope: "main-frame-navigation-window" | "unconfirmed"
  schema: 1
  project: "desktop" | "mobile"
  attempt: 0 | 1
  phase: Phase
  elapsed: "lt1s" | "1to5s" | "5to15s" | "ge15s" | "unavailable"
  auth: Stat
  csrf: Stat
  forgot: Stat
  snapshot: Snapshot | null
}

const SNAPSHOT_KEYS = [
  "forgotRoute",
  "hydrated",
  "formPresent",
  "formInvalid",
  "formAlert",
  "submitPresent",
  "submitDisabled",
  "submitBusy",
  "successMarkerVisible",
] as const
const STAT_KEYS = [
  "requests",
  "responses",
  "completed",
  "failed",
  "status",
  "responsePhase",
] as const
const RECORD_KEYS = [
  "scope",
  "schema",
  "project",
  "attempt",
  "phase",
  "elapsed",
  "auth",
  "csrf",
  "forgot",
  "snapshot",
] as const
const COUNTS = new Set(["0", "1", "many"])
const STATUSES = new Set([
  "none",
  "2xx",
  "401",
  "403",
  "429",
  "4xx",
  "5xx",
  "other",
  "mixed",
  "unavailable",
])
const RESPONSE_PHASES = new Set(["none", "before-click", "after-click", "mixed"])
const PHASES = new Set(["navigate", "fill", "click", "success"])
const ELAPSED = new Set(["lt1s", "1to5s", "5to15s", "ge15s", "unavailable"])
const emitted = new Set<string>()

function ownValues(value: unknown, expected: readonly string[]): Record<string, unknown> | null {
  if (value === null || typeof value !== "object" || Array.isArray(value)) return null
  try {
    const descriptors = Object.getOwnPropertyDescriptors(value)
    const keys = Reflect.ownKeys(descriptors)
    if (
      keys.length !== expected.length ||
      keys.some((key) => typeof key !== "string" || !expected.includes(key))
    )
      return null
    const result: Record<string, unknown> = Object.create(null)
    for (const key of expected) {
      const descriptor = descriptors[key]
      if (!descriptor || !("value" in descriptor)) return null
      result[key] = descriptor.value
    }
    return result
  } catch {
    return null
  }
}

function validatedSnapshot(value: unknown): Snapshot | null {
  const input = ownValues(value, SNAPSHOT_KEYS)
  if (!input || SNAPSHOT_KEYS.some((key) => typeof input[key] !== "boolean")) return null
  if (
    (!input.formPresent &&
      (input.formInvalid ||
        input.formAlert ||
        input.submitPresent ||
        input.submitDisabled ||
        input.submitBusy)) ||
    (!input.submitPresent && (input.submitDisabled || input.submitBusy))
  )
    return null
  return Object.fromEntries(SNAPSHOT_KEYS.map((key) => [key, input[key]])) as Snapshot
}

function validatedStat(value: unknown): Stat | null {
  const input = ownValues(value, STAT_KEYS)
  if (
    !input ||
    ["requests", "responses", "completed", "failed"].some(
      (key) => !COUNTS.has(input[key] as string)
    ) ||
    !STATUSES.has(input.status as string) ||
    !RESPONSE_PHASES.has(input.responsePhase as string)
  )
    return null
  if (
    input.requests === "0" &&
    (input.responses !== "0" || input.completed !== "0" || input.failed !== "0")
  )
    return null
  if (
    (input.responses === "0") !== (input.status === "none") ||
    (input.responses === "0") !== (input.responsePhase === "none")
  )
    return null
  if (input.completed !== "0" && input.responses === "0") return null
  if (
    input.requests === "1" &&
    (input.responses === "many" ||
      input.completed === "many" ||
      input.failed === "many" ||
      (input.completed === "1" && input.failed === "1"))
  )
    return null
  return Object.fromEntries(STAT_KEYS.map((key) => [key, input[key]])) as Stat
}

export function validatedPasswordForgotRecord(value: unknown): RecordValue | null {
  const input = ownValues(value, RECORD_KEYS)
  if (
    !input ||
    (input.scope !== "main-frame-navigation-window" && input.scope !== "unconfirmed") ||
    input.schema !== 1 ||
    (input.project !== "desktop" && input.project !== "mobile") ||
    (input.attempt !== 0 && input.attempt !== 1) ||
    !PHASES.has(input.phase as string) ||
    !ELAPSED.has(input.elapsed as string)
  )
    return null
  const auth = validatedStat(input.auth)
  const csrf = validatedStat(input.csrf)
  const forgot = validatedStat(input.forgot)
  const snapshot = input.snapshot === null ? null : validatedSnapshot(input.snapshot)
  if (!auth || !csrf || !forgot || (input.snapshot !== null && snapshot === null)) return null
  if (input.scope === "unconfirmed" && [auth, csrf, forgot].some((stat) => stat.requests !== "0"))
    return null
  return {
    scope: input.scope,
    schema: 1,
    project: input.project,
    attempt: input.attempt,
    phase: input.phase as Phase,
    elapsed: input.elapsed as RecordValue["elapsed"],
    auth,
    csrf,
    forgot,
    snapshot,
  }
}

export function reportPasswordForgotFailure(value: unknown): void {
  try {
    const record = validatedPasswordForgotRecord(value)
    if (!record) return
    const key = record.project + ":" + record.attempt
    if (emitted.has(key) || emitted.size >= 4) return
    const line = "UE_LIVE_PASSWORD_FORGOT_V1 " + JSON.stringify(record) + "\n"
    if (line.length > 2_048) return // All validated output is ASCII.
    emitted.add(key)
    try {
      process.stdout.write(line)
    } catch {
      /* Preserve original assertion. */
    }
  } catch {
    /* Diagnostics cannot replace the original assertion. */
  }
}

function readForgotSnapshot() {
  const submit = document.getElementById("forgot-submit-btn")
  const form = submit?.closest("form") ?? null
  const submitPresent = submit instanceof HTMLButtonElement && form !== null
  const successMarker = document.getElementById("forgot-back-to-login")
  const successBox = successMarker?.getBoundingClientRect()
  const successMarkerVisible = Boolean(
    successMarker &&
      successBox &&
      successBox.width > 0 &&
      successBox.height > 0 &&
      window.getComputedStyle(successMarker).visibility === "visible"
  )
  return {
    forgotRoute: window.location.pathname === "/forgot-password",
    hydrated: window.__APP_HYDRATED === true,
    formPresent: form !== null,
    formInvalid: form?.matches(":invalid") ?? false,
    formAlert: Boolean(form?.querySelector('[role="alert"]')),
    submitPresent,
    submitDisabled: submitPresent && (submit as HTMLButtonElement).disabled,
    submitBusy: submitPresent && submit?.getAttribute("aria-busy") === "true",
    successMarkerVisible,
  }
}

async function snapshotWithinDeadline(
  page: Page,
  deadlineAtMs: number | null
): Promise<Snapshot | null> {
  const remaining =
    typeof deadlineAtMs === "number" && Number.isFinite(deadlineAtMs)
      ? Math.floor(deadlineAtMs - performance.now())
      : 0
  if (remaining < 1) return null
  let timer: ReturnType<typeof setTimeout> | undefined
  // A timeout stops only our wait. The read-only evaluation retains a rejection
  // handler and may finish later; it performs no mutation or logging.
  const pending = Promise.resolve()
    .then(() => {
      if (
        typeof deadlineAtMs !== "number" ||
        !Number.isFinite(deadlineAtMs) ||
        Math.floor(deadlineAtMs - performance.now()) < 1
      )
        return null
      return page.evaluate(readForgotSnapshot)
    })
    .then(validatedSnapshot, () => null)
  try {
    return await Promise.race([
      pending,
      new Promise<null>((resolve) => {
        timer = setTimeout(() => resolve(null), Math.min(250, remaining))
      }),
    ])
  } catch {
    return null
  } finally {
    if (timer !== undefined) clearTimeout(timer)
  }
}

function emptyStat(): Stat {
  return {
    requests: "0",
    responses: "0",
    completed: "0",
    failed: "0",
    status: "none",
    responsePhase: "none",
  }
}

function increment(value: Count): Count {
  return value === "0" ? "1" : "many"
}

function statusClass(status: number): Status {
  if (!Number.isInteger(status) || status < 100 || status > 599) return "unavailable"
  if (status >= 200 && status < 300) return "2xx"
  if (status === 401 || status === 403 || status === 429) return String(status) as Status
  if (status >= 400 && status < 500) return "4xx"
  if (status >= 500) return "5xx"
  return "other"
}

function elapsedClass(start: number): RecordValue["elapsed"] {
  const elapsed = performance.now() - start
  return !Number.isFinite(elapsed) || elapsed < 0
    ? "unavailable"
    : elapsed < 1_000
      ? "lt1s"
      : elapsed < 5_000
        ? "1to5s"
        : elapsed < 15_000
          ? "5to15s"
          : "ge15s"
}

export async function withPasswordForgotDiagnostics<T>(
  page: Page,
  options: { project: string; attempt: number; ownedOrigin: string; deadlineAtMs: number | null },
  action: (markPhase: (phase: Phase) => void) => Promise<T>
): Promise<T> {
  const { project, attempt, ownedOrigin, deadlineAtMs } = options
  const noObserve = () => action(() => undefined)
  if ((project !== "desktop" && project !== "mobile") || (attempt !== 0 && attempt !== 1))
    return noObserve()
  try {
    const origin = new URL(ownedOrigin)
    if (
      !["http:", "https:"].includes(origin.protocol) ||
      !["localhost", "127.0.0.1"].includes(origin.hostname) ||
      !origin.port ||
      origin.port === "0" ||
      origin.origin !== ownedOrigin ||
      origin.username ||
      origin.password
    )
      return noObserve()
  } catch {
    return noObserve()
  }
  const started = performance.now()
  const stats = { auth: emptyStat(), csrf: emptyStat(), forgot: emptyStat() }
  const tracked = new WeakMap<Request, Route>()
  const responded = new WeakSet<Request>()
  const terminated = new WeakSet<Request>()
  let phase: Phase = "navigate"
  let disposed = false
  let scope: RecordValue["scope"] = "unconfirmed"
  let insideNavigationWindow = false
  // framenavigated includes same-document events; this is an observation window,
  // not a renderer document ID or proof of auth/epoch completion.
  const onFrameNavigated = (frame: Frame) => {
    if (disposed) return
    try {
      if (frame !== page.mainFrame()) return
      insideNavigationWindow = frame.url() === ownedOrigin + "/forgot-password"
      if (insideNavigationWindow) scope = "main-frame-navigation-window"
    } catch {
      insideNavigationWindow = false
    }
  }
  const markPhase = (next: Phase) => {
    if (PHASES.has(next)) phase = next
  }
  const onRequest = (request: Request) => {
    if (disposed || !insideNavigationWindow || tracked.has(request)) return
    try {
      if (request.frame() !== page.mainFrame()) return
      const raw = request.url()
      const method = request.method()
      // Exact equality: never normalize query, encoded-path, userinfo or dot aliases.
      const route: Route | null =
        method === "GET" && raw === ownedOrigin + "/api/v1/users/me"
          ? "auth"
          : method === "GET" && raw === ownedOrigin + "/api/v1/auth/csrf-cookie"
            ? "csrf"
            : method === "POST" && raw === ownedOrigin + "/api/v1/password/forgot"
              ? "forgot"
              : null
      if (route === null) return
      tracked.set(request, route)
      stats[route].requests = increment(stats[route].requests)
    } catch {
      /* Retain no raw URL, request values, or error. */
    }
  }
  const onResponse = (response: Response) => {
    if (disposed) return
    try {
      const request = response.request()
      const route = tracked.get(request)
      if (!route || responded.has(request)) return
      let status: Status = "unavailable"
      try {
        status = statusClass(response.status())
      } catch {
        /* Never inspect the error. */
      }
      responded.add(request)
      const stat = stats[route]
      stat.responses = increment(stat.responses)
      stat.status = stat.status === "none" ? status : stat.status === status ? status : "mixed"
      // Relative to invoking click(), not proof of browser delivery/handler completion.
      const observedPhase =
        phase === "navigate" || phase === "fill" ? "before-click" : "after-click"
      stat.responsePhase =
        stat.responsePhase === "none"
          ? observedPhase
          : stat.responsePhase === observedPhase
            ? observedPhase
            : "mixed"
    } catch {
      /* Retain no response content or error. */
    }
  }
  const finish = (request: Request, failed: boolean) => {
    if (disposed) return
    try {
      const route = tracked.get(request)
      if (!route || terminated.has(request)) return
      terminated.add(request)
      const field = failed ? "failed" : "completed"
      stats[route][field] = increment(stats[route][field])
    } catch {
      /* No request.failure() or error strings. */
    }
  }
  const onFinished = (request: Request) => finish(request, false)
  const onFailed = (request: Request) => finish(request, true)
  const dispose = () => {
    if (disposed) return
    disposed = true
    for (const stop of [
      () => page.off("framenavigated", onFrameNavigated),
      () => page.off("request", onRequest),
      () => page.off("response", onResponse),
      () => page.off("requestfinished", onFinished),
      () => page.off("requestfailed", onFailed),
    ]) {
      try {
        stop()
      } catch {
        /* Continue detaching remaining listeners. */
      }
    }
  }
  try {
    page.on("framenavigated", onFrameNavigated)
    page.on("request", onRequest)
    page.on("response", onResponse)
    page.on("requestfinished", onFinished)
    page.on("requestfailed", onFailed)
  } catch {
    dispose()
    return noObserve()
  }
  try {
    return await action(markPhase)
  } catch (error) {
    dispose()
    try {
      const elapsed = elapsedClass(started)
      const snapshot = await snapshotWithinDeadline(page, deadlineAtMs)
      reportPasswordForgotFailure({
        scope,
        schema: 1,
        project,
        attempt,
        phase,
        elapsed,
        ...stats,
        snapshot,
      })
    } catch {
      /* Preserve exact original failure object. */
    }
    throw error
  } finally {
    dispose()
  }
}
