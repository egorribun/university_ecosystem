import { describe, expect, it } from "vitest"
import axios from "axios"
import { extractApiError, createFallback } from "../error"
import { ApiResponseValidationError, ensureValidResponse } from "@/api/validation"
import * as v from "valibot"

// ---------------------------------------------------------------------------
// Helpers — build a minimal AxiosError shape without importing internals
// ---------------------------------------------------------------------------

// Actually — just use axios.create to get a typed AxiosError via real axios Error type:
const buildAxiosError = (status: number, data: Record<string, unknown>) => {
  const error = axios.create().interceptors // doesn't matter
  void error
  // Simplest approach: construct the object axios.isAxiosError will accept
  const err = Object.assign(new Error("network error"), {
    isAxiosError: true,
    response: { status, data },
  })
  return err
}

describe("extractApiError", () => {
  // ---------------------------------------------------------------------------
  // Axios errors
  // ---------------------------------------------------------------------------
  describe("with an Axios error", () => {
    it("extracts status and string detail", () => {
      const err = buildAxiosError(400, { detail: "Bad input" })
      const result = extractApiError(err)
      expect(result.status).toBe(400)
      expect(result.message).toBe("Bad input")
    })

    it("falls back to data.message when detail is not a string", () => {
      const err = buildAxiosError(500, { message: "Internal error" })
      const result = extractApiError(err)
      expect(result.status).toBe(500)
      expect(result.message).toBe("Internal error")
    })

    it("falls back to error.message when data has no detail or message", () => {
      const err = buildAxiosError(503, {})
      ;(err as unknown as { message: string }).message = "Service Unavailable"
      const result = extractApiError(err)
      expect(result.status).toBe(503)
      expect(result.message).toBe("Service Unavailable")
    })

    it("uses the custom fallbackMessage when data and message are absent", () => {
      const err = buildAxiosError(0, {})
      ;(err as unknown as { message: string }).message = ""
      const result = extractApiError(err, "Custom fallback")
      expect(result.message).toBe("Custom fallback")
    })

    it("extracts traceId from data.trace_id", () => {
      const err = buildAxiosError(500, { detail: "Oops", trace_id: "abc-123" })
      expect(extractApiError(err).traceId).toBe("abc-123")
    })

    it("omits traceId when not present", () => {
      const err = buildAxiosError(400, { detail: "Fail" })
      expect(extractApiError(err).traceId).toBeUndefined()
    })

    it("parses FastAPI Pydantic validation array in detail", () => {
      const err = buildAxiosError(422, {
        detail: [
          { msg: "field required", loc: ["body", "email"], type: "missing" },
          { msg: "invalid format", loc: ["body", "phone"], type: "value_error" },
        ],
      })
      const result = extractApiError(err)
      expect(result.status).toBe(422)
      // When detail is an array, message falls back to the Axios error message
      expect(result.details).toHaveLength(2)
      expect(result.details![0]).toMatchObject({
        code: "missing",
        message: "field required",
        field: "email",
      })
      expect(result.details![1]).toMatchObject({
        code: "value_error",
        message: "invalid format",
        field: "phone",
      })
    })

    it("normalizes missing validation type and non-array locations", () => {
      const err = buildAxiosError(422, {
        detail: [{ msg: "invalid", loc: "email" }],
      })

      expect(extractApiError(err).details).toEqual([
        { code: "validation_error", message: "invalid", field: undefined },
      ])
    })

    it("ignores malformed validation detail entries", () => {
      const err = buildAxiosError(422, {
        detail: [{ msg: "missing location" }, { loc: ["body", "email"] }, null],
      })

      expect(extractApiError(err).details).toBeUndefined()
    })

    it("omits details when validation array is empty", () => {
      const err = buildAxiosError(200, { detail: [] })
      const result = extractApiError(err)
      expect(result.details).toBeUndefined()
    })

    it("returns status 0 when response is absent (network error)", () => {
      const err = Object.assign(new Error("Network Error"), { isAxiosError: true })
      const result = extractApiError(err)
      expect(result.status).toBe(0)
    })
  })

  // ---------------------------------------------------------------------------
  // Plain Error
  // ---------------------------------------------------------------------------
  describe("with a plain Error", () => {
    it("extracts message and status 0", () => {
      const err = new Error("Something went wrong")
      const result = extractApiError(err)
      expect(result.status).toBe(0)
      expect(result.message).toBe("Something went wrong")
    })

    it("uses fallbackMessage when error.message is empty", () => {
      const err = new Error("")
      const result = extractApiError(err, "Fallback msg")
      expect(result.message).toBe("Fallback msg")
    })
  })

  it("normalizes a response-validation error with issue paths", () => {
    let caught: unknown
    try {
      ensureValidResponse(v.object({ id: v.string() }), { id: 42 }, "users/me")
    } catch (error) {
      caught = error
    }

    expect(caught).toBeInstanceOf(ApiResponseValidationError)
    const result = extractApiError(caught)
    expect(result.status).toBe(422)
    expect(result.details?.[0]?.field).toBe("id")
  })

  it("uses validation fallbacks for a root issue without a received value or path", () => {
    let caught: unknown
    try {
      ensureValidResponse(v.string(), undefined, "root")
    } catch (error) {
      caught = error
    }

    const result = extractApiError(caught)
    expect(result.details?.[0]).toMatchObject({ code: "string", field: undefined })
  })

  // ---------------------------------------------------------------------------
  // String error
  // ---------------------------------------------------------------------------
  describe("with a string error", () => {
    it("uses the string directly as the message", () => {
      const result = extractApiError("string error")
      expect(result.status).toBe(0)
      expect(result.message).toBe("string error")
    })
  })

  // ---------------------------------------------------------------------------
  // Unknown / non-Error, non-string
  // ---------------------------------------------------------------------------
  describe("with an unknown error type", () => {
    it("returns fallbackMessage for null", () => {
      const result = extractApiError(null)
      expect(result.message).toBe("An unexpected error occurred")
    })

    it("returns fallbackMessage for a number", () => {
      const result = extractApiError(42)
      expect(result.message).toBe("An unexpected error occurred")
    })

    it("uses custom fallbackMessage for unknown types", () => {
      const result = extractApiError({}, "Custom fallback")
      expect(result.message).toBe("Custom fallback")
    })
  })

  // ---------------------------------------------------------------------------
  // Default fallbackMessage
  // ---------------------------------------------------------------------------
  it("uses 'An unexpected error occurred' as the default fallbackMessage", () => {
    const result = extractApiError(null)
    expect(result.message).toBe("An unexpected error occurred")
  })
})

// ---------------------------------------------------------------------------
// createFallback
// ---------------------------------------------------------------------------
describe("createFallback", () => {
  it("returns a function that always returns the fallback value", () => {
    const fn = createFallback<string>("default")
    expect(fn(new Error("irrelevant"))).toBe("default")
    expect(fn(null)).toBe("default")
  })

  it("works with complex fallback values", () => {
    const fn = createFallback<number[]>([1, 2, 3])
    expect(fn("any error")).toEqual([1, 2, 3])
  })

  it("works with null as fallback", () => {
    const fn = createFallback<null>(null)
    expect(fn(new Error("x"))).toBeNull()
  })
})
