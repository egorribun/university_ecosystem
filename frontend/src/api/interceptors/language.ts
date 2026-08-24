import type { InternalAxiosRequestConfig } from "axios"
import { AxiosHeaders } from "axios"
import i18n, { fallbackLng, supportedLngs } from "@/i18n/config"

const acceptLanguageHeader = "Accept-Language"

const normalizeLanguageCandidate = (candidate: string) =>
  candidate.toLowerCase().replace(/_/g, "-").split(",", 1).join("").trim()

const resolveAcceptLanguage = (language: string) => {
  const fallbackLanguage = fallbackLng

  const normalized = normalizeLanguageCandidate(language)
  if (!normalized) return fallbackLanguage

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

  if (!headers.has(acceptLanguageHeader) && !headers.has(acceptLanguageHeader.toLowerCase())) {
    headers.set(acceptLanguageHeader, headerValue)
  }

  config.headers = headers
  return config
}
