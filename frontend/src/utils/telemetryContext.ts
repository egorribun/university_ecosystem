import { context, type Context } from "@opentelemetry/api"

export interface CapturedTelemetryContext {
  /**
   * Re-enter the captured context while synchronously starting an operation.
   * The operation may return a Promise, but callers must invoke `run` again
   * after each await before starting another traced operation.
   */
  run<T>(operation: () => T): T
}

export function captureActiveTelemetryContext(): CapturedTelemetryContext {
  const capturedContext: Context = context.active()
  return {
    run<T>(operation: () => T): T {
      return context.with(capturedContext, operation)
    },
  }
}
