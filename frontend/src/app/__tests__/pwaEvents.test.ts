import { afterEach, describe, expect, it, vi } from "vitest"
import { consumePendingPushEducation, requestPushEducation } from "../pwaEvents"

describe("requestPushEducation", () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it("keeps an education request pending during SSR without dispatching a browser event", () => {
    vi.stubGlobal("window", undefined)

    requestPushEducation("student-1")

    expect(consumePendingPushEducation("student-1")).toBe(true)
    expect(consumePendingPushEducation("student-1")).toBe(false)
  })
})
