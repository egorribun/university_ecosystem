import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

const loggerMocks = vi.hoisted(() => ({ logDebug: vi.fn() }))
vi.mock("@/app/logger", () => ({ logDebug: loggerMocks.logDebug }))

import {
  getWebVitals,
  mark,
  measure,
  measureAsync,
  metricsBuffer,
  reportMetric,
  timed,
} from "../performance"

type Buffer = typeof metricsBuffer
const createBuffer = (): Buffer => new (metricsBuffer.constructor as new () => Buffer)()

function installOtel() {
  const recordMetric = vi.fn()
  vi.stubGlobal("otel", { recordMetric })
  return recordMetric
}

describe("performance utilities", () => {
  beforeEach(() => {
    loggerMocks.logDebug.mockReset()
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
    vi.unstubAllEnvs()
    vi.restoreAllMocks()
  })

  describe("measureAsync", () => {
    it("reports the elapsed duration and logs it in development", async () => {
      vi.spyOn(performance, "now").mockReturnValueOnce(100).mockReturnValueOnce(130.456)
      const onComplete = vi.fn()

      await expect(measureAsync("load", async () => "value", onComplete)).resolves.toBe("value")

      expect(onComplete).toHaveBeenCalledWith(expect.closeTo(30.456, 6))
      expect(loggerMocks.logDebug).toHaveBeenCalledExactlyOnceWith("[Perf] load: 30.46ms")
    })

    it("stays silent in production", async () => {
      vi.stubEnv("DEV", false)
      const onComplete = vi.fn()

      await measureAsync("load", async () => 1, onComplete)

      expect(onComplete).toHaveBeenCalledOnce()
      expect(loggerMocks.logDebug).not.toHaveBeenCalled()
    })
  })

  describe("mark", () => {
    it("forwards the marker name to the Performance API", () => {
      const markSpy = vi.spyOn(performance, "mark").mockImplementation(() => undefined as never)

      mark("route-start")

      expect(markSpy).toHaveBeenCalledExactlyOnceWith("route-start")
    })
  })

  describe("measure", () => {
    it("passes the end mark only when one is supplied", () => {
      const measureSpy = vi
        .spyOn(performance, "measure")
        .mockImplementation(() => undefined as never)
      vi.spyOn(performance, "getEntriesByName").mockReturnValue([])

      measure("with-end", "a", "b")
      measure("open-ended", "a")

      expect(measureSpy.mock.calls).toStrictEqual([
        ["with-end", "a", "b"],
        ["open-ended", "a"],
      ])
    })

    it("returns the duration of the latest measure entry with that name", () => {
      vi.spyOn(performance, "measure").mockImplementation(() => undefined as never)
      vi.spyOn(performance, "getEntriesByName").mockImplementation((name, type) =>
        name === "render" && type === "measure"
          ? ([{ duration: 5 }, { duration: 7.5 }] as PerformanceEntry[])
          : []
      )

      expect(measure("render", "a", "b")).toBe(7.5)
    })
  })

  describe("getWebVitals", () => {
    it("reads FCP from the named paint entry", () => {
      vi.spyOn(performance, "getEntriesByName").mockImplementation((name) =>
        name === "first-contentful-paint" ? ([{ startTime: 80 }] as PerformanceEntry[]) : []
      )
      vi.spyOn(performance, "getEntriesByType").mockReturnValue([])

      expect(getWebVitals()).toStrictEqual({ fcp: 80 })
    })

    it("still computes TTFB when no paint entry exists", () => {
      vi.spyOn(performance, "getEntriesByName").mockReturnValue([])
      vi.spyOn(performance, "getEntriesByType").mockImplementation((type) =>
        type === "navigation"
          ? ([{ responseStart: 100, requestStart: 40 }] as unknown as ReturnType<
              typeof performance.getEntriesByType
            >)
          : []
      )

      expect(getWebVitals()).toStrictEqual({ ttfb: 60 })
    })
  })

  describe("reportMetric", () => {
    it("forwards to OpenTelemetry and logs with tags in development", () => {
      const recordMetric = installOtel()

      reportMetric("api.latency", 1.5, { route: "news" })

      expect(recordMetric).toHaveBeenCalledExactlyOnceWith("api.latency", 1.5, { route: "news" })
      expect(loggerMocks.logDebug).toHaveBeenCalledExactlyOnceWith("[Metric] api.latency=1.50", {
        route: "news",
      })
    })

    it("logs an empty tag placeholder when no tags are given", () => {
      reportMetric("api.latency", 2)

      expect(loggerMocks.logDebug).toHaveBeenCalledExactlyOnceWith("[Metric] api.latency=2.00", "")
    })

    it("does not log in production", () => {
      vi.stubEnv("DEV", false)

      reportMetric("api.latency", 2)

      expect(loggerMocks.logDebug).not.toHaveBeenCalled()
    })

    it("tolerates an absent window during server rendering", () => {
      vi.stubGlobal("window", undefined)

      expect(() => reportMetric("ssr.metric", 1)).not.toThrow()
    })

    it("tolerates a declared but empty OpenTelemetry bridge", () => {
      vi.stubGlobal("otel", undefined)
      expect(() => reportMetric("otel.missing", 1)).not.toThrow()

      vi.stubGlobal("otel", {})
      expect(() => reportMetric("otel.partial", 1)).not.toThrow()
    })
  })

  describe("timed", () => {
    it("reports under the explicit name, falling back to the method name", async () => {
      const recordMetric = installOtel()
      vi.spyOn(performance, "now").mockReturnValue(10)

      const named = timed("explicit")({}, "method", { value: async () => "a" })
      const unnamed = timed()({}, "method", { value: async () => "b" })

      await expect(named.value!()).resolves.toBe("a")
      await expect(unnamed.value!()).resolves.toBe("b")

      expect(recordMetric.mock.calls.map(([name]) => name)).toStrictEqual([
        "timing.explicit",
        "timing.method",
      ])
    })
  })

  describe("metricsBuffer", () => {
    it("reports nothing when a fresh buffer is flushed", () => {
      const recordMetric = installOtel()

      createBuffer().flush()

      expect(recordMetric).not.toHaveBeenCalled()
    })

    it("aggregates recorded values per metric name", () => {
      const recordMetric = installOtel()
      const buffer = createBuffer()

      buffer.record("latency", 40)
      buffer.record("errors", 3)
      buffer.record("latency", 60)
      buffer.flush()

      expect(recordMetric.mock.calls).toStrictEqual([
        ["latency.avg", 50, undefined],
        ["latency.max", 60, undefined],
        ["latency.count", 2, undefined],
        ["errors.avg", 3, undefined],
        ["errors.max", 3, undefined],
        ["errors.count", 1, undefined],
      ])
    })

    it("empties the buffer after each flush", () => {
      const recordMetric = installOtel()
      const buffer = createBuffer()

      buffer.record("latency", 10)
      buffer.flush()
      recordMetric.mockClear()
      buffer.flush()

      expect(recordMetric).not.toHaveBeenCalled()
    })

    it("flushes on its interval until stopped", () => {
      vi.useFakeTimers()
      const recordMetric = installOtel()
      const buffer = createBuffer()

      buffer.start(100)
      buffer.record("latency", 10)
      vi.advanceTimersByTime(100)
      expect(recordMetric).toHaveBeenCalledWith("latency.count", 1, undefined)

      recordMetric.mockClear()
      buffer.stop()
      buffer.record("latency", 20)
      vi.advanceTimersByTime(1_000)
      expect(recordMetric).not.toHaveBeenCalled()
    })

    it("keeps a single interval when started twice", () => {
      vi.useFakeTimers()
      const recordMetric = installOtel()
      const buffer = createBuffer()

      buffer.start(100)
      buffer.start(100)
      buffer.stop()
      buffer.record("latency", 10)
      vi.advanceTimersByTime(1_000)

      expect(recordMetric).not.toHaveBeenCalled()
    })
  })
})
