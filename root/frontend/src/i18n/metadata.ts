export const defaultNS = "common" as const

export const namespaces = [
  "common",
  "navigation",
  "dashboard",
  "activity",
  "schedule",
  "auth",
  "settings",
  "system",
  "news",
  "events",
  "profile",
  "notifications",
  "admin",
  "stories",
  "messenger",
] as const

export const localeMeta = {
  en: {
    dir: "ltr" as const,
    dayjsLocale: "en",
    formatterLocale: "en-US",
  },
  ru: {
    dir: "ltr" as const,
    dayjsLocale: "ru",
    formatterLocale: "ru-RU",
  },
  ar: {
    dir: "rtl" as const,
    dayjsLocale: "ar",
    formatterLocale: "ar-EG",
  },
} as const

export type SupportedLanguage = keyof typeof localeMeta

export const supportedLngs = Object.keys(localeMeta) as SupportedLanguage[]

export const fallbackLng: SupportedLanguage = "en"
