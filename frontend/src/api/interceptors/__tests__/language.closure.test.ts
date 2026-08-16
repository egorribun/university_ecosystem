import { afterEach, describe, expect, it, vi } from "vitest"
import { AxiosHeaders } from "axios"

import i18n, { fallbackLng } from "@/i18n/config"
import { applyLanguageHeader } from "@/api/interceptors/language"

const withLanguage = async (language: string, resolvedLanguage?: string) => {
  const previousLanguage = i18n.language
  const previousResolvedLanguage = i18n.resolvedLanguage
  Object.defineProperty(i18n, "language", { configurable: true, value: language })
  Object.defineProperty(i18n, "resolvedLanguage", {
    configurable: true,
    value: resolvedLanguage,
  })
  try {
    return applyLanguageHeader({ headers: undefined } as never).headers
  } finally {
    Object.defineProperty(i18n, "language", { configurable: true, value: previousLanguage })
    Object.defineProperty(i18n, "resolvedLanguage", {
      configurable: true,
      value: previousResolvedLanguage,
    })
  }
}

afterEach(() => {
  vi.restoreAllMocks()
})

describe("applyLanguageHeader", () => {
  it.each([
    ["ru-RU", "ru"],
    ["RU_ru, en;q=0.8", "ru"],
    ["en-US", "en"],
  ])("normalizes supported language %s to %s", async (language, expected) => {
    const headers = await withLanguage(language)
    expect(AxiosHeaders.from(headers).get("Accept-Language")).toBe(expected)
  })

  it("uses the fallback for blank and unsupported languages", async () => {
    expect(AxiosHeaders.from(await withLanguage(" ")).get("Accept-Language")).toBe(fallbackLng)
    expect(AxiosHeaders.from(await withLanguage("de-DE")).get("Accept-Language")).toBe(fallbackLng)
  })

  it("uses resolvedLanguage when i18n.language is empty", async () => {
    const headers = await withLanguage("", "ru-RU")
    expect(AxiosHeaders.from(headers).get("Accept-Language")).toBe("ru")
  })

  it("uses fallbackLng when both runtime language fields are empty", async () => {
    const headers = await withLanguage("", "")
    expect(AxiosHeaders.from(headers).get("Accept-Language")).toBe(fallbackLng)
  })

  it("does not overwrite either casing of an existing header", () => {
    const upper = applyLanguageHeader({
      headers: { "Accept-Language": "custom" },
    } as never)
    expect(AxiosHeaders.from(upper.headers).get("Accept-Language")).toBe("custom")

    const lower = applyLanguageHeader({
      headers: { "accept-language": "custom-lower" },
    } as never)
    expect(AxiosHeaders.from(lower.headers).get("Accept-Language")).toBe("custom-lower")
  })
})
