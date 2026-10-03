// Bound both projects × four checks × two attempts (CI retries once).
const emittedRecords = new Set<string>()
const MAX_RECORDS = 16

export function reportLiveHttpStatus(
  project: string,
  check: "admin-users" | "admin-feature-flags" | "admin-feature-flags-ui" | "password-reset-replay",
  status: number
): void {
  if (
    (project !== "desktop" && project !== "mobile") ||
    (check !== "admin-users" &&
      check !== "admin-feature-flags" &&
      check !== "admin-feature-flags-ui" &&
      check !== "password-reset-replay") ||
    !Number.isInteger(status) ||
    status < 100 ||
    status > 599 ||
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
