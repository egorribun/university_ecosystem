/** @vitest-environment node */

import { describe, expect, it } from "vitest"
import { resolveRedirectPath } from "../redirect"

describe("resolveRedirectPath without a window (SSR)", () => {
  it("keeps only the path of an absolute redirect, dropping its origin", () => {
    expect(resolveRedirectPath("https://other.test/events?tab=my#top")).toBe("/events?tab=my#top")
  })

  it("still falls back for malformed and empty redirects", () => {
    expect(resolveRedirectPath("")).toBe("/dashboard")
    expect(resolveRedirectPath("http://")).toBe("/dashboard")
  })
})
