import { describe, expect, it, vi } from "vitest"

import { createPasswordStrengthAnalyzer } from "./passwordStrength"

describe("createPasswordStrengthAnalyzer", () => {
  it("shares one analyzer load across concurrent first checks", async () => {
    const result = { score: 3 } as never
    const check = vi.fn(() => result)
    let resolveLoad!: (analyzer: { check: typeof check }) => void
    const loadAnalyzer = vi.fn(
      () =>
        new Promise<{ check: typeof check }>((resolve) => {
          resolveLoad = resolve
        })
    )
    const analyze = createPasswordStrengthAnalyzer(loadAnalyzer)

    const first = analyze("first-password")
    const second = analyze("second-password")

    expect(loadAnalyzer).toHaveBeenCalledTimes(1)
    resolveLoad({ check })
    await expect(Promise.all([first, second])).resolves.toEqual([result, result])
    expect(check).toHaveBeenNthCalledWith(1, "first-password")
    expect(check).toHaveBeenNthCalledWith(2, "second-password")
  })

  it("retries loading after a rejected first attempt", async () => {
    const result = { score: 2 } as never
    const check = vi.fn(() => result)
    let attempts = 0
    const loadAnalyzer = vi.fn(async () => {
      attempts += 1
      if (attempts === 1) throw new Error("analyzer chunk unavailable")
      return { check }
    })
    const analyze = createPasswordStrengthAnalyzer(loadAnalyzer)

    await expect(analyze("first-password")).rejects.toThrow("analyzer chunk unavailable")
    await expect(analyze("second-password")).resolves.toBe(result)

    expect(loadAnalyzer).toHaveBeenCalledTimes(2)
    expect(check).toHaveBeenCalledWith("second-password")
  })
})
