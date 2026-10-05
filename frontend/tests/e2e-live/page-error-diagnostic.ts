// Hard worker-local cap for the fixed cross-project page/error protocol.
const emittedRecords = new Set<string>()
const MAX_RECORDS = 248
const MAX_COUNT = 999

type DiagnosticCheck = "password-reset" | "admin-notifications"

const ADMIN_NOTIFICATIONS_TITLES = new Set([
  "admin can read the seeded notification queue without changing it",
  "student cannot view or mutate notification queue data",
  "teacher cannot view or mutate notification queue data",
])

export function isLiveAdminNotificationsScenario(
  project: unknown,
  file: unknown,
  title: unknown
): boolean {
  if (project !== "desktop" && project !== "mobile") return false
  if (typeof file !== "string") return false
  if (!file.replace(/\\/g, "/").endsWith("/tests/e2e-live/admin-notifications-rbac.live.spec.ts")) {
    return false
  }
  return typeof title === "string" && ADMIN_NOTIFICATIONS_TITLES.has(title)
}

function isReactHydration418(error: object): boolean {
  try {
    const message = (error as { message?: unknown }).message
    return (
      typeof message === "string" &&
      (/^Minified React error #418(?:;|$)/u.test(message) ||
        /^Hydration failed because the server rendered HTML didn't match the client(?:\.|\s)/u.test(
          message
        ))
    )
  } catch {
    // A custom message getter must never mask the original uncaught exception.
    return false
  }
}

function errorType(error: unknown, check: DiagnosticCheck): string {
  if (typeof error !== "object" || error === null) return "other"
  if (check === "admin-notifications" && isReactHydration418(error)) return "react-418"
  try {
    switch ((error as { name?: unknown }).name) {
      case "Error":
        return "error"
      case "TypeError":
        return "type-error"
      case "ReferenceError":
        return "reference-error"
      case "SyntaxError":
        return "syntax-error"
      case "RangeError":
        return "range-error"
      case "URIError":
        return "uri-error"
      case "EvalError":
        return "eval-error"
      case "AggregateError":
        return "aggregate-error"
      case "AbortError":
        return "abort-error"
      case "SecurityError":
        return "security-error"
      case "InvalidStateError":
        return "invalid-state-error"
    }
  } catch {
    // A custom name accessor must never mask the original uncaught exception.
  }
  return "other"
}

function currentPage(pathname: unknown, check: DiagnosticCheck): string {
  if (check === "admin-notifications") {
    switch (pathname) {
      case "/login":
        return "login"
      case "/dashboard":
        return "dashboard"
      case "/admin/notifications":
        return "admin-notifications"
      default:
        return "other"
    }
  }

  switch (pathname) {
    case "/register":
      return "register"
    case "/login":
      return "login"
    case "/forgot-password":
      return "forgot-password"
    case "/reset-password":
      return "reset-password"
    case "/dashboard":
      return "dashboard"
    default:
      return "other"
  }
}

export function createLivePageErrorDiagnostics() {
  // Retain only fixed labels and saturated counts, never input objects or paths.
  const counts = new Map<string, { currentPage: string; type: string; count: number }>()
  return {
    record(error: unknown, pathname: unknown, check: DiagnosticCheck = "password-reset"): void {
      const location = currentPage(pathname, check)
      const type = errorType(error, check)
      const key = `${location}:${type}`
      const existing = counts.get(key)
      if (existing) existing.count = Math.min(MAX_COUNT, existing.count + 1)
      else counts.set(key, { currentPage: location, type, count: 1 })
    },
    report(project: string, check: DiagnosticCheck): void {
      if (
        (project !== "desktop" && project !== "mobile") ||
        (check !== "password-reset" && check !== "admin-notifications")
      )
        return
      for (const { currentPage, type, count } of counts.values()) {
        if (emittedRecords.size >= MAX_RECORDS) return
        const record = `UE_LIVE_PAGE_ERROR_V1 project=${project} check=${check} page=${currentPage} type=${type} count=${count}\n`
        if (emittedRecords.has(record)) continue
        emittedRecords.add(record)
        try {
          process.stdout.write(record)
        } catch {
          return
        }
      }
    },
  }
}
