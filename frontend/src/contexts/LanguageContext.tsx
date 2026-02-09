import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react"
import dayjs from "dayjs"
import "dayjs/locale/en"
import "dayjs/locale/ru"
import "dayjs/locale/ar"
import type { ReactNode } from "react"
import i18n from "@/i18n/config"
import { fallbackLng, localeMeta, supportedLngs, type SupportedLanguage } from "@/i18n/metadata"
export type { SupportedLanguage } from "@/i18n/metadata"

const storageKey = "ue:language"

const resolveInitialLanguage = (): SupportedLanguage => {
  if (typeof window === "undefined") {
    return (i18n.language as SupportedLanguage) || fallbackLng
  }

  const stored = window.localStorage.getItem(storageKey)
  if (stored && supportedLngs.includes(stored as SupportedLanguage)) {
    return stored as SupportedLanguage
  }

  const browser = window.navigator?.language || ""
  const match = supportedLngs.find((lng) => browser.toLowerCase().startsWith(lng))
  return match ?? fallbackLng
}

type LanguageContextValue = {
  language: SupportedLanguage
  setLanguage: (language: SupportedLanguage) => void
  available: readonly SupportedLanguage[]
}

const LanguageContext = createContext<LanguageContextValue | undefined>(undefined)

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [language, setLanguageState] = useState<SupportedLanguage>(resolveInitialLanguage)

  useEffect(() => {
    const onLanguageChanged = (lng: string) => {
      if (supportedLngs.includes(lng as SupportedLanguage)) {
        setLanguageState(lng as SupportedLanguage)
      }
    }
    i18n.on("languageChanged", onLanguageChanged)
    return () => {
      i18n.off("languageChanged", onLanguageChanged)
    }
  }, [])

  useEffect(() => {
    void i18n.changeLanguage(language)
    const locale = localeMeta[language]
    dayjs.locale(locale?.dayjsLocale)
    if (typeof window !== "undefined") {
      window.localStorage.setItem(storageKey, language)
      document.documentElement.setAttribute("lang", language)
      document.documentElement.setAttribute("dir", locale?.dir ?? "ltr")
      document.body?.setAttribute("dir", locale?.dir ?? "ltr")
    }
  }, [language])

  const setLanguage = useCallback((lng: SupportedLanguage) => {
    setLanguageState(lng)
  }, [])

  const value = useMemo<LanguageContextValue>(
    () => ({ language, setLanguage, available: supportedLngs }),
    [language, setLanguage]
  )

  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>
}

export function useLanguage() {
  const context = useContext(LanguageContext)
  if (!context) {
    throw new Error("useLanguage must be used within a LanguageProvider")
  }
  return context
}

export function getLocaleForLanguage(language: SupportedLanguage) {
  return localeMeta[language]?.formatterLocale ?? "en-US"
}




