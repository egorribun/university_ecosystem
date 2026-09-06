import { describe, expect, it } from "vitest"

import { getRetryDelay, isAbortError } from "@/api/client"

describe("api client defensive helper contracts", () => {
  it.each([
    [new DOMException("aborted", "AbortError"), true],
    // A DOMException is handled by its own branch even when its name happens
    // to match the object-branch names.
    [new DOMException("cancelled", "CanceledError"), false],
    [{ name: "AbortError" }, true],
    [{ name: "CanceledError" }, true],
    [{ name: "NetworkError" }, false],
    [{}, false],
    [Object.create(null), false],
    [null, false],
    [undefined, false],
    ["AbortError", false],
    [42, false],
  ])("classifies %j as abort=%s", (error, expected) => {
    expect(isAbortError(error)).toBe(expected)
  })

  it("normalizes retry-after headers with deterministic precedence and bounds", () => {
    expect(getRetryDelay(undefined)).toBe(2_000)
    expect(getRetryDelay({})).toBe(2_000)
    expect(getRetryDelay({ "retry-after": "2" })).toBe(2_000)
    expect(getRetryDelay({ "Retry-After": "3" })).toBe(3_000)
    expect(getRetryDelay({ "retry-after": "1", "Retry-After": "9" })).toBe(1_000)
    expect(getRetryDelay({ "retry-after": 3 })).toBe(2_000)
    expect(getRetryDelay({ "retry-after": "not-a-number" })).toBe(2_000)
    expect(getRetryDelay({ "retry-after": "Infinity" })).toBe(2_000)
    expect(getRetryDelay({ "retry-after": "-1" })).toBe(0)
  })
})
