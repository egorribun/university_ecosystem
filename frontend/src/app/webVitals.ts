import type { Metric } from "web-vitals"
import { onCLS, onFCP, onINP, onLCP, onTTFB } from "web-vitals"
import { logDebug } from "@/app/logger"

type MetricRating = Metric["rating"]

export interface CustomMetric extends Omit<Metric, "name"> {
  name: string
}

export type WebVitalMetric = Metric | CustomMetric
export type WebVitalReporter = (metric: WebVitalMetric) => void

type ExtendedEnv = ImportMetaEnv & {
  VITE_ENABLE_WEB_VITALS?: string
  VITE_WEB_VITALS_ENDPOINT?: string
  VITE_CWV_TRUSTED_RUM?: string
}

let initialized = false
let reporterRef: WebVitalReporter | undefined

const TRUE_VALUES = new Set(["true", "1", "yes"])

function isEnabled(value: string | undefined): boolean {
  if (!value) return false
  const normalized = value.trim().toLowerCase()
  return TRUE_VALUES.has(normalized)
}

function hasLabel(metric: WebVitalMetric): metric is WebVitalMetric & { label: string } {
  return typeof (metric as { label?: unknown }).label === "string"
}

function sendMetric(endpoint: string, metric: WebVitalMetric): void {
  const payloadObject: Record<string, unknown> = {
    name: metric.name,
    value: metric.value,
    delta: metric.delta,
    id: metric.id,
    rating: metric.rating,
    navigationType: metric.navigationType,
  }

  if (hasLabel(metric)) {
    payloadObject.label = metric.label
  }

  const payload = JSON.stringify(payloadObject)

  if (
    typeof navigator !== "undefined" &&
    typeof navigator.sendBeacon === "function" &&
    typeof Blob !== "undefined"
  ) {
    try {
      const blob = new Blob([payload], { type: "application/json" })
      navigator.sendBeacon(endpoint, blob)
      return
    } catch (_error) {
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

const CERTIFICATION_METRICS = new Set(["LCP", "INP", "CLS"])

function trustedRequestHeaders(): Record<string, string> {
  const headers: Record<string, string> = { "Content-Type": "application/json" }
  const csrfCookie = document.cookie
    .split(";")
    .map((part) => part.trim())
    .find((part) => part.startsWith("csrf_token="))
  if (csrfCookie) {
    const encodedToken = csrfCookie.slice("csrf_token=".length)
    try {
      headers["X-CSRF-Token"] = decodeURIComponent(encodedToken)
    } catch {
      return headers
    }
  }
  return headers
}

function isSameOriginEndpoint(endpoint: string): boolean {
  try {
    return new URL(endpoint, window.location.origin).origin === window.location.origin
  } catch {
    return false
  }
}

function createTrustedReporter(endpoint: string): WebVitalReporter | undefined {
  if (!isSameOriginEndpoint(endpoint) || typeof fetch !== "function") return undefined
  const base = endpoint.replace(/\/+$/, "")
  type EnvelopeState = {
    envelope: string
    expiresAt: number
    navigationKey: string
  }
  let cachedEnvelope: EnvelopeState | undefined
  let envelopeRequest: { navigationKey: string; promise: Promise<EnvelopeState> } | undefined
  // web-vitals callbacks describe the current document lifecycle. Pin the
  // initial route/device so a soft navigation cannot relabel lifetime CLS/INP.
  const pathname = window.location.pathname
  const deviceClass = window.matchMedia("(max-width: 767px)").matches ? "mobile" : "desktop"
  const navigationKey = `${deviceClass}:${pathname}`

  const getEnvelope = (): Promise<EnvelopeState> => {
    if (
      cachedEnvelope?.navigationKey === navigationKey &&
      cachedEnvelope.expiresAt > Date.now() + 30_000
    ) {
      return Promise.resolve(cachedEnvelope)
    }
    if (envelopeRequest?.navigationKey === navigationKey) {
      return envelopeRequest.promise
    }
    if (envelopeRequest) {
      return envelopeRequest.promise.then(getEnvelope, getEnvelope)
    }
    const renewalEnvelope =
      cachedEnvelope?.navigationKey === navigationKey ? cachedEnvelope.envelope : undefined
    const body: Record<string, string> = {
      pathname,
      device_class: deviceClass,
    }
    if (renewalEnvelope) body.renewal_envelope = renewalEnvelope
    const pending = fetch(`${base}/envelope`, {
      method: "POST",
      headers: trustedRequestHeaders(),
      credentials: "include",
      body: JSON.stringify(body),
    }).then(async (response) => {
      if (!response.ok) throw new Error("CWV envelope rejected")
      const responseBody = (await response.json()) as {
        envelope?: unknown
        expires_at?: unknown
      }
      const expiresAt =
        typeof responseBody.expires_at === "string"
          ? Date.parse(responseBody.expires_at)
          : Number.NaN
      if (
        typeof responseBody.envelope !== "string" ||
        !Number.isFinite(expiresAt) ||
        expiresAt <= Date.now()
      ) {
        throw new Error("CWV envelope malformed")
      }
      cachedEnvelope = {
        envelope: responseBody.envelope,
        expiresAt,
        navigationKey,
      }
      return cachedEnvelope
    })
    envelopeRequest = { navigationKey, promise: pending }
    const clearPending = () => {
      if (envelopeRequest?.promise === pending) envelopeRequest = undefined
    }
    void pending.then(clearPending, clearPending)
    return pending
  }
  // A rejected envelope intentionally disables this navigation's collection.
  void getEnvelope().catch(() => undefined)
  return (metric) => {
    if (!CERTIFICATION_METRICS.has(metric.name)) return
    void getEnvelope()
      .then(({ envelope }) =>
        fetch(`${base}/observations`, {
          method: "POST",
          headers: trustedRequestHeaders(),
          credentials: "include",
          keepalive: true,
          body: JSON.stringify({ envelope, metric: metric.name, value: metric.value }),
        })
      )
      .catch(() => {
        // Performance collection is strictly non-blocking for the product UI.
      })
  }
}

function createReporter(env: ExtendedEnv): WebVitalReporter | undefined {
  const endpoint = env.VITE_WEB_VITALS_ENDPOINT
  if (isEnabled(env.VITE_CWV_TRUSTED_RUM)) {
    return endpoint ? createTrustedReporter(endpoint) : undefined
  }
  if (endpoint) {
    return (metric) => {
      sendMetric(endpoint, metric)
    }
  }

  if (typeof console !== "undefined") {
    return (metric) => {
      logDebug(`[web-vitals] ${metric.name}`, {
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
  onINP(reporter)
  onLCP(reporter)
  onTTFB(reporter)

  reporterRef = reporter
  initialized = true
  return true
}

export function resetWebVitalsForTesting(): void {
  initialized = false
  reporterRef = undefined
}

function resolveRating(
  value: number,
  [goodThreshold, needsImprovementThreshold]: [number, number]
): MetricRating {
  if (value <= goodThreshold) {
    return "good"
  }

  if (value <= needsImprovementThreshold) {
    return "needs-improvement"
  }

  return "poor"
}

function resolveNavigationType(): WebVitalMetric["navigationType"] {
  if (typeof performance === "undefined" || typeof performance.getEntriesByType !== "function") {
    return "navigate"
  }

  const navigationEntry = performance.getEntriesByType("navigation")[0] as
    PerformanceNavigationTiming | undefined
  if (!navigationEntry || !navigationEntry.type) {
    return "navigate"
  }

  if (navigationEntry.type === "back_forward") {
    return "back-forward"
  }

  return navigationEntry.type as WebVitalMetric["navigationType"]
}

function createCustomMetric(
  name: string,
  value: number,
  thresholds: [number, number]
): CustomMetric {
  return {
    name,
    value,
    delta: value,
    rating: resolveRating(value, thresholds),
    id: `${name}-${Date.now()}`,
    entries: [],
    navigationType: resolveNavigationType(),
    navigationId: 0,
  }
}

const BOOTSTRAP_TTI_THRESHOLDS: [number, number] = [3800, 7300]

export function reportBootstrapTTI(duration: number): boolean {
  if (!reporterRef) {
    return false
  }

  const metric = createCustomMetric("APP_TTI", duration, BOOTSTRAP_TTI_THRESHOLDS)
  reporterRef(metric)
  return true
}
