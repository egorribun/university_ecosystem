import { describe, expect, it } from "vitest"
import { readAccessToken, persistAccessToken, clearAccessToken } from "../tokenStorage"

describe("tokenStorage", () => {
  it("readAccessToken returns null", () => {
    expect(readAccessToken()).toBeNull()
  })

  it("persistAccessToken is a no-op", () => {
    expect(() => persistAccessToken("test")).not.toThrow()
  })

  it("clearAccessToken is a no-op", () => {
    expect(() => clearAccessToken()).not.toThrow()
  })
})
