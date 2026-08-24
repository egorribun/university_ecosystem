import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react"
import type { ReactNode } from "react"
import { I18nextProvider } from "react-i18next"
import type { i18n as I18nInstance } from "i18next"
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

const isSupportedLanguage = (value: unknown): value is SupportedLanguage =>
  typeof value === "string" && supportedLngs.includes(value as SupportedLanguage)

export const resolveInitialLanguage = (instance: I18nInstance): SupportedLanguage => {
  if (typeof window === "undefined") {
    return isSupportedLanguage(instance.language) ? instance.language : fallbackLng
  }

  if (isSupportedLanguage(window.__UE_SELECTED_LANG__)) return window.__UE_SELECTED_LANG__

  let stored: string | null = null
  try {
    stored = window.localStorage.getItem(storageKey)
  } catch {
    // Storage can be unavailable in privacy modes; continue with browser locale.
  }
  if (isSupportedLanguage(stored)) return stored
  return fallbackLng
}

type LanguageContextValue = {
  language: SupportedLanguage
  setLanguage: (language: SupportedLanguage) => void
  available: readonly SupportedLanguage[]
}

const LanguageContext = createContext<LanguageContextValue | undefined>(undefined)

export function LanguageProvider({ children }: { children: ReactNode }) {
  const instance = globalThis.__ssrI18nGetter__?.() ?? i18n
  const [language, setLanguageState] = useState<SupportedLanguage>(() =>
    resolveInitialLanguage(instance)
  )

  useEffect(() => {
    const onLanguageChanged = (lng: string) => {
      if (supportedLngs.includes(lng as SupportedLanguage)) {
        setLanguageState(lng as SupportedLanguage)
      }
    }
    instance.on("languageChanged", onLanguageChanged)
    return () => {
      instance.off("languageChanged", onLanguageChanged)
    }
  }, [instance])

  useEffect(() => {
    void instance.changeLanguage(language)
    const locale = localeMeta[language]
    // dayjs.locale(locale?.dayjsLocale) removed
    // React never executes effects during server rendering, so this callback is
    // intrinsically browser-only. Keeping a second environment guard here hid
    // the actual invariant and created a permanently unreachable branch.
    try {
      window.localStorage.setItem(storageKey, language)
    } catch {
      // Persistence is best-effort; DOM and cookie state must still update.
    }
    document.documentElement.setAttribute("lang", language)
    document.documentElement.setAttribute("dir", locale.dir)
    document.body?.setAttribute("dir", locale.dir)
    // Wave 127 SW3 — cookie-mirror alongside localStorage write
    setLangCookie(language)
  }, [instance, language])

  const setLanguage = useCallback((lng: SupportedLanguage) => {
    setLanguageState(lng)
  }, [])

  const value = useMemo<LanguageContextValue>(
    () => ({ language, setLanguage, available: supportedLngs }),
    [language, setLanguage]
  )

  return (
    <I18nextProvider i18n={instance}>
      <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>
    </I18nextProvider>
  )
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
