import type { JSHandle, Page, Request, Response } from "@playwright/test"

export type ResetRegistrationStep = "arm-response" | "click" | "await-response"

type ResetRegistrationDiagnostics = {
  reportFailure: (step: ResetRegistrationStep, error: unknown) => Promise<void>
  dispose: () => void
}

type RegistrationSnapshot = {
  hydrated: boolean
  formPresent: boolean
  formInvalid: boolean
  formError: boolean
  nameError: boolean
  emailError: boolean
  inviteError: boolean
  passwordError: boolean
  confirmError: boolean
  rootError: boolean
  submitPresent: boolean
  submitDisabled: boolean
  submitBusy: boolean
}

type CsrfResponseClass = "not-observed" | "success" | "http-error" | "mixed" | "unavailable"

const ERROR_SNAPSHOT_KEYS = [
  "nameError",
  "emailError",
  "inviteError",
  "passwordError",
  "confirmError",
  "rootError",
] as const

const SNAPSHOT_KEYS = [
  "hydrated",
  "formPresent",
  "formInvalid",
  "formError",
  ...ERROR_SNAPSHOT_KEYS,
  "submitPresent",
  "submitDisabled",
  "submitBusy",
] as const
const emittedRegistrationDiagnostics = new Set<string>()
const MAX_REGISTRATION_DIAGNOSTICS = 6
const MAX_SNAPSHOT_MS = 250

function registrationErrorCategory(error: unknown): string {
  if (typeof error !== "object" || error === null) return "other"
  try {
    switch ((error as { name?: unknown }).name) {
      case "TimeoutError":
        return "timeout"
      case "AbortError":
        return "abort"
      case "TypeError":
        return "type-error"
      case "TargetClosedError":
        return "target-closed"
      case "Error":
        return "error"
    }
  } catch {
    // Never inspect private error messages, stacks, or constructor names.
  }
  return "other"
}

function validateRegistrationSnapshot(value: unknown): RegistrationSnapshot | null {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return null
  try {
    const descriptors = Object.getOwnPropertyDescriptors(value)
    const keys = Object.keys(descriptors)
    if (
      keys.length !== SNAPSHOT_KEYS.length ||
      keys.some((key) => !SNAPSHOT_KEYS.some((expected) => key === expected))
    ) {
      return null
    }
    const snapshot = {} as RegistrationSnapshot
    for (const key of SNAPSHOT_KEYS) {
      const descriptor = descriptors[key]
      if (!descriptor || !("value" in descriptor) || typeof descriptor.value !== "boolean") {
        return null
      }
      snapshot[key] = descriptor.value
    }
    if (
      (!snapshot.formPresent &&
        (snapshot.formInvalid ||
          snapshot.formError ||
          snapshot.submitPresent ||
          snapshot.submitDisabled ||
          snapshot.submitBusy)) ||
      (!snapshot.formError && ERROR_SNAPSHOT_KEYS.some((key) => snapshot[key])) ||
      (!snapshot.submitPresent && (snapshot.submitDisabled || snapshot.submitBusy))
    ) {
      return null
    }
    return snapshot
  } catch {
    return null
  }
}

async function registrationSnapshot(
  page: Page,
  deadlineAtMs: number | null
): Promise<RegistrationSnapshot | null> {
  const remainingMs =
    typeof deadlineAtMs === "number" && Number.isFinite(deadlineAtMs)
      ? Math.floor(deadlineAtMs - performance.now())
      : 0
  if (remainingMs < 1) return null
  let timer: ReturnType<typeof setTimeout> | undefined
  try {
    const pending = page
      .evaluate(() => {
        const submit = document.getElementById("register-submit")
        const form = submit?.closest("form") ?? document.querySelector("form")
        const submitPresent = submit instanceof HTMLButtonElement && form !== null
        return {
          hydrated: (window as Window & { __APP_HYDRATED?: unknown }).__APP_HYDRATED === true,
          formPresent: form !== null,
          formInvalid: form?.matches(":invalid") ?? false,
          formError: Boolean(form?.querySelector('[role="alert"]')),
          nameError: Boolean(form?.querySelector('#register-name-error[role="alert"]')),
          emailError: Boolean(form?.querySelector('#register-email-error[role="alert"]')),
          inviteError: Boolean(form?.querySelector('#register-invite-error[role="alert"]')),
          passwordError: Boolean(form?.querySelector('#register-password-error[role="alert"]')),
          confirmError: Boolean(
            form?.querySelector('#register-confirm-password-error[role="alert"]')
          ),
          rootError: Boolean(form?.querySelector(':scope > [role="alert"][aria-live="assertive"]')),
          submitPresent,
          submitDisabled: submitPresent && (submit as HTMLButtonElement).disabled,
          submitBusy: submitPresent && submit?.getAttribute("aria-busy") === "true",
        }
      })
      .then(validateRegistrationSnapshot, () => null)
    // The losing evaluation still owns its rejection. This diagnostic budget is
    // strictly inside the existing test deadline, never a new test allowance.
    const expired = new Promise<null>((resolve) => {
      timer = setTimeout(() => resolve(null), Math.min(MAX_SNAPSHOT_MS, remainingMs))
    })
    return await Promise.race([pending, expired])
  } catch {
    return null
  } finally {
    if (timer !== undefined) clearTimeout(timer)
  }
}

