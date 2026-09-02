import * as Sentry from "@sentry/react"
import { initTelemetry } from "./telemetry"
import { logInfo } from "./logger"

let initialized: boolean | undefined

const MIN_SAMPLE_RATE = 0
const MAX_SAMPLE_RATE = 1

function parseSampleRate(value: string | undefined): number | undefined {
  const parsed = Number.parseFloat(value ?? "NaN")
  if (Number.isNaN(parsed)) return undefined
  if (parsed < MIN_SAMPLE_RATE || parsed > MAX_SAMPLE_RATE) return undefined
  return parsed
}

export function initObservability(env: ImportMetaEnv = import.meta.env): boolean {
  if (initialized === true) return true

  // ── OTel Web SDK ───────────────────────────────────────────────────────────
  // Initialize telemetry unconditionally so that spans are exported in local
  // development and staging environments even when VITE_SENTRY_DSN is not set.
  // initTelemetry is a no-op when VITE_OTEL_EXPORTER_OTLP_ENDPOINT is absent
  // in production (see telemetry.ts), so there is no performance impact for
  // environments that have opted out of tracing entirely.
  initTelemetry(env)

  // Mark as initialized here — not at the end of the function — so that
  // subsequent calls do not re-run initTelemetry() regardless of whether Sentry
  // is configured.  The early guard `if (initialized) return true` at the top
  // already prevents the whole function from running twice.
  initialized = true

  // ── Sentry ─────────────────────────────────────────────────────────────────
  const dsn = env.VITE_SENTRY_DSN
  if (!dsn) {
    return false
  }

  if (env.DEV) {
    if (typeof console !== "undefined") {
      logInfo("Sentry disabled in development mode; skipping initialization")
    }
    return false
  }

  const environment = env.VITE_ENVIRONMENT ?? (env.PROD ? "production" : "development")
  const release = env.VITE_APP_RELEASE ?? env.VITE_RELEASE ?? env.VITE_SENTRY_RELEASE ?? undefined
  const tracesSampleRate = parseSampleRate(env.VITE_SENTRY_TRACES_SAMPLE_RATE)
  const profilesSampleRate = parseSampleRate(env.VITE_SENTRY_PROFILES_SAMPLE_RATE)

  const config = {
    dsn,
    environment,
    enabled: true,
    tracesSampleRate,
    profilesSampleRate,
    ...(release ? { release } : {}),
  }

  Sentry.init(config)

  return true
}

export function resetObservabilityForTesting(): void {
  initialized = undefined
}
