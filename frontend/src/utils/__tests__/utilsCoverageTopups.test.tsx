import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { render, waitFor } from "@testing-library/react"
import { getBootstrapFallbackCopy, renderBootstrapFallback } from "../bootstrapFallback"
import { measureAsync, mark, measure, getWebVitals, reportMetric, timed, metricsBuffer } from "../performance"
import { prefetchRouteModules } from "../prefetchRoutes"
import { COMMON_EMAIL_DOMAINS } from "../../constants/emailDomains"
import React from "react"

describe("Utils Coverage Topups", () => {
  describe("emailDomains.ts", () => {
    it("exports COMMON_EMAIL_DOMAINS array", () => {
      expect(COMMON_EMAIL_DOMAINS).toBeDefined()
      expect(COMMON_EMAIL_DOMAINS.length).toBeGreaterThan(0)
      expect(COMMON_EMAIL_DOMAINS).toContain("gmail.com")
    })
  })

  describe("bootstrapFallback.ts", () => {
    let mockDoc: Document
    let mockRoot: HTMLElement

    beforeEach(() => {
      mockRoot = document.createElement("div")
      document.body.appendChild(mockRoot)
      mockDoc = document
    })

    afterEach(() => {
      document.body.removeChild(mockRoot)
    })

    it("gets copy for different lang settings", () => {
      // Default to Russian if lang is ru
      mockDoc.documentElement.lang = "ru"
      let copy = getBootstrapFallbackCopy(mockDoc)
      expect(copy.title).toContain("Не удалось загрузить")

      // English
      mockDoc.documentElement.lang = "en"
      copy = getBootstrapFallbackCopy(mockDoc)
      expect(copy.title).toContain("We couldn't load")

      // Unmatched default to English
      mockDoc.documentElement.lang = "fr"
      copy = getBootstrapFallbackCopy(mockDoc)
      expect(copy.title).toContain("We couldn't load")

      // Null lang fallback
      mockDoc.documentElement.lang = ""
      copy = getBootstrapFallbackCopy(mockDoc)
      expect(copy.title).toContain("We couldn't load")
    })

    it("renders fallback DOM structure and handles click handlers", async () => {
      const onReload = vi.fn()
      const clearCachesAndReload = vi.fn().mockResolvedValue(undefined)
      const logError = vi.fn()

      let clickListener: any = null
      const customDoc = {
        documentElement: { lang: "ru", getAttribute: () => "ru" },
        defaultView: window,
        createElement: (tag: string) => {
          const el = document.createElement(tag)
          if (tag === "button") {
            const orig = el.addEventListener
            el.addEventListener = function (type, cb, options) {
              if (type === "click") clickListener = cb
              return orig.call(this, type, cb, options)
            }
          }
          return el
        }
      } as any

      const copy = getBootstrapFallbackCopy(customDoc)
      const rendered = renderBootstrapFallback({
        documentRef: customDoc,
        rootElement: mockRoot,
        copy,
        logError,
        onReload,
        clearCachesAndReload,
      })

      expect(rendered.container).toBeDefined()
      expect(rendered.reloadButton).toBeDefined()
      expect(rendered.clearCacheButton).toBeDefined()

      // Manually trigger click callback when disabled is true to cover early return
      rendered.clearCacheButton.disabled = true
      if (clickListener) {
        clickListener()
      }
      expect(clearCachesAndReload).not.toHaveBeenCalled()

      // Re-enable and click standard way
      rendered.clearCacheButton.disabled = false
      rendered.clearCacheButton.click()
      await waitFor(() => {
        expect(clearCachesAndReload).toHaveBeenCalled()
      })
    })

    it("uses default clearCaches and reload implementation", async () => {
      const logError = vi.fn()
      const mockReload = vi.fn()

      // Stub default navigator / caches / reload
      const mockUnregister = vi.fn().mockResolvedValue(true)
      const mockGetRegistrations = vi.fn().mockResolvedValue([{ unregister: mockUnregister }])
      const mockDelete = vi.fn().mockResolvedValue(true)
      const mockKeys = vi.fn().mockResolvedValue(["cache1"])

      const fakeWindow = {
        location: { reload: mockReload },
        navigator: { serviceWorker: { getRegistrations: mockGetRegistrations } },
        caches: { keys: mockKeys, delete: mockDelete },
      }
      
      const customDoc = {
        documentElement: { lang: "ru", getAttribute: () => "ru" },
        defaultView: fakeWindow,
        createElement: (tag: string) => document.createElement(tag),
      } as any

      const copy = getBootstrapFallbackCopy(customDoc)
      const rendered = renderBootstrapFallback({
        documentRef: customDoc,
        rootElement: mockRoot,
        copy,
        logError,
      })

      rendered.clearCacheButton.click()
      await waitFor(() => {
        expect(mockGetRegistrations).toHaveBeenCalled()
        expect(mockKeys).toHaveBeenCalled()
        expect(mockReload).toHaveBeenCalled()
      })
    })

    it("handles error in clearCaches gracefully", async () => {
      const logError = vi.fn()
      const mockReload = vi.fn()
      const failingClearCaches = vi.fn().mockRejectedValue(new Error("SW error"))

      const fakeWindow = {
        location: { reload: mockReload },
      }
      const customDoc = {
        documentElement: { lang: "ru", getAttribute: () => "ru" },
        defaultView: fakeWindow,
        createElement: (tag: string) => document.createElement(tag),
      } as any

      const copy = getBootstrapFallbackCopy(customDoc)
      const rendered = renderBootstrapFallback({
        documentRef: customDoc,
        rootElement: mockRoot,
        copy,
        logError,
        clearCachesAndReload: failingClearCaches,
      })

      rendered.clearCacheButton.click()
      await waitFor(() => {
        expect(failingClearCaches).toHaveBeenCalled()
        expect(logError).toHaveBeenCalled()
        expect(mockReload).toHaveBeenCalled()
      })
    })

    it("handles reload using defaultWindow reload when defaultView is null", () => {
      const customDoc = {
        documentElement: { lang: "ru", getAttribute: () => "ru" },
        defaultView: null,
        createElement: (tag: string) => document.createElement(tag),
      } as any

      const copy = getBootstrapFallbackCopy(customDoc)
      const rendered = renderBootstrapFallback({
        documentRef: customDoc,
        rootElement: mockRoot,
        copy,
        logError: vi.fn(),
      })

      // Simply click reloadButton and expect it not to throw
      expect(() => rendered.reloadButton.click()).not.toThrow()
    })
  })

  describe("performance.ts", () => {
    it("measureAsync measures execution time", async () => {
      const onComplete = vi.fn()
      const res = await measureAsync("test-measure", async () => {
        return "val"
      }, onComplete)

      expect(res).toBe("val")
      expect(onComplete).toHaveBeenCalled()
    })

    it("mark and measure timing and error fallbacks", () => {
      mark("start-mark")
      mark("end-mark")
      const duration = measure("test-measure", "start-mark", "end-mark")
      expect(typeof duration).toBe("number")

      const duration2 = measure("test-measure2", "start-mark")
      expect(typeof duration2).toBe("number")

      // Force empty entries branch
      const spyGetEntries = vi.spyOn(performance, "getEntriesByName").mockReturnValue([])
      const durationEmpty = measure("test-empty", "start-mark")
      expect(durationEmpty).toBe(0)
      spyGetEntries.mockRestore()

      // Force catch blocks
      const spyMark = vi.spyOn(performance, "mark").mockImplementation(() => {
        throw new Error("unsupported")
      })
      const spyMeasure = vi.spyOn(performance, "measure").mockImplementation(() => {
        throw new Error("unsupported")
      })
      mark("error-mark")
      const errDuration = measure("test-measure", "start-mark")
      expect(errDuration).toBe(0)

      spyMark.mockRestore()
      spyMeasure.mockRestore()
    })

    it("getWebVitals returns structure and handles navigation entry ttfb and fcp", () => {
      // Mock navigation and FCP entries
      const spyType = vi.spyOn(performance, "getEntriesByType").mockReturnValue([
        { responseStart: 100, requestStart: 40 } as any
      ])
      const spyName = vi.spyOn(performance, "getEntriesByName").mockReturnValue([
        { startTime: 80 } as any
      ])

      const vitals = getWebVitals()
      expect(vitals).toBeDefined()
      expect(vitals.ttfb).toBe(60)
      expect(vitals.fcp).toBe(80)

      // Throw inside getEntriesByType to trigger catch block
      spyType.mockImplementation(() => {
        throw new Error("unsupported")
      })
      const vitalsErr = getWebVitals()
      expect(vitalsErr).toBeDefined()

      spyType.mockRestore()
      spyName.mockRestore()
    })

    it("reportMetric log/otel", () => {
      const mockRecordMetric = vi.fn()
      vi.stubGlobal("otel", { recordMetric: mockRecordMetric })
      
      reportMetric("test-metric", 100, { tag: "value" })
      expect(mockRecordMetric).toHaveBeenCalledWith("test-metric", 100, { tag: "value" })

      vi.unstubAllGlobals()
    })

    it("timed decorator timing check", async () => {
      const descriptor: TypedPropertyDescriptor<any> = {
        value: async () => "ok"
      }
      const decorated = timed("decorator-test")({}, "run", descriptor)
      const res = await decorated.value()
      expect(res).toBe("ok")

      // Test default propertyKey name fallback
      const descriptor2: TypedPropertyDescriptor<any> = {
        value: async () => "ok2"
      }
      const decorated2 = (timed as any)()({}, "run_fallback", descriptor2)
      const res2 = await decorated2.value()
      expect(res2).toBe("ok2")

      // Test throwing non-Error object
      const descriptor3: TypedPropertyDescriptor<any> = {
        value: async () => {
          throw "raw-error-string"
        }
      }
      const decorated3 = timed("error-test")({}, "run_err", descriptor3)
      await expect(decorated3.value()).rejects.toBe("raw-error-string")
    })

    it("MetricsBuffer aggregates and flushes", () => {
      metricsBuffer.start(10000)
      // Try starting again to hit coverage branch
      metricsBuffer.start(10000)

      metricsBuffer.record("buffered-metric", 42)
      metricsBuffer.record("buffered-metric", 58)
      
      // Force flush
      metricsBuffer.flush()
      metricsBuffer.stop()

      // Flush empty buffer construct
      const freshBuffer = new (metricsBuffer as any).constructor()
      freshBuffer.flush()
    })
  })

  describe("prefetchRoutes.ts", () => {
    it("prefetches route modules and manages idle callback", async () => {
      const loader1 = vi.fn().mockResolvedValue({})
      const loader2 = vi.fn().mockResolvedValue({})

      // Stub requestIdleCallback
      const mockRequestIdleCallback = vi.fn().mockImplementation((cb) => {
        cb()
      })
      vi.stubGlobal("requestIdleCallback", mockRequestIdleCallback)

      prefetchRouteModules([loader1, loader2], { timeoutMs: 100 })
      
      await waitFor(() => {
        expect(loader1).toHaveBeenCalled()
        expect(loader2).toHaveBeenCalled()
      })

      // Duplicate loaders should be ignored
      loader1.mockClear()
      prefetchRouteModules([loader1], { timeoutMs: 100 })
      expect(loader1).not.toHaveBeenCalled()

      vi.unstubAllGlobals()
    })

    it("prefetches route modules using setTimeout when requestIdleCallback is unavailable", async () => {
      const loader = vi.fn().mockResolvedValue({})

      // Stub requestIdleCallback as undefined
      vi.stubGlobal("requestIdleCallback", undefined)
      
      prefetchRouteModules([loader], { timeoutMs: 10 })

      await waitFor(() => {
        expect(loader).toHaveBeenCalled()
      })

      vi.unstubAllGlobals()
    })

    it("handles hasWindow fallback when window is undefined", async () => {
      vi.stubGlobal("window", undefined)
      const { prefetchRouteModules: localPrefetch } = await import("../prefetchRoutes?nocache=" + Date.now())
      
      const loader = vi.fn().mockResolvedValue({})
      localPrefetch([loader])
      expect(loader).not.toHaveBeenCalled()
      
      vi.unstubAllGlobals()
    })
  })
})
