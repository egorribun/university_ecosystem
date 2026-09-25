import type { InternalAxiosRequestConfig } from "axios"
import { AxiosHeaders } from "axios"
import i18n, { fallbackLng, supportedLngs } from "@/i18n/config"

const acceptLanguageHeader = "Accept-Language"

const normalizeLanguageCandidate = (candidate: string) =>
  // `String.prototype.split` always returns at least one item for a string;
  // the non-null assertion keeps that invariant explicit for strict indexed
  // access without introducing an unreachable branch into the coverage map.
  candidate.toLowerCase().replace(/_/g, "-").split(",", 1)[0]!.trim()

const resolveAcceptLanguage = (language: string) => {
  const fallbackLanguage = fallbackLng

  const normalized = normalizeLanguageCandidate(language)
  const supportedMatch = supportedLngs.find((locale) => {
    const normalizedLocale = locale.toLowerCase()
    return normalized === normalizedLocale || normalized.startsWith(`${normalizedLocale}-`)
  })

  return supportedMatch ?? fallbackLanguage
}

export const applyLanguageHeader = (config: InternalAxiosRequestConfig) => {
  const currentLanguage = i18n.language || i18n.resolvedLanguage || fallbackLng
  const headerValue = resolveAcceptLanguage(currentLanguage)

  const headers = AxiosHeaders.from(config.headers ?? {})

  if (!headers.has(acceptLanguageHeader)) {
    headers.set(acceptLanguageHeader, headerValue)
  }

  config.headers = headers
  return config
}