export function createPasswordResetRegistrationDiagnostics(
  page: Page,
  project: string,
  ownedOrigin: string,
  deadlineAtMs: number | null
): ResetRegistrationDiagnostics {
  const noop: ResetRegistrationDiagnostics = {
    reportFailure: async () => undefined,
    dispose: () => undefined,
  }
  if (project !== "desktop" && project !== "mobile") return noop
  if (typeof ownedOrigin !== "string") return noop
  try {
    const origin = new URL(ownedOrigin)
    if (
      origin.origin !== ownedOrigin ||
      (origin.protocol !== "http:" && origin.protocol !== "https:") ||
      origin.username !== "" ||
      origin.password !== ""
    ) {
      return noop
    }
  } catch {
    return noop
  }

  const tracked = new WeakSet<Request>()
  let csrfRequested = false
  let csrfResponse: CsrfResponseClass = "not-observed"
  let csrfFailed = false
  let disposed = false
  const onRequest = (request: Request) => {
    if (disposed) return
    try {
      const rawUrl = request.url()
      if (typeof rawUrl !== "string" || request.method() !== "GET") return
      const url = new URL(rawUrl)
      if (
        url.origin !== ownedOrigin ||
        url.username !== "" ||
        url.password !== "" ||
        url.pathname !== "/api/v1/auth/csrf-cookie" ||
        url.search !== "" ||
        url.hash !== ""
      ) {
        return
      }
      tracked.add(request)
      csrfRequested = true
    } catch {
      // Passive observation must not change request behavior.
    }
  }
  const onResponse = (response: Response) => {
    if (disposed) return
    try {
      if (!tracked.has(response.request())) return
      const status = response.status()
      const classification =
        !Number.isInteger(status) || status < 100 || status > 599
          ? "unavailable"
          : status >= 200 && status < 300
            ? "success"
            : "http-error"
      if (classification === "unavailable" || csrfResponse === "unavailable") {
        csrfResponse = "unavailable"
      } else if (csrfResponse === "not-observed") {
        csrfResponse = classification
      } else if (csrfResponse !== classification) {
        csrfResponse = "mixed"
      }
    } catch {
      // Do not retain response objects, addresses, headers, or content.
    }
  }
  const onRequestFailed = (request: Request) => {
    if (!disposed && tracked.has(request)) csrfFailed = true
  }
  const dispose = () => {
    if (disposed) return
    disposed = true
    for (const stop of [
      () => page.off("request", onRequest),
      () => page.off("response", onResponse),
      () => page.off("requestfailed", onRequestFailed),
    ]) {
      try {
        stop()
      } catch {
        // Continue detaching the other listeners if one accessor is unavailable.
      }
    }
  }
  try {
    page.on("request", onRequest)
    page.on("response", onResponse)
    page.on("requestfailed", onRequestFailed)
  } catch {
    dispose()
    return noop
  }

  return {
    async reportFailure(step, error) {
      if (
        disposed ||
        emittedRegistrationDiagnostics.size >= MAX_REGISTRATION_DIAGNOSTICS ||
        (step !== "arm-response" && step !== "click" && step !== "await-response")
      ) {
        return
      }
      const snapshot = await registrationSnapshot(page, deadlineAtMs)
      if (disposed || emittedRegistrationDiagnostics.size >= MAX_REGISTRATION_DIAGNOSTICS) return
      const record = {
        project,
        step,
        errorCategory: registrationErrorCategory(error),
        snapshot: snapshot === null ? "unavailable" : "available",
        hydrated: snapshot?.hydrated ?? false,
        formPresent: snapshot?.formPresent ?? false,
        formInvalid: snapshot?.formInvalid ?? false,
        formError: snapshot?.formError ?? false,
        nameError: snapshot?.nameError ?? false,
        emailError: snapshot?.emailError ?? false,
        inviteError: snapshot?.inviteError ?? false,
        passwordError: snapshot?.passwordError ?? false,
        confirmError: snapshot?.confirmError ?? false,
        rootError: snapshot?.rootError ?? false,
        submitPresent: snapshot?.submitPresent ?? false,
        submitDisabled: snapshot?.submitDisabled ?? false,
        submitBusy: snapshot?.submitBusy ?? false,
        csrfRequested,
        csrfResponse,
        csrfFailed,
      }
      const line = "UE_LIVE_RESET_REGISTRATION_V2 " + JSON.stringify(record) + "\n"
      if (emittedRegistrationDiagnostics.has(line)) return
      emittedRegistrationDiagnostics.add(line)
      try {
        process.stdout.write(line)
      } catch {
        // Diagnostics never replace the original registration action exception.
      }
    },
    dispose,
  }
}

