// Record caps bound protocol output; they are not expected live-case totals.
const emittedRecords = new Set<string>()
const emittedDetailRecords = new Set<string>()
const MAX_RECORDS = 534
const MAX_DETAIL_RECORDS = 156
const MAX_COUNT = 999
const MAX_STACK_CHARS = 8192
const MAX_STACK_FRAMES = 24

type DiagnosticCheck =
  "password-reset" | "admin-notifications" | "auth-roles" | "map-gesture" | "schedule-grid-keyboard"
type DiagnosticSource =
  "map-worker" | "map-shared" | "map-bundle" | "schedule-bundle" | "remote-script" | "unknown"
type SourceLocation = { source: DiagnosticSource; line: number; column: number }

const UNKNOWN_SOURCE_LOCATION: SourceLocation = { source: "unknown", line: 0, column: 0 }
const STACK_SOURCE_LOCATION =
  /((?:https?:\/\/|file:\/\/|\/|<anonymous>)[^\s(),]*?):([1-9][0-9]{0,5}):([1-9][0-9]{0,5})(?=$|[\s),])/gu

const AUTH_ROLE_DENIAL_TITLES = new Set([
  "student is denied access to admin pages, user listing, and feature flags",
  "teacher is denied access to admin pages, user listing, and feature flags",
])

const MAP_GESTURE_TITLES = new Set([
  "live map captures wheel zoom without page scroll or center drift",
  "live map leaves page scrolling available outside the map",
  "live mobile map keeps pinch and one-finger pan inside the map",
])
const SCHEDULE_GRID_KEYBOARD_TITLE =
  "Enter opens the lesson in the keyboard-selected schedule grid cell"

const ADMIN_NOTIFICATIONS_TITLES = new Set([
  "admin can read the seeded notification queue without changing it",
  "student cannot view or mutate notification queue data",
  "teacher cannot view or mutate notification queue data",
])

export function isLiveMapGestureScenario(project: unknown, file: unknown, title: unknown): boolean {
  if (project !== "desktop" && project !== "mobile") return false
  if (typeof file !== "string") return false
  if (!file.replace(/\\/g, "/").endsWith("/tests/e2e-live/map-gesture-isolation.live.spec.ts")) {
    return false
  }
  return typeof title === "string" && MAP_GESTURE_TITLES.has(title)
}

export function isLiveScheduleGridKeyboardScenario(
  project: unknown,
  file: unknown,
  title: unknown
): boolean {
  if (project !== "desktop") return false
  if (typeof file !== "string") return false
  if (!file.replace(/\\/g, "/").endsWith("/tests/e2e-live/schedule-grid-keyboard.live.spec.ts")) {
    return false
  }
  return title === SCHEDULE_GRID_KEYBOARD_TITLE
}

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

