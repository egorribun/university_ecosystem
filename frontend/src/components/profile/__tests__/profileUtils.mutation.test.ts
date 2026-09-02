import { describe, expect, it } from "vitest"

import { formatDuration } from "@/components/profile/profileUtils"

describe("profile utility mutation contracts", () => {
  it("uses the zero-duration fallback for absent values and formats valid milliseconds", () => {
    expect(formatDuration(null)).toBe("0:00")
    expect(formatDuration(undefined)).toBe("0:00")
    expect(formatDuration(-1)).toBe("0:00")
    expect(formatDuration(0)).toBe("0:00")
    expect(formatDuration(61_000)).toBe("1:01")
    expect(formatDuration(3_661_000)).toBe("61:01")
  })
})
