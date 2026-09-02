import { describe, expect, it, vi } from "vitest"

import { analyzePasswordStrength, createPasswordStrengthAnalyzer } from "./passwordStrength"

describe("createPasswordStrengthAnalyzer", () => {
  it("shares one analyzer load per locale across concurrent first checks", async () => {
    const result = { score: 3 } as never
    const englishCheck = vi.fn(() => result)
    const russianCheck = vi.fn(() => result)
    const resolvers = new Map<
      string,
      (analyzer: { check: typeof englishCheck | typeof russianCheck }) => void
    >()
    const loadAnalyzer = vi.fn(
      (locale: string) =>
        new Promise<{ check: typeof englishCheck | typeof russianCheck }>((resolve) => {
          resolvers.set(locale, resolve)
        })
    )
    const analyze = createPasswordStrengthAnalyzer(loadAnalyzer)

    const firstEnglish = analyze("first-password", "en-US")
    const secondEnglish = analyze("second-password", "en")
    const firstRussian = analyze("третий-пароль", "ru-RU")

    expect(loadAnalyzer).toHaveBeenCalledTimes(2)
    expect(loadAnalyzer).toHaveBeenCalledWith("en")
    expect(loadAnalyzer).toHaveBeenCalledWith("ru")
    resolvers.get("en")?.({ check: englishCheck })
    resolvers.get("ru")?.({ check: russianCheck })
    await expect(Promise.all([firstEnglish, secondEnglish, firstRussian])).resolves.toEqual([
      result,
      result,
      result,
    ])
    expect(englishCheck).toHaveBeenNthCalledWith(1, "first-password")
    expect(englishCheck).toHaveBeenNthCalledWith(2, "second-password")
    expect(russianCheck).toHaveBeenCalledWith("третий-пароль")
  })

  it("retries loading after a rejected first attempt", async () => {
    const result = { score: 2 } as never
    const check = vi.fn(() => result)
    let attempts = 0
    const loadAnalyzer = vi.fn(async (locale: string) => {
      attempts += 1
      if (attempts === 1) throw new Error("analyzer chunk unavailable")
      expect(locale).toBe("ru")
      return { check }
    })
    const analyze = createPasswordStrengthAnalyzer(loadAnalyzer)

    await expect(analyze("первый-пароль", "ru-RU")).rejects.toThrow("analyzer chunk unavailable")
    await expect(analyze("второй-пароль", "ru")).resolves.toBe(result)

    expect(loadAnalyzer).toHaveBeenCalledTimes(2)
    expect(check).toHaveBeenCalledWith("второй-пароль")
  })
})

describe("real localized password analyzer", () => {
  it.each([
    ["en-US", /[A-Za-z]/],
    ["ru-RU", /[А-Яа-яЁё]/],
  ])("returns meaningful %s feedback instead of raw translation keys", async (locale, script) => {
    const result = await analyzePasswordStrength("password", locale)
    const feedback = [result.feedback.warning, ...result.feedback.suggestions]
      .filter(Boolean)
      .join(" ")

    expect(feedback).not.toMatch(/\b(?:topTen|anotherWord)\b/)
    expect(feedback).toMatch(script)
  })
})
