import { afterEach, describe, expect, it, vi } from "vitest"
import {
  consumePendingPushEducation,
  PUSH_EDUCATION_REQUEST_EVENT,
  requestPushEducation,
} from "../pwaEvents"

describe("requestPushEducation", () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.useRealTimers()
  })

  it("keeps an education request pending during SSR without dispatching a browser event", () => {
    vi.stubGlobal("window", undefined)

    requestPushEducation("student-1")

    expect(consumePendingPushEducation("student-1")).toBe(true)
    expect(consumePendingPushEducation("student-1")).toBe(false)
  })

  it("announces the request in the browser and honours it only for the same user", () => {
    const listener = vi.fn()
    window.addEventListener(PUSH_EDUCATION_REQUEST_EVENT, listener)

    try {
      requestPushEducation("student-1")
      expect(listener).toHaveBeenCalledTimes(1)
      expect(consumePendingPushEducation("student-2")).toBe(false)

      requestPushEducation("student-1")
      expect(consumePendingPushEducation("student-1")).toBe(true)
    } finally {
      window.removeEventListener(PUSH_EDUCATION_REQUEST_EVENT, listener)
    }
  })

  it("honours a pending request for exactly thirty seconds", () => {
    vi.useFakeTimers({ now: 1_000_000 })

    requestPushEducation("student-1")
    vi.setSystemTime(1_030_000)
    expect(consumePendingPushEducation("student-1")).toBe(true)

    requestPushEducation("student-1")
    vi.setSystemTime(1_060_001)
    expect(consumePendingPushEducation("student-1")).toBe(false)
  })
})
