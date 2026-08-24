// @vitest-environment node

import { describe, expect, it } from "vitest"

import { resolveShareUrl } from "../useShare"

describe("resolveShareUrl in an SSR runtime", () => {
  it("returns an explicit URL without requiring window", () => {
    expect(resolveShareUrl("https://example.test/shared")).toBe("https://example.test/shared")
  })

  it("returns an empty URL when no browser location exists", () => {
    expect(resolveShareUrl()).toBe("")
  })
})
