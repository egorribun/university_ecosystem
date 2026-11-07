import { afterEach, describe, expect, it, vi } from "vitest"

import {
  isExpiredOtherSessionRecord,
  isRetryableReplayStatus,
  OTHER_SESSION_RECORD_TTL_MS,
  replayBackoffMs,
} from "../replayPolicy"

describe("AUD-375: replay retry policy", () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it.each([408, 425, 429, 500, 503, 599])("treats HTTP %s as retryable", (status) => {
    expect(isRetryableReplayStatus(status)).toBe(true)
  })

  it.each([0, 200, 302, 400, 403, 404, 409, 410, 422])(
    "treats HTTP %s as a non-retryable rejection",
    (status) => {
      expect(isRetryableReplayStatus(status)).toBe(false)
    }
  )

  it("draws full jitter below a ceiling that doubles per attempt", () => {
    vi.spyOn(Math, "random").mockReturnValue(0.5)

    expect(replayBackoffMs(1)).toBe(500)
    expect(replayBackoffMs(2)).toBe(1_000)
    expect(replayBackoffMs(3)).toBe(2_000)
  })

  it("caps the backoff ceiling at five minutes for late attempts", () => {
    vi.spyOn(Math, "random").mockReturnValue(0.5)

    expect(replayBackoffMs(20)).toBe(150_000)
  })

  it("never returns a delay at or above the cap", () => {
    vi.spyOn(Math, "random").mockReturnValue(0.999_999)

    expect(replayBackoffMs(20)).toBeLessThan(300_000)
  })

  it("expires another session's record exactly at the retention limit", () => {
    expect(isExpiredOtherSessionRecord(0, OTHER_SESSION_RECORD_TTL_MS - 1)).toBe(false)
    expect(isExpiredOtherSessionRecord(0, OTHER_SESSION_RECORD_TTL_MS)).toBe(true)
  })
})
