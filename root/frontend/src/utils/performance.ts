/**
 * Performance timing utilities for measuring and reporting
 * key user experience metrics.
 */

/**
 * Measure the execution time of an async function.
 */
export async function measureAsync<T>(
  name: string,
  fn: () => Promise<T>,
  onComplete?: (durationMs: number) => void
): Promise<T> {
  const start = performance.now()
  try {
    return await fn()
  } finally {
    const duration = performance.now() - start
    if (import.meta.env.DEV) {
      console.debug(`[Perf] ${name}: ${duration.toFixed(2)}ms`)
    }
    onComplete?.(duration)
  }
}

/**
 * Create a performance marker for Navigation Timing API.
 */
export function mark(name: string): void {
  try {
    performance.mark(name)
  } catch {
    // Ignore if not supported
  }
}

/**
 * Measure between two marks and report.
 */
export function measure(name: string, startMark: string, endMark?: string): number {
  try {
    if (endMark) {
      performance.measure(name, startMark, endMark)
    } else {
      performance.measure(name, startMark)
    }
    const entries = performance.getEntriesByName(name, 'measure')
    return entries[entries.length - 1]?.duration ?? 0
  } catch {
    return 0
  }
}

/**
 * Get Web Vitals metrics if available.
 */
export interface WebVitals {
  fcp?: number // First Contentful Paint
  lcp?: number // Largest Contentful Paint
  fid?: number // First Input Delay
  cls?: number // Cumulative Layout Shift
  ttfb?: number // Time to First Byte
}

export function getWebVitals(): WebVitals {
  const vitals: WebVitals = {}

  try {
    // FCP
    const fcpEntries = performance.getEntriesByName('first-contentful-paint')
    if (fcpEntries.length > 0) {
      vitals.fcp = fcpEntries[0].startTime
    }

    // TTFB from navigation timing
    const navEntries = performance.getEntriesByType('navigation') as PerformanceNavigationTiming[]
    if (navEntries.length > 0) {
      vitals.ttfb = navEntries[0].responseStart - navEntries[0].requestStart
    }
  } catch {
    // Metrics not available
  }

  return vitals
}

/**
 * Report performance metrics to analytics/monitoring.
 */
export function reportMetric(name: string, value: number, tags?: Record<string, string>): void {
  // Send to OpenTelemetry if configured
  if (typeof window !== 'undefined' && 'otel' in window) {
    // @ts-expect-error - otel may be injected
    window.otel?.recordMetric?.(name, value, tags)
  }

  // Log in development
  if (import.meta.env.DEV) {
    console.debug(`[Metric] ${name}=${value.toFixed(2)}`, tags ?? '')
  }
}

/**
 * Create a timing decorator for class methods.
 */
export function timed(name?: string) {
  return function <T extends (...args: unknown[]) => Promise<unknown>>(
    target: unknown,
    propertyKey: string,
    descriptor: TypedPropertyDescriptor<T>
  ): TypedPropertyDescriptor<T> {
    const original = descriptor.value!
    const metricName = name ?? propertyKey

    descriptor.value = async function (this: unknown, ...args: Parameters<T>) {
      const start = performance.now()
      try {
        return await original.apply(this, args)
      } finally {
        reportMetric(`timing.${metricName}`, performance.now() - start)
      }
    } as T

    return descriptor
  }
}

/**
 * Simple in-memory metrics aggregator for batch reporting.
 */
class MetricsBuffer {
  private buffer: Array<{ name: string; value: number; timestamp: number }> = []
  private flushInterval: ReturnType<typeof setInterval> | null = null

  start(intervalMs = 30000): void {
    if (this.flushInterval) return
    this.flushInterval = setInterval(() => this.flush(), intervalMs)
  }

  stop(): void {
    if (this.flushInterval) {
      clearInterval(this.flushInterval)
      this.flushInterval = null
    }
  }

  record(name: string, value: number): void {
    this.buffer.push({ name, value, timestamp: Date.now() })
  }

  flush(): void {
    if (this.buffer.length === 0) return

    const metrics = [...this.buffer]
    this.buffer = []

    // Group by name and compute stats
    const grouped = new Map<string, number[]>()
    for (const m of metrics) {
      const arr = grouped.get(m.name) ?? []
      arr.push(m.value)
      grouped.set(m.name, arr)
    }

    for (const [name, values] of grouped) {
      const avg = values.reduce((a, b) => a + b, 0) / values.length
      const max = Math.max(...values)
      reportMetric(`${name}.avg`, avg)
      reportMetric(`${name}.max`, max)
      reportMetric(`${name}.count`, values.length)
    }
  }
}

export const metricsBuffer = new MetricsBuffer()
