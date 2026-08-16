import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react"
import type { ReactNode } from "react"
import i18n from "@/i18n/config"
import { fallbackLng, localeMeta, supportedLngs, type SupportedLanguage } from "@/i18n/metadata"
export type { SupportedLanguage } from "@/i18n/metadata"

const storageKey = "ue:language"
const COOKIE_MAX_AGE_SECONDS = 365 * 24 * 60 * 60 // 1 year

// Wave 127 SW3 — cookie-mirror for SSR language parity. Server reads this
// cookie + exposes via globalThis.__ssrLangGetter__ (W127 SW4); RootShell
// renders <html lang="en"> server-side from the cookie value (W127 SW5),
// matching the client's THEME_INIT_SCRIPT pre-paint state.
//
// Cookie name `ue:language` matches the localStorage storageKey; per RFC 6265
// the `:` character is allowed in cookie names without URL-encoding (token
// grammar excludes only separators like `=`, `;`, ` `). Browsers preserve
// the colon as-is, so server-side parseCookie reads `ue:language` directly.
// Cookie attrs identical to W127 SW2 ThemeContext (Path=/, Lax, 1y, Secure
// on HTTPS).
const setLangCookie = (lang: SupportedLanguage) => {
  const isSecure = typeof location !== "undefined" && location.protocol === "https:"
  const secureAttr = isSecure ? "; Secure" : ""
  document.cookie = `${storageKey}=${encodeURIComponent(lang)}; Path=/; Max-Age=${COOKIE_MAX_AGE_SECONDS}; SameSite=Lax${secureAttr}`
}

const resolveInitialLanguage = (): SupportedLanguage => {
  if (typeof window === "undefined") {
    return (i18n.language as SupportedLanguage) || fallbackLng
  }

  let stored: string | null = null
  try {
    stored = window.localStorage.getItem(storageKey)
  } catch {
    // Storage can be unavailable in privacy modes; continue with browser locale.
  }
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
    // dayjs.locale(locale?.dayjsLocale) removed
    if (typeof window !== "undefined") {
      try {
        window.localStorage.setItem(storageKey, language)
      } catch {
        // Persistence is best-effort; DOM and cookie state must still update.
      }
      document.documentElement.setAttribute("lang", language)
      document.documentElement.setAttribute("dir", locale?.dir ?? "ltr")
      document.body?.setAttribute("dir", locale?.dir ?? "ltr")
      // Wave 127 SW3 — cookie-mirror alongside localStorage write
      setLangCookie(language)
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
