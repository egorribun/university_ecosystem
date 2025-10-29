import type { Metric } from "web-vitals"
import { onCLS, onFCP, onFID, onINP, onLCP, onTTFB } from "web-vitals"

export type WebVitalMetric = Metric
export type WebVitalReporter = (metric: WebVitalMetric) => void

type ExtendedEnv = ImportMetaEnv & {
  VITE_ENABLE_WEB_VITALS?: string
  VITE_WEB_VITALS_ENDPOINT?: string
}

let initialized = false

function isEnabled(value: string | undefined): boolean {
  if (!value) return false
  const normalized = value.trim().toLowerCase()
  return normalized === "true" || normalized === "1" || normalized === "yes"
}

function sendMetric(endpoint: string, metric: WebVitalMetric): void {
  const payload = JSON.stringify({
    name: metric.name,
    value: metric.value,
    delta: metric.delta,
    id: metric.id,
    rating: metric.rating,
    label: metric.label,
    navigationType: metric.navigationType,
  })

  if (
    typeof navigator !== "undefined" &&
    typeof navigator.sendBeacon === "function" &&
    typeof Blob !== "undefined"
  ) {
    try {
      const blob = new Blob([payload], { type: "application/json" })
      navigator.sendBeacon(endpoint, blob)
      return
    } catch (error) {
      // Fallback to fetch below; ignore transport errors
    }
  }

  if (typeof fetch === "function") {
    void fetch(endpoint, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: payload,
      keepalive: true,
      credentials: "omit",
    }).catch(() => {
      // Swallow network errors — observability should not break the app
    })
  }
}

function createReporter(env: ExtendedEnv): WebVitalReporter | undefined {
  const endpoint = env.VITE_WEB_VITALS_ENDPOINT
  if (endpoint) {
    return (metric) => {
      sendMetric(endpoint, metric)
    }
  }

  if (typeof console !== "undefined") {
    return (metric) => {
      console.debug(`[web-vitals] ${metric.name}`, {
        value: metric.value,
        delta: metric.delta,
        rating: metric.rating,
      })
    }
  }

  return undefined
}

export function initWebVitals(env: ExtendedEnv = import.meta.env as ExtendedEnv): boolean {
  if (initialized) {
    return true
  }

  if (env.DEV || env.MODE === "test") {
    return false
  }

  if (!isEnabled(env.VITE_ENABLE_WEB_VITALS)) {
    return false
  }

  if (typeof window === "undefined" || typeof document === "undefined") {
    return false
  }

  const reporter = createReporter(env)
  if (!reporter) {
    return false
  }

  onCLS(reporter)
  onFCP(reporter)
  onFID(reporter)
  onINP(reporter)
  onLCP(reporter)
  onTTFB(reporter)

  initialized = true
  return true
}

export function resetWebVitalsForTesting(): void {
  initialized = false
}
