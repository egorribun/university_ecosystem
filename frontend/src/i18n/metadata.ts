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
  "map",
] as const

export const localeMeta = {
  en: {
    dir: "ltr" as const,
    formatterLocale: "en-US",
  },
  ru: {
    dir: "ltr" as const,
    formatterLocale: "ru-RU",
  },
} as const

export type SupportedLanguage = keyof typeof localeMeta

export const supportedLngs = Object.keys(localeMeta) as SupportedLanguage[]

export const fallbackLng: SupportedLanguage = "ru"
