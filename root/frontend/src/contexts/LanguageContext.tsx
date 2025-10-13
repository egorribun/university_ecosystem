import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react"
import dayjs from "dayjs"
import "dayjs/locale/en"
import "dayjs/locale/ru"
import type { ReactNode } from "react"
import i18n from "@/i18n/config"

export type SupportedLanguage = "en" | "ru"

const storageKey = "ue:language"

const resolveInitialLanguage = (): SupportedLanguage => {
  if (typeof window === "undefined") {
    return (i18n.language as SupportedLanguage) || "ru"
  }
  const stored = window.localStorage.getItem(storageKey)
  if (stored === "en" || stored === "ru") return stored
  const browser = window.navigator?.language || ""
  if (browser.toLowerCase().startsWith("en")) return "en"
  return "ru"
}

type LanguageContextValue = {
  language: SupportedLanguage
  setLanguage: (language: SupportedLanguage) => void
  available: readonly SupportedLanguage[]
}

const LanguageContext = createContext<LanguageContextValue | undefined>(undefined)

const availableLanguages: readonly SupportedLanguage[] = ["ru", "en"]

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [language, setLanguageState] = useState<SupportedLanguage>(resolveInitialLanguage)

  useEffect(() => {
    const onLanguageChanged = (lng: string) => {
      if (lng === "en" || lng === "ru") {
        setLanguageState(lng)
      }
    }
    i18n.on("languageChanged", onLanguageChanged)
    return () => {
      i18n.off("languageChanged", onLanguageChanged)
    }
  }, [])

  useEffect(() => {
    void i18n.changeLanguage(language)
    dayjs.locale(language === "ru" ? "ru" : "en")
    if (typeof window !== "undefined") {
      window.localStorage.setItem(storageKey, language)
      document.documentElement.setAttribute("lang", language)
    }
  }, [language])

  const setLanguage = useCallback((lng: SupportedLanguage) => {
    setLanguageState(lng)
  }, [])

  const value = useMemo<LanguageContextValue>(
    () => ({ language, setLanguage, available: availableLanguages }),
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
  return language === "ru" ? "ru-RU" : "en-US"
}
