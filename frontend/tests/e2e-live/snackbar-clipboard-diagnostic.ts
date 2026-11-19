import type { Locator, Page } from "@playwright/test"

const emittedRecords = new Set<string>()

function flag(value: unknown): string {
  return typeof value === "boolean" ? String(value) : "unknown"
}

function count(value: unknown): string {
  return typeof value === "number" && Number.isSafeInteger(value) && value >= 0
    ? String(Math.min(value, 999))
    : "unknown"
}

function permission(value: unknown): string {
  return value === "granted" || value === "denied" || value === "prompt" ? value : "unavailable"
}

export function reportSnackbarClipboardFailure(input: unknown): void {
  try {
    if (typeof input !== "object" || input === null) return
    const record = input as Record<string, unknown>
    const { project } = record
    if (project !== "desktop" && project !== "mobile") return
    const line =
      `UE_LIVE_SNACKBAR_CLIPBOARD_V1 project=${project} permission=${permission(record.permission)} ` +
      `secure=${flag(record.secure)} focused=${flag(record.focused)} ` +
      `clipboard=${flag(record.clipboard)} hydrated=${flag(record.hydrated)} ` +
      `enabled=${flag(record.enabled)} alerts=${count(record.alerts)}\n`
    if (emittedRecords.size >= 4 || emittedRecords.has(line)) return
    emittedRecords.add(line)
    process.stdout.write(line)
  } catch {
    // No diagnostics error may replace the original acceptance assertion.
  }
}

async function bounded<T>(observe: () => Promise<T>): Promise<T | undefined> {
  let timer: ReturnType<typeof setTimeout> | undefined
  try {
    return await Promise.race([
      Promise.resolve().then(observe),
      new Promise<undefined>((resolve) => {
        // This is the Node runner clock, independent of page.clock.
        timer = setTimeout(() => resolve(undefined), 750)
      }),
    ])
  } catch {
    return undefined
  } finally {
    clearTimeout(timer)
  }
}

export async function sampleSnackbarClipboardFailure(
  page: Page,
  button: Locator,
  alert: Locator,
  project: string
): Promise<void> {
  try {
    const [state, permissionState, enabled, alerts] = await Promise.all([
      bounded(() =>
        page.evaluate(() => ({
          secure: window.isSecureContext,
          focused: document.hasFocus(),
          clipboard: typeof navigator.clipboard?.writeText === "function",
          hydrated: window.__APP_HYDRATED === true,
        }))
      ),
      bounded(() =>
        page.evaluate(async () => {
          try {
            const status = await navigator.permissions.query({
              name: "clipboard-write" as PermissionName,
            })
            return status.state
          } catch {
            return "unavailable"
          }
        })
      ),
      bounded(() => button.isEnabled({ timeout: 500 })),
      bounded(() => alert.count()),
    ])
    reportSnackbarClipboardFailure({
      project,
      secure: state?.secure,
      focused: state?.focused,
      clipboard: state?.clipboard,
      hydrated: state?.hydrated,
      permission: permissionState,
      enabled,
      alerts,
    })
  } catch {
    // Page closure and malformed runtime observations remain diagnostic-only.
  }
}
