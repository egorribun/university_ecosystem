const emittedRecords = new Set<string>()
const MAX_RECORDS = 4
const MAX_COUNT = 999
const MAX_DETAIL_ITEMS = 256

type DetailKind =
  "absent" | "array" | "object" | "string" | "number" | "boolean" | "null" | "unavailable"
type PageErrorKind =
  | "none"
  | "error"
  | "type-error"
  | "reference-error"
  | "syntax-error"
  | "range-error"
  | "uri-error"
  | "eval-error"
  | "aggregate-error"
  | "abort-error"
  | "security-error"
  | "invalid-state-error"
  | "other"
  | "unknown"
type SafeFlag = "true" | "false" | "unknown"

interface ProfileSaveFailureInput {
  project: unknown
  status: unknown
  body: unknown
  alertCount: unknown
  saveDisabled: unknown
  pathname: unknown
  pageErrors: unknown
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
}

function boundedCount(value: unknown): string {
  if (typeof value !== "number" || !Number.isInteger(value) || value < 0) return "unknown"
  return String(Math.min(value, MAX_COUNT))
}

function detailSummary(body: unknown): { kind: DetailKind; count: string; message: SafeFlag } {
  if (body === undefined) return { kind: "unavailable", count: "unknown", message: "unknown" }
  if (!isRecord(body)) return { kind: "absent", count: "0", message: "false" }
  try {
    if (!Object.prototype.hasOwnProperty.call(body, "detail")) {
      return { kind: "absent", count: "0", message: "false" }
    }
    const detail = body.detail
    if (Array.isArray(detail)) {
      const count = boundedCount(detail.length)
      const inspected = Math.min(detail.length, MAX_DETAIL_ITEMS)
      for (let index = 0; index < inspected; index += 1) {
        const entry = detail[index]
        if (
          isRecord(entry) &&
          Object.prototype.hasOwnProperty.call(entry, "msg") &&
          typeof entry.msg === "string"
        ) {
          return { kind: "array", count, message: "true" }
        }
      }
      return {
        kind: "array",
        count,
        message: detail.length > MAX_DETAIL_ITEMS ? "unknown" : "false",
      }
    }
    if (detail === null) return { kind: "null", count: "0", message: "false" }
    if (isRecord(detail)) {
      return {
        kind: "object",
        count: "0",
        message:
          Object.prototype.hasOwnProperty.call(detail, "msg") && typeof detail.msg === "string"
            ? "true"
            : "false",
      }
    }
    switch (typeof detail) {
      case "string":
        return { kind: "string", count: "0", message: "false" }
      case "number":
        return { kind: "number", count: "0", message: "false" }
      case "boolean":
        return { kind: "boolean", count: "0", message: "false" }
      default:
        return { kind: "unavailable", count: "unknown", message: "unknown" }
    }
  } catch {
    return { kind: "unavailable", count: "unknown", message: "unknown" }
  }
}

function routeFamily(pathname: unknown): "profile" | "login" | "register" | "dashboard" | "other" {
  switch (pathname) {
    case "/profile":
      return "profile"
    case "/login":
      return "login"
    case "/register":
      return "register"
    case "/dashboard":
      return "dashboard"
    default:
      return "other"
  }
}

function firstPageError(errors: unknown): { count: string; kind: PageErrorKind } {
  if (!Array.isArray(errors)) return { count: "unknown", kind: "unknown" }
  if (errors.length === 0) return { count: "0", kind: "none" }
  let name: unknown
  try {
    name = errors[0]?.name
  } catch {
    return { count: boundedCount(errors.length), kind: "other" }
  }
  const known: Record<string, Exclude<PageErrorKind, "none" | "unknown">> = {
    Error: "error",
    TypeError: "type-error",
    ReferenceError: "reference-error",
    SyntaxError: "syntax-error",
    RangeError: "range-error",
    URIError: "uri-error",
    EvalError: "eval-error",
    AggregateError: "aggregate-error",
    AbortError: "abort-error",
    SecurityError: "security-error",
    InvalidStateError: "invalid-state-error",
  }
  const pageError =
    typeof name === "string" && Object.prototype.hasOwnProperty.call(known, name)
      ? known[name]
      : undefined
  return { count: boundedCount(errors.length), kind: pageError ?? "other" }
}

export function reportLiveProfileSaveFailure(input: ProfileSaveFailureInput): void {
  try {
    if (!isRecord(input)) return
    const { project, status, body, alertCount, saveDisabled, pathname, pageErrors } = input
    if (
      (project !== "desktop" && project !== "mobile") ||
      typeof status !== "number" ||
      !Number.isInteger(status) ||
      status < 100 ||
      status > 599
    ) {
      return
    }
    const detail = detailSummary(body)
    const alertToken = boundedCount(alertCount)
    const disabledToken: SafeFlag =
      typeof saveDisabled === "boolean" ? (String(saveDisabled) as SafeFlag) : "unknown"
    const pageError = firstPageError(pageErrors)
    const record =
      `UE_LIVE_PROFILE_SAVE_V1 project=${project} status=${status} detail=${detail.kind} ` +
      `detail_count=${detail.count} detail_msg=${detail.message} alert_count=${alertToken} ` +
      `save_disabled=${disabledToken} route=${routeFamily(pathname)} ` +
      `page_error_count=${pageError.count} page_error=${pageError.kind}\n`
    if (emittedRecords.has(record) || emittedRecords.size >= MAX_RECORDS) return
    emittedRecords.add(record)
    try {
      process.stdout.write(record)
    } catch {
      // Diagnostics must not replace the original Playwright assertion.
    }
  } catch {
    // Malformed runtime values are ignored without affecting the scenario.
  }
}
