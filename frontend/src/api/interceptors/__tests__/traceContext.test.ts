import { beforeEach, describe, expect, it, vi } from "vitest"
import { AxiosHeaders } from "axios"

import { updateTraceContext } from "@/api/interceptors/traceContext"
import { setLoggerClient } from "@/app/logger"

const setTag = vi.fn()

describe("updateTraceContext", () => {
  beforeEach(() => {
    setTag.mockReset()
    setLoggerClient({ setTag })
  })

  it("clears trace state when response headers are absent", () => {
    const fromSpy = vi.spyOn(AxiosHeaders, "from")

    updateTraceContext(undefined)

    // The absent-header path must return before constructing an Axios adapter.
    // Besides avoiding needless work, this keeps the interceptor safe when a
    // response object is only partially initialized during error handling.
    expect(fromSpy).not.toHaveBeenCalled()
    expect(setTag).toHaveBeenCalledWith("trace_id", "")
  })

  it("stores a non-empty trace identifier case-insensitively", () => {
    updateTraceContext({ "X-Trace-Id": "trace-123" })
    expect(setTag).toHaveBeenCalledWith("trace_id", "trace-123")
  })

  it("clears an empty trace header", () => {
    updateTraceContext({ "x-trace-id": "" })
    expect(setTag).toHaveBeenCalledWith("trace_id", "")
  })

  it("rejects a whitespace-only trace header", () => {
    updateTraceContext({ "x-trace-id": "   " })
    expect(setTag).toHaveBeenCalledWith("trace_id", "")
  })

  it("normalizes valid numeric HTTP header values", () => {
    updateTraceContext({ "x-trace-id": 42 })
    expect(setTag).toHaveBeenCalledWith("trace_id", "42")
  })

  it("clears a non-string value returned by a defensive header adapter", () => {
    vi.spyOn(AxiosHeaders, "from").mockReturnValue({
      get: () => 42,
    } as unknown as AxiosHeaders)

    updateTraceContext({ "x-trace-id": "ignored" })
    expect(setTag).toHaveBeenCalledWith("trace_id", "")
  })
})
