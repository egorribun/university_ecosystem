// Bound both projects × eight checks × two attempts (CI retries once).
const emittedRecords = new Set<string>()
const MAX_RECORDS = 32

export type LiveHttpStatusCheck =
  | "admin-users"
  | "admin-feature-flags"
  | "admin-feature-flags-ui"
  | "password-reset-replay"
  | "auth-login"
  | "auth-session-cap"
  | "auth-logout"
  | "auth-session-preflight"

const LIVE_HTTP_STATUS_CHECKS: ReadonlySet<LiveHttpStatusCheck> = new Set([
  "admin-users",
  "admin-feature-flags",
  "admin-feature-flags-ui",
  "password-reset-replay",
  "auth-login",
  "auth-session-cap",
  "auth-logout",
  "auth-session-preflight",
])

export function reportLiveHttpStatus(
  project: string,
  check: LiveHttpStatusCheck,
  status: number
): void {
  if (
    (project !== "desktop" && project !== "mobile") ||
    !LIVE_HTTP_STATUS_CHECKS.has(check) ||
    !Number.isInteger(status) ||
    status < 100 ||
    status > 599 ||
    (check === "auth-session-cap" && status !== 403) ||
    emittedRecords.size >= MAX_RECORDS
  ) {
    return
  }

  const record = `UE_LIVE_HTTP_STATUS_V1 project=${project} check=${check} status=${status}\n`
  if (emittedRecords.has(record)) return
  emittedRecords.add(record)
  try {
    process.stdout.write(record)
  } catch {
    // Diagnostics must not replace the scenario's hard assertion.
  }
}
