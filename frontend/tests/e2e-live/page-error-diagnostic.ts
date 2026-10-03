// At most both projects' 6 current-page labels x 12 error types per worker.
const emittedRecords = new Set<string>()
const MAX_RECORDS = 144
const MAX_COUNT = 999

function errorType(error: unknown): string {
  if (typeof error !== "object" || error === null) return "other"
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

function currentPage(pathname: unknown): string {
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
    record(error: unknown, pathname: unknown): void {
      const location = currentPage(pathname)
      const type = errorType(error)
      const key = `${location}:${type}`
      const existing = counts.get(key)
      if (existing) existing.count = Math.min(MAX_COUNT, existing.count + 1)
      else counts.set(key, { currentPage: location, type, count: 1 })
    },
    report(project: string, check: "password-reset"): void {
      if ((project !== "desktop" && project !== "mobile") || check !== "password-reset") return
      for (const { currentPage, type, count } of counts.values()) {
        if (emittedRecords.size >= MAX_RECORDS) return
        const record = `UE_LIVE_PAGE_ERROR_V1 project=${project} check=password-reset page=${currentPage} type=${type} count=${count}\n`
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
