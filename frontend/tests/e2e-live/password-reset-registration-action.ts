import type { Page, Request, Response } from "@playwright/test"

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
  submitPresent: boolean
  submitDisabled: boolean
  submitBusy: boolean
}

type CsrfResponseClass = "not-observed" | "success" | "http-error" | "mixed" | "unavailable"

const SNAPSHOT_KEYS = [
  "hydrated",
  "formPresent",
  "formInvalid",
  "formError",
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