type RegistrationNameState = "missing" | "empty" | "short" | "at-least-two"
type RegistrationTimelineSnapshot = {
  hydrated: boolean
  nameState: RegistrationNameState
  nameError: boolean
}
type RegistrationSubmitSnapshot = RegistrationTimelineSnapshot & {
  trigger: "click" | "invalid" | "submit"
}
type RegistrationTimelineReadout = {
  beforeName: RegistrationTimelineSnapshot | null
  afterName: RegistrationTimelineSnapshot | null
  beforeSubmit: RegistrationSubmitSnapshot | null
}
type RegistrationBrowserObserver = {
  read: () => RegistrationTimelineReadout
  dispose: () => void
}
type RegistrationTimeline = {
  setup: () => Promise<void>
  reportFailure: (step: ResetRegistrationStep) => Promise<void>
  dispose: () => void
}

const emittedRegistrationTimelines = new Set<string>()

function validateRegistrationTimelineSnapshot(
  value: unknown,
  requireTrigger: boolean
): RegistrationTimelineSnapshot | RegistrationSubmitSnapshot | null {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return null
  try {
    const descriptors = Object.getOwnPropertyDescriptors(value)
    const keys = Reflect.ownKeys(descriptors)
    const expected = requireTrigger
      ? ["hydrated", "nameState", "nameError", "trigger"]
      : ["hydrated", "nameState", "nameError"]
    if (
      keys.length !== expected.length ||
      keys.some((key) => typeof key !== "string" || !expected.includes(key))
    ) {
      return null
    }
    const hydrated = descriptors.hydrated
    const nameState = descriptors.nameState
    const nameError = descriptors.nameError
    if (
      !hydrated ||
      !("value" in hydrated) ||
      typeof hydrated.value !== "boolean" ||
      !nameError ||
      !("value" in nameError) ||
      typeof nameError.value !== "boolean" ||
      !nameState ||
      !("value" in nameState) ||
      (nameState.value !== "missing" &&
        nameState.value !== "empty" &&
        nameState.value !== "short" &&
        nameState.value !== "at-least-two")
    ) {
      return null
    }
    const snapshot = {
      hydrated: hydrated.value,
      nameState: nameState.value,
      nameError: nameError.value,
    }
    if (!requireTrigger) return snapshot
    const trigger = descriptors.trigger
    if (
      !trigger ||
      !("value" in trigger) ||
      (trigger.value !== "click" && trigger.value !== "invalid" && trigger.value !== "submit")
    ) {
      return null
    }
    return { ...snapshot, trigger: trigger.value }
  } catch {
    return null
  }
}

