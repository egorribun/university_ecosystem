import { describe, it, expect } from "vitest"
import * as v from "valibot"

import { ensureValidResponse, ApiResponseValidationError } from "../validation"

describe("ensureValidResponse", () => {
  it("returns the parsed output for valid data", () => {
    const schema = v.object({ name: v.string(), age: v.number() })
    const data = { name: "Ada", age: 30 }
    expect(ensureValidResponse(schema, data)).toEqual(data)
  })

  it("throws ApiResponseValidationError on a nested field mismatch", () => {
    const schema = v.object({ name: v.string() })
    let caught: unknown
    try {
      ensureValidResponse(schema, { name: 123 })
    } catch (error) {
      caught = error
    }
    expect(caught).toBeInstanceOf(ApiResponseValidationError)
    const err = caught as ApiResponseValidationError
    expect(err.issues.length).toBeGreaterThan(0)
    expect(err.name).toBe("ApiResponseValidationError")
    expect(err.message).toContain("Invalid API response")
  })

  it("includes the context and covers the root-level issue branch", () => {
    const schema = v.string()
    // A top-level type mismatch produces a root issue (not a nested one),
    // and the context string is woven into the message.
    expect(() => ensureValidResponse(schema, 123, "users")).toThrow(
      /Invalid API response for users/
    )
  })

  it("uses a stable fallback message when no issue text is available", () => {
    const error = new ApiResponseValidationError([])

    expect(error.message).toBe("Invalid API response: Validation failed")
    expect(error.issues).toEqual([])
  })

  it("prefers nested issue text and then falls back to the root summary", () => {
    const nestedSchema = v.object({ user: v.object({ email: v.string() }) })
    expect(() => ensureValidResponse(nestedSchema, { user: { email: 42 } }, "profile")).toThrow(
      "Invalid API response for profile: Invalid type: Expected string but received 42"
    )

    const rootSchema = v.pipe(
      v.string(),
      v.check(() => false, "root contract failed")
    )
    expect(() => ensureValidResponse(rootSchema, "ok", "root")).toThrow(
      "Invalid API response for root: root contract failed"
    )
  })

  it("preserves structured validation issues for callers", () => {
    let caught: unknown
    try {
      ensureValidResponse(v.object({ id: v.string() }), { id: 42 })
    } catch (error) {
      caught = error
    }

    expect(caught).toBeInstanceOf(ApiResponseValidationError)
    expect((caught as ApiResponseValidationError).issues).toEqual(
      expect.arrayContaining([expect.objectContaining({ path: expect.any(Array) })])
    )
  })
})
