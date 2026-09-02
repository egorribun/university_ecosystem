import { isAxiosError } from "axios"
import { logError, logWarning, logInfo } from "./logger"

type GlobalTarget = Pick<Window & typeof globalThis, "addEventListener" | "removeEventListener">

let initialized = false
let teardown: (() => void) | null = null

const LOGGER_TAGS = {
  source: "global-error-handler",
}

function serializeReason(reason: unknown): unknown {
  if (reason === null) {
    return null
  }
  if (typeof reason === "object") {
    try {
      return JSON.parse(JSON.stringify(reason))
    } catch {
      return Object.assign({}, reason as Record<string, unknown>)
    }
  }
  return reason
}

function handlePromiseRejection(event: PromiseRejectionEvent) {
  const { reason } = event
  if (isAxiosError(reason)) {
    logError("[GlobalErrors] Unhandled Axios error", reason)
    return
  }
  if (reason instanceof Error) {
    logError("[GlobalErrors] Unhandled promise rejection", reason)
    return
  }

  logWarning("[GlobalErrors] Promise rejected with a non-error value", serializeReason(reason))
}

function handleWindowError(event: ErrorEvent) {
  const error = event.error instanceof Error ? event.error : undefined
  if (error) {
    logError("[GlobalErrors] Unhandled error event", error)
    return
  }

  logError("[GlobalErrors] Error event", event.message, {
    filename: event.filename,
    lineno: event.lineno,
    colno: event.colno,
  })
}

export function initGlobalErrorHandlers(target?: GlobalTarget): boolean {
  if (initialized) return true

  const resolvedTarget = target ?? (typeof window !== "undefined" ? window : undefined)
  if (!resolvedTarget) {
    return false
  }

  resolvedTarget.addEventListener("unhandledrejection", handlePromiseRejection)
  resolvedTarget.addEventListener("error", handleWindowError)

  teardown = () => {
    resolvedTarget.removeEventListener("unhandledrejection", handlePromiseRejection)
    resolvedTarget.removeEventListener("error", handleWindowError)
    teardown = null
    initialized = false
  }

  initialized = true
  logInfo("[GlobalErrors] Handlers registered", LOGGER_TAGS)
  return true
}

export function resetGlobalErrorHandlersForTesting(): void {
  teardown?.()
}