export function isLiveAuthRoleDenialScenario(
  project: unknown,
  file: unknown,
  title: unknown
): boolean {
  if (project !== "desktop" && project !== "mobile") return false
  if (typeof file !== "string") return false
  if (!file.replace(/\\/g, "/").endsWith("/tests/e2e-live/auth-roles.live.spec.ts")) {
    return false
  }
  return typeof title === "string" && AUTH_ROLE_DENIAL_TITLES.has(title)
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
  if (check !== "password-reset" && isReactHydration418(error)) return "react-418"
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

function generatedSourceBucket(source: string, check: DiagnosticCheck): DiagnosticSource | null {
  const queryOrFragment = source.search(/[?#]/u)
  const sourcePath = queryOrFragment === -1 ? source : source.slice(0, queryOrFragment)
  if (check === "map-gesture") {
    if (/(?:^|\/)maplibre-gl-worker-[A-Za-z0-9_-]+\.mjs$/u.test(sourcePath)) return "map-worker"
    if (/(?:^|\/)maplibre-gl-shared\.mjs$/u.test(sourcePath)) return "map-shared"
    if (/(?:^|\/)assets\/[^/]+\.(?:mjs|js)$/u.test(sourcePath)) return "map-bundle"
  }
  if (check === "schedule-grid-keyboard") {
    if (/(?:^|\/)assets\/[^/]+\.(?:mjs|js)$/u.test(sourcePath)) return "schedule-bundle"
  }
  if (/^https?:\/\//u.test(sourcePath)) return "remote-script"
  return null
}

function generatedSourceLocation(error: unknown, check: DiagnosticCheck): SourceLocation {
  if (check !== "map-gesture" && check !== "schedule-grid-keyboard") {
    return UNKNOWN_SOURCE_LOCATION
  }

  let stack: unknown
  try {
    stack = (error as { stack?: unknown } | null)?.stack
  } catch {
    return UNKNOWN_SOURCE_LOCATION
  }
  if (typeof stack !== "string") return UNKNOWN_SOURCE_LOCATION

  const frames = stack
    .slice(0, MAX_STACK_CHARS)
    .split(/\r?\n/u)
    .slice(1, MAX_STACK_FRAMES + 1)
  for (const frame of frames) {
    STACK_SOURCE_LOCATION.lastIndex = 0
    for (const match of frame.matchAll(STACK_SOURCE_LOCATION)) {
      const source = match[1]
      if (typeof source !== "string") continue
      const bucket = generatedSourceBucket(source, check)
      if (!bucket) continue

      const line = Number(match[2])
      const column = Number(match[3])
      if (!Number.isSafeInteger(line) || !Number.isSafeInteger(column)) continue
      if (line > 999999 || column > 999999) continue
      return { source: bucket, line, column }
    }
  }
  return UNKNOWN_SOURCE_LOCATION
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

  if (check === "auth-roles") {
    switch (pathname) {
      case "/login":
        return "login"
      case "/dashboard":
        return "dashboard"
      case "/admin/users":
        return "admin-users"
      case "/admin/feature-flags":
        return "admin-feature-flags"
      default:
        return "other"
    }
  }

  if (check === "map-gesture") {
    switch (pathname) {
      case "/login":
        return "login"
      case "/map":
        return "map"
      default:
        return "other"
    }
  }

  if (check === "schedule-grid-keyboard") {
    switch (pathname) {
      case "/login":
        return "login"
      case "/schedule":
        return "schedule"
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
  const counts = new Map<
    string,
    {
      check: DiagnosticCheck
      currentPage: string
      type: string
      count: number
      sourceLocation: SourceLocation
    }
  >()
  return {
    record(error: unknown, pathname: unknown, check: DiagnosticCheck = "password-reset"): void {
      if (
        check !== "password-reset" &&
        check !== "admin-notifications" &&
        check !== "auth-roles" &&
        check !== "map-gesture" &&
        check !== "schedule-grid-keyboard"
      ) {
        return
      }
      const location = currentPage(pathname, check)
      const type = errorType(error, check)
      const key = `${check}:${location}:${type}`
      const sourceLocation = generatedSourceLocation(error, check)
      const existing = counts.get(key)
      if (existing) {
        existing.count = Math.min(MAX_COUNT, existing.count + 1)
        if (existing.sourceLocation.source === "unknown" && sourceLocation.source !== "unknown") {
          existing.sourceLocation = sourceLocation
        }
      } else {
        counts.set(key, { check, currentPage: location, type, count: 1, sourceLocation })
      }
    },
    report(project: string, check: DiagnosticCheck): void {
      if (
        (project !== "desktop" && project !== "mobile") ||
        (check !== "password-reset" &&
          check !== "admin-notifications" &&
          check !== "auth-roles" &&
          check !== "map-gesture" &&
          check !== "schedule-grid-keyboard")
      )
        return
      for (const {
        check: recordCheck,
        currentPage,
        type,
        count,
        sourceLocation,
      } of counts.values()) {
        if (recordCheck !== check) continue
        const record = `UE_LIVE_PAGE_ERROR_V1 project=${project} check=${check} page=${currentPage} type=${type} count=${count}\n`
        if (!emittedRecords.has(record) && emittedRecords.size < MAX_RECORDS) {
          emittedRecords.add(record)
          try {
            process.stdout.write(record)
          } catch {
            return
          }
        }

        if (check !== "map-gesture" && check !== "schedule-grid-keyboard") continue
        const detailRecord =
          `UE_LIVE_PAGE_ERROR_DETAIL_V1 project=${project} check=${check} ` +
          `page=${currentPage} type=${type} source=${sourceLocation.source} ` +
          `line=${sourceLocation.line} column=${sourceLocation.column} count=${count}\n`
        if (emittedDetailRecords.has(detailRecord)) continue
        if (emittedDetailRecords.size >= MAX_DETAIL_RECORDS) return
        emittedDetailRecords.add(detailRecord)
        try {
          process.stdout.write(detailRecord)
        } catch {
          return
        }
      }
    },
  }
}
