import { useMemo } from "react"
import { useLanguage } from "@/contexts/LanguageContext"
import { localeMeta, type SupportedLanguage } from "@/i18n/metadata"

type DateTimeFormatOptions = Intl.DateTimeFormatOptions & { preset?: "date" | "datetime" }

const getLocaleCode = (language: SupportedLanguage) => localeMeta[language]?.formatterLocale ?? "en-US"

export const getPluralCategory = (language: SupportedLanguage, value: number | bigint) => {
  const rules = new Intl.PluralRules(getLocaleCode(language))
  return rules.select(value)
}

export const formatNumber = (
  language: SupportedLanguage,
  value: number,
  options: Intl.NumberFormatOptions = {}
) => new Intl.NumberFormat(getLocaleCode(language), options).format(value)

export const formatCurrency = (
  language: SupportedLanguage,
  value: number,
  currency: string,
  options: Intl.NumberFormatOptions = {}
) =>
  new Intl.NumberFormat(getLocaleCode(language), {
    style: "currency",
    currency,
    ...options,
  }).format(value)

export const formatDate = (
  language: SupportedLanguage,
  value: Date | string | number,
  options: DateTimeFormatOptions = { preset: "date" }
) => {
  const parsed = typeof value === "string" || typeof value === "number" ? new Date(value) : value
  const locale = getLocaleCode(language)
  const { preset, ...rest } = options
  const merged: Intl.DateTimeFormatOptions = {
    ...(preset === "datetime"
      ? { dateStyle: "medium", timeStyle: "short" }
      : preset === "date"
        ? { dateStyle: "medium" }
        : {}),
    ...rest,
  }

  return new Intl.DateTimeFormat(locale, merged).format(parsed)
}

export function useLocaleFormatters() {
  const { language } = useLanguage()

  return useMemo(
    () => ({
      formatNumber: (value: number, options?: Intl.NumberFormatOptions) =>
        formatNumber(language, value, options),
      formatCurrency: (value: number, currency: string, options?: Intl.NumberFormatOptions) =>
        formatCurrency(language, value, currency, options),
      formatDate: (value: Date | string | number, options?: DateTimeFormatOptions) =>
        formatDate(language, value, options),
      getPlural: (value: number | bigint) => getPluralCategory(language, value),
      localeCode: getLocaleCode(language),
    }),
    [language]
  )
}
