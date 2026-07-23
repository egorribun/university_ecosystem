import { renderHook } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

vi.mock("@/contexts/LanguageContext", () => ({
  useLanguage: () => ({ language: "en" }),
}))

import {
  formatCurrency,
  formatDate,
  formatNumber,
  getPluralCategory,
  useLocaleFormatters,
} from "@/i18n/formatters"

describe("locale formatters", () => {
  it("formats numbers with the selected locale and options", () => {
    expect(formatNumber("en", 1234.5, { minimumFractionDigits: 2 })).toBe("1,234.50")
    expect(formatNumber("ru", 1234.5, { minimumFractionDigits: 2 })).toContain("1")
    expect(formatNumber("ru", 1234.5, { minimumFractionDigits: 2 })).toContain(",50")
  })

  it("formats currencies and preserves caller options", () => {
    expect(formatCurrency("en", 12.5, "USD", { currencyDisplay: "code" })).toBe("USD 12.50")
  })

  it("supports numeric and bigint plural inputs", () => {
    expect(getPluralCategory("en", 1)).toBe("one")
    expect(getPluralCategory("en", 2)).toBe("other")
    expect(getPluralCategory("en", BigInt(1))).toBe("one")
  })

  it("supports date, datetime, and caller-defined date options", () => {
    const value = new Date("2024-06-15T12:30:00.000Z")
    expect(formatDate("en", value)).toContain("Jun")
    expect(formatDate("en", value, { preset: "datetime" })).toContain("Jun")
    expect(formatDate("en", "2024-06-15", { preset: undefined, year: "numeric" })).toBe("2024")
    expect(formatDate("en", value.getTime(), { month: "2-digit", day: "2-digit" })).toContain("06")
  })

  it("exposes all formatter methods through the locale hook", () => {
    const { result } = renderHook(() => useLocaleFormatters())

    expect(result.current.localeCode).toBe("en-US")
    expect(result.current.formatNumber(1000)).toBe("1,000")
    expect(result.current.formatCurrency(12.5, "USD")).toContain("12.50")
    expect(result.current.formatDate("2024-06-15")).toContain("Jun")
    expect(result.current.getPlural(1)).toBe("one")
  })
})