function validateRegistrationTimelineReadout(value: unknown): RegistrationTimelineReadout {
  const empty: RegistrationTimelineReadout = {
    beforeName: null,
    afterName: null,
    beforeSubmit: null,
  }
  if (typeof value !== "object" || value === null || Array.isArray(value)) return empty
  try {
    const descriptors = Object.getOwnPropertyDescriptors(value)
    const keys = Reflect.ownKeys(descriptors)
    if (
      keys.length !== 3 ||
      keys.some((key) => key !== "beforeName" && key !== "afterName" && key !== "beforeSubmit")
    ) {
      return empty
    }
    const beforeName = descriptors.beforeName
    const afterName = descriptors.afterName
    const beforeSubmit = descriptors.beforeSubmit
    if (
      !beforeName ||
      !("value" in beforeName) ||
      !afterName ||
      !("value" in afterName) ||
      !beforeSubmit ||
      !("value" in beforeSubmit)
    ) {
      return empty
    }
    return {
      beforeName: validateRegistrationTimelineSnapshot(beforeName.value, false),
      afterName: validateRegistrationTimelineSnapshot(afterName.value, false),
      beforeSubmit: validateRegistrationTimelineSnapshot(
        beforeSubmit.value,
        true
      ) as RegistrationSubmitSnapshot | null,
    }
  } catch {
    return empty
  }
}

function timelineRemainingMs(deadlineAtMs: number | null): number {
  return typeof deadlineAtMs === "number" && Number.isFinite(deadlineAtMs)
    ? Math.max(0, Math.floor(deadlineAtMs - performance.now()))
    : 0
}

async function withinTimelineBudget<T>(
  pending: Promise<T>,
  deadlineAtMs: number | null,
  fallback: T,
  onExpire?: () => void
): Promise<T> {
  const remainingMs = timelineRemainingMs(deadlineAtMs)
  if (remainingMs < 1) {
    onExpire?.()
    void pending.catch(() => undefined)
    return fallback
  }
  let timer: ReturnType<typeof setTimeout> | undefined
  try {
    const expired = new Promise<T>((resolve) => {
      timer = setTimeout(
        () => {
          onExpire?.()
          resolve(fallback)
        },
        Math.min(MAX_SNAPSHOT_MS, remainingMs)
      )
    })
    return await Promise.race([pending, expired])
  } catch {
    return fallback
  } finally {
    if (timer !== undefined) clearTimeout(timer)
  }
}

export function createPasswordResetRegistrationTimeline(
  page: Page,
  project: string,
  deadlineAtMs: number | null
): RegistrationTimeline {
  const noop: RegistrationTimeline = {
    setup: async () => undefined,
    reportFailure: async () => undefined,
    dispose: () => undefined,
  }
  if (project !== "desktop" && project !== "mobile") return noop
  let observer: JSHandle<RegistrationBrowserObserver> | null = null
  let closed = false
  let setupStarted = false
  let setupExpired = false

  const release = async (candidate: JSHandle<RegistrationBrowserObserver>): Promise<void> => {
    try {
      const detach = candidate
        .evaluate((value) => value.dispose())
        .then(
          () => undefined,
          () => undefined
        )
      await withinTimelineBudget(detach, deadlineAtMs, undefined)
    } catch {
      // A closed page has already removed its document listeners.
    }
    try {
      const disposeHandle = candidate.dispose().then(
        () => undefined,
        () => undefined
      )
      await withinTimelineBudget(disposeHandle, deadlineAtMs, undefined)
    } catch {
      // Handle cleanup never replaces a test outcome.
    }
  }

  return {
    async setup() {
      if (closed || setupStarted || timelineRemainingMs(deadlineAtMs) < 1) return
      setupStarted = true
      try {
        const pending = page
          .evaluateHandle(() => {
            const snapshot = (): RegistrationTimelineSnapshot => {
              const input = document.getElementById("full_name")
              const length = input instanceof HTMLInputElement ? input.value.length : null
              return {
                hydrated: (window as Window & { __APP_HYDRATED?: unknown }).__APP_HYDRATED === true,
                nameState:
                  length === null
                    ? "missing"
                    : length === 0
                      ? "empty"
                      : length === 1
                        ? "short"
                        : "at-least-two",
                nameError: Boolean(document.querySelector('#register-name-error[role="alert"]')),
              }
            }
            const result: RegistrationTimelineReadout = {
              beforeName: snapshot(),
              afterName: null,
              beforeSubmit: null,
            }
            const onInput = (event: Event) => {
              if (event.target instanceof HTMLInputElement && event.target.id === "full_name") {
                result.afterName = snapshot()
              }
            }
            const onAction = (event: Event) => {
              if (result.beforeSubmit !== null) return
              const button = document.getElementById("register-submit")
              const form = button?.closest("form")
              if (!button || !form) return
              if (event.type === "click") {
                if (
                  !(event.target instanceof Element) ||
                  event.target.closest("#register-submit") !== button
                )
                  return
              } else if (event.type === "invalid") {
                if (!(event.target instanceof Element) || event.target.closest("form") !== form)
                  return
              } else if (event.type === "submit") {
                if (event.target !== form) return
              } else {
                return
              }
              result.beforeSubmit = {
                ...snapshot(),
                trigger: event.type as "click" | "invalid" | "submit",
              }
            }
            document.addEventListener("input", onInput, true)
            document.addEventListener("click", onAction, true)
            document.addEventListener("invalid", onAction, true)
            document.addEventListener("submit", onAction, true)
            return {
              read: () => ({ ...result }),
              dispose: () => {
                document.removeEventListener("input", onInput, true)
                document.removeEventListener("click", onAction, true)
                document.removeEventListener("invalid", onAction, true)
                document.removeEventListener("submit", onAction, true)
              },
            }
          })
          .then(
            (candidate) => {
              if (closed || setupExpired) {
                void release(candidate)
                return null
              }
              return candidate
            },
            () => null
          )
        const candidate = await withinTimelineBudget(pending, deadlineAtMs, null, () => {
          setupExpired = true
        })
        if (candidate !== null) {
          if (closed) void release(candidate)
          else observer = candidate
        }
      } catch {
        // A failed setup leaves all observations unavailable.
      }
    },
    async reportFailure(step) {
      if (
        closed ||
        (step !== "arm-response" && step !== "click" && step !== "await-response") ||
        emittedRegistrationTimelines.size >= MAX_REGISTRATION_DIAGNOSTICS
      ) {
        return
      }
      let readout: RegistrationTimelineReadout = {
        beforeName: null,
        afterName: null,
        beforeSubmit: null,
      }
      if (observer !== null) {
        try {
          const pending = observer
            .evaluate((value) => value.read())
            .then(validateRegistrationTimelineReadout, () => readout)
          readout = await withinTimelineBudget(pending, deadlineAtMs, readout)
        } catch {
          // A failed read leaves all observations unavailable.
        }
      }
      const record = { project, step, ...readout }
      const line = "UE_LIVE_RESET_REGISTRATION_V3 " + JSON.stringify(record) + "\n"
      if (emittedRegistrationTimelines.has(line)) return
      emittedRegistrationTimelines.add(line)
      try {
        process.stdout.write(line)
      } catch {
        // Diagnostics cannot replace the registration action's original error.
      }
    },
    dispose() {
      if (closed) return
      closed = true
      const candidate = observer
      observer = null
      if (candidate !== null) void release(candidate)
    },
  }
}

