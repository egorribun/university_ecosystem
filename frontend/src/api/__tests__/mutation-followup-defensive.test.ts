import { AxiosHeaders } from "axios"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { parseWsMessage } from "@/api/schemas/wsMessage"
import { updateTraceContext } from "@/api/interceptors/traceContext"
import { setLoggerClient } from "@/app/logger"
import { readWeatherCache } from "@/api/weather"

describe("defensive API mutation contracts", () => {
  describe("trace context", () => {
    const setTag = vi.fn()

    beforeEach(() => {
      setTag.mockReset()
      setLoggerClient({ setTag })
    })

    afterEach(() => {
      vi.restoreAllMocks()
    })

    it("trims a string returned by the canonical Axios header adapter", () => {
      const get = vi.fn(() => "  trace-from-adapter  ")
      vi.spyOn(AxiosHeaders, "from").mockReturnValue({ get } as unknown as AxiosHeaders)

      updateTraceContext({ "x-trace-id": "ignored" })

      expect(get).toHaveBeenCalledOnce()
      expect(setTag).toHaveBeenCalledWith("trace_id", "trace-from-adapter")
    })
  })

  describe("WebSocket frame parsing", () => {
    it.each(["42", "null", "true", '"text"'])(
      "rejects JSON primitive %s without throwing",
      (raw) => {
        expect(() => parseWsMessage(raw)).not.toThrow()
        expect(parseWsMessage(raw)).toBeNull()
      }
    )
  })

  describe("weather cache storage guards", () => {
    afterEach(() => {
      vi.restoreAllMocks()
      window.sessionStorage.clear()
    })

    it("does not parse when sessionStorage is unavailable", () => {
      vi.spyOn(window, "sessionStorage", "get").mockReturnValue(undefined as unknown as Storage)
      const parseSpy = vi.spyOn(JSON, "parse")

      expect(readWeatherCache({ lat: 55, lon: 37 })).toBeNull()
      expect(parseSpy).not.toHaveBeenCalled()
    })

    it("does not parse when the sessionStorage getter throws", () => {
      vi.spyOn(window, "sessionStorage", "get").mockImplementation(() => {
        throw new Error("storage unavailable")
      })
      const parseSpy = vi.spyOn(JSON, "parse")

      expect(readWeatherCache({ lat: 55, lon: 37 })).toBeNull()
      expect(parseSpy).not.toHaveBeenCalled()
    })
  })
})
