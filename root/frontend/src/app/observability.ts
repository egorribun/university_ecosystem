import * as Sentry from "@sentry/react"

let initialized = false

function parseSampleRate(value: string | undefined): number | undefined {
  if (!value) return undefined
  const parsed = Number.parseFloat(value)
  if (Number.isNaN(parsed)) return undefined
  if (parsed < 0 || parsed > 1) return undefined
  return parsed
}

export function initObservability(env: ImportMetaEnv = import.meta.env): boolean {
  if (initialized) return true

  const dsn = env.VITE_SENTRY_DSN
  if (!dsn) {
    return false
  }

  if (env.DEV) {
    if (typeof console !== "undefined") {
      console.info("Sentry disabled in development mode; skipping initialization")
    }
    return false
  }

  const environment = env.VITE_ENVIRONMENT ?? (env.PROD ? "production" : "development")
  const tracesSampleRate = parseSampleRate(env.VITE_SENTRY_TRACES_SAMPLE_RATE)
  const profilesSampleRate = parseSampleRate(env.VITE_SENTRY_PROFILES_SAMPLE_RATE)

  Sentry.init({
    dsn,
    environment,
    enabled: true,
    tracesSampleRate,
    profilesSampleRate,
  })

  initialized = true
  return true
}

export function resetObservabilityForTesting(): void {
  initialized = false
}