export function withPasswordResetRegistrationTimeline(
  diagnostics: ResetRegistrationDiagnostics,
  timeline: RegistrationTimeline
): ResetRegistrationDiagnostics {
  return {
    async reportFailure(step, error) {
      await Promise.allSettled([
        Promise.resolve().then(() => diagnostics.reportFailure(step, error)),
        Promise.resolve().then(() => timeline.reportFailure(step)),
      ])
    },
    dispose() {
      try {
        diagnostics.dispose()
      } finally {
        timeline.dispose()
      }
    },
  }
}

export async function withRegistrationTimeline<T>(
  timeline: RegistrationTimeline,
  action: () => Promise<T>
): Promise<T> {
  try {
    return await action()
  } finally {
    try {
      timeline.dispose()
    } catch {
      // Cleanup cannot replace the original response or failure.
    }
  }
}

export async function runPasswordResetRegistrationAction<T>(
  armResponse: () => Promise<T>,
  click: () => Promise<unknown>,
  reportFailure: (step: ResetRegistrationStep) => void,
  diagnostics?: ResetRegistrationDiagnostics
): Promise<T> {
  let step: ResetRegistrationStep = "arm-response"
  try {
    const pending = armResponse()
    // Own a later rejection even when clicking fails before the original await.
    // Awaiting the original promise below still propagates response failures.
    void pending.catch(() => undefined)
    step = "click"
    await click()
    step = "await-response"
    return await pending
  } catch (error) {
    try {
      reportFailure(step)
    } catch {
      // A diagnostic sink must never replace the original operation error.
    }
    try {
      await diagnostics?.reportFailure(step, error)
    } catch {
      // The optional V2 sink has the same non-interference contract as V1.
    }
    throw error
  } finally {
    try {
      diagnostics?.dispose()
    } catch {
      // Teardown cannot replace a successful value or the original exception.
    }
  }
}
