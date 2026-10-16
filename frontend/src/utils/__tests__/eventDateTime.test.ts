import { describe, expect, it, vi } from "vitest"

import {
  eventDateErrorTranslationKey,
  formatEventDateInput,
  formatInstantForCampusInput,
  resolveCampusEventDateRange,
  resolveCampusWallTime,
} from "@/utils/eventDateTime"

describe("campus event wall-time conversion", () => {
  it("converts an ordinary wall time to an explicit UTC instant", () => {
    expect(resolveCampusWallTime("2026-01-15T10:00", "America/New_York")).toEqual({
      status: "valid",
      epochMilliseconds: Date.parse("2026-01-15T15:00:00.000Z"),
      iso: "2026-01-15T15:00:00.000Z",
    })
  })

  it("rejects a spring-forward gap and an autumn fold without guessing", () => {
    expect(resolveCampusWallTime("2026-03-08T02:30", "America/New_York")).toEqual({
      status: "nonexistent",
    })
    expect(resolveCampusWallTime("2026-11-01T01:30", "America/New_York")).toEqual({
      status: "ambiguous",
    })
  })

  it.each(["2026-02-30T10:00", "2026-01-15T24:00", "2026-01-15 10:00"])(
    "rejects invalid calendar or input value %s",
    (value) => {
      expect(resolveCampusWallTime(value, "America/New_York")).toEqual({ status: "invalid" })
    }
  )

  it("handles the UTC date crossing at a year boundary", () => {
    expect(resolveCampusWallTime("2026-01-01T00:30", "Pacific/Kiritimati")).toMatchObject({
      status: "valid",
      iso: "2025-12-31T10:30:00.000Z",
    })
  })

  it("handles a fractional-hour IANA offset and formats the same instant back", () => {
    const resolution = resolveCampusWallTime("2026-02-01T10:15", "Asia/Kathmandu")
    expect(resolution).toMatchObject({ status: "valid", iso: "2026-02-01T04:30:00.000Z" })
    if (resolution.status === "valid") {
      expect(formatInstantForCampusInput(resolution.iso, "Asia/Kathmandu")).toBe("2026-02-01T10:15")
    }
  })

  it("formats API instants as campus wall values instead of host-local values", () => {
    expect(formatEventDateInput("2026-06-15T14:00:00.000Z", "America/New_York")).toBe(
      "2026-06-15T10:00"
    )
    expect(formatEventDateInput("2026-06-15T14:00:00.000Z", null)).toBe("")
  })

  it("compares resolved instants and preserves unchanged original values exactly", () => {
    const springRange = resolveCampusEventDateRange(
      "2026-03-08T01:30",
      "2026-03-08T03:00",
      "America/New_York"
    )
    expect(springRange).toMatchObject({
      startsAt: "2026-03-08T06:30:00.000Z",
      endsAt: "2026-03-08T07:00:00.000Z",
      valid: true,
    })

    const originalFoldRange = resolveCampusEventDateRange(
      "2026-11-01T01:30",
      "2026-11-01T02:00",
      "America/New_York",
      {
        startsAt: "2026-11-01T06:30:17.000Z",
        endsAt: "2026-11-01T07:00:23.000Z",
      }
    )
    expect(originalFoldRange).toMatchObject({
      startsAt: "2026-11-01T06:30:17.000Z",
      endsAt: "2026-11-01T07:00:23.000Z",
      valid: true,
    })
  })

  it("rejects changed ambiguous values and end instants that do not follow start", () => {
    const ambiguous = resolveCampusEventDateRange(
      "2026-11-01T01:30",
      "2026-11-01T03:00",
      "America/New_York",
      { startsAt: "2026-11-01T05:00:00.000Z" }
    )
    expect(ambiguous.startError).toBe("ambiguous")
    expect(ambiguous.valid).toBe(false)

    const reversed = resolveCampusEventDateRange(
      "2026-03-08T03:15",
      "2026-03-08T03:00",
      "America/New_York"
    )
    expect(reversed.endError).toBe("endsBeforeStarts")
    expect(reversed.valid).toBe(false)
  })

  it("fails closed when the campus zone is unavailable or invalid", () => {
    expect(resolveCampusEventDateRange("", "", null).startError).toBe("timezoneUnavailable")
    expect(resolveCampusWallTime("2026-01-15T10:00", "Not/AZone")).toEqual({
      status: "invalid",
    })
  })

  it("maps invalid event dates to a user-facing translation key", () => {
    expect(eventDateErrorTranslationKey("invalid", "start")).toBe(
      "events:form.errors.invalidDateTime"
    )
  })

  it("formats Date instances and fails closed for unsupported instant inputs", () => {
    expect(formatInstantForCampusInput("2026-06-15T10:00", "America/New_York")).toBe("")
    expect(
      formatInstantForCampusInput(new Date("2026-06-15T14:00:00.000Z"), "America/New_York")
    ).toBe("2026-06-15T10:00")
    expect(formatInstantForCampusInput("2026-01-15T99:00:00Z", "America/New_York")).toBe("")
    expect(formatInstantForCampusInput("2026-06-15T14:00:00Z", "Not/AZone")).toBe("")
    expect(formatEventDateInput("2026-02-30T10:00", "America/New_York")).toBe("")
    expect(
      resolveCampusEventDateRange("2026-06-15T10:00", "2026-06-15T11:00", "Not/AZone").startError
    ).toBe("timezoneUnavailable")
  })

  it("treats nullable and empty draft fields as the same required inputs", () => {
    const nullable = resolveCampusEventDateRange(null, undefined, "America/New_York")
    const empty = resolveCampusEventDateRange("", "", "America/New_York")

    expect(nullable).toEqual(empty)
    expect(nullable).toMatchObject({
      startError: "required",
      endError: "required",
      valid: false,
    })
  })

  it("re-resolves an unchanged wall-time original and rejects malformed explicit instants", () => {
    const changed = resolveCampusEventDateRange(
      "2026-06-15T11:00",
      "2026-06-15T12:00",
      "America/New_York",
      { startsAt: "2026-06-15T10:00", endsAt: "2026-06-15T13:00" }
    )
    expect(changed).toMatchObject({
      startsAt: "2026-06-15T15:00:00.000Z",
      endsAt: "2026-06-15T16:00:00.000Z",
      valid: true,
    })

    const invalid = resolveCampusEventDateRange(
      "2026-01-15T99:00:00Z",
      "2026-01-15T12:00",
      "America/New_York"
    )
    expect(invalid.startError).toBe("invalid")
    expect(invalid.valid).toBe(false)
  })

  it("ignores malformed formatter parts instead of accepting an invalid offset", () => {
    const formatToParts = vi
      .spyOn(Intl.DateTimeFormat.prototype, "formatToParts")
      .mockReturnValue([])
    try {
      expect(resolveCampusWallTime("2026-01-15T10:00", "UTC")).toEqual({
        status: "nonexistent",
      })
    } finally {
      formatToParts.mockRestore()
    }
  })
})
