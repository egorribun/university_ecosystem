import * as Sentry from "@sentry/react"

const sentryCaptureException = Sentry.captureException
const sentryCaptureMessage = Sentry.captureMessage
const sentrySetTag = Sentry.setTag

type LogMethod = "error" | "warn" | "info" | "log"

type SentryClient = {
  captureException?: typeof sentryCaptureException
  captureMessage?: typeof sentryCaptureMessage
  setTag?: typeof sentrySetTag
}

let currentTraceId: string | null = null
const defaultSentry = Object.create(null) as SentryClient
defaultSentry.captureException = sentryCaptureException
defaultSentry.captureMessage = sentryCaptureMessage
defaultSentry.setTag = sentrySetTag
let sentry: SentryClient = defaultSentry

export function setLoggerClient(overrides: Partial<SentryClient>): void {
  sentry = { ...sentry, ...overrides }
}

function normalizeArg(value: unknown): unknown {
  if (value instanceof Error) {
    return {
      name: value.name,
      message: value.message,
      stack: value.stack,
    }
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return value
  }
  if (typeof value === "object") {
    try {
      return JSON.parse(JSON.stringify(value))
    } catch {
      return Object.prototype.toString.call(value)
    }
  }
  return String(value)
}

function callConsole(method: LogMethod, args: unknown[]): void {
  // eslint-disable-next-line no-console
  const target = console[method]
  if (typeof target === "function") {
    target(...(args as unknown[]))
  }
}

function findFirstError(args: unknown[]): Error | undefined {
  return args.find((value): value is Error => value instanceof Error)
}

function findFirstMessage(args: unknown[]): string | undefined {
  return args.find((value): value is string => typeof value === "string")
}

function resolveTags() {
  const tags: Record<string, string> = {
    logger: "app",
  }
  if (currentTraceId !== null) {
    tags.trace_id = currentTraceId
  }
  return tags
}

export function setTraceContext(traceId: string | null | undefined): void {
  currentTraceId = traceId && String(traceId).trim() ? String(traceId) : null
  if (typeof sentry.setTag === "function") {
    sentry.setTag("trace_id", currentTraceId ?? "")
  }
}

export function logError(...args: unknown[]): void {
  const error = findFirstError(args)
  try {
    if (error) {
      if (typeof sentry.captureException === "function") {
        sentry.captureException(error, {
          extra: {
            logArgs: args.map(normalizeArg),
          },
          tags: {
            ...resolveTags(),
            level: "error",
          },
        })
      } else if (typeof sentry.captureMessage === "function") {
        const message = findFirstMessage(args)
        if (message) {
          sentry.captureMessage(message, "error")
        }
      }
    } else if (typeof sentry.captureMessage === "function") {
      const message = findFirstMessage(args)
      if (message) {
        sentry.captureMessage(message, "error")
      }
    }
  } catch (sentryError) {
    callConsole("warn", ["[logger] Failed to forward error to Sentry", sentryError])
  }

  callConsole("error", args)
}

export function logWarning(...args: unknown[]): void {
  try {
    const message = findFirstMessage(args)
    if (message && typeof sentry.captureMessage === "function") {
      sentry.captureMessage(message, "warning")
    }
  } catch (sentryError) {
    callConsole("warn", ["[logger] Failed to forward warning to Sentry", sentryError])
  }

  callConsole("warn", args)
}

export function logInfo(...args: unknown[]): void {
  callConsole("info", args)
}

export function logDebug(...args: unknown[]): void {
  if (import.meta.env.DEV) {
    callConsole("log", args)
  }
}
