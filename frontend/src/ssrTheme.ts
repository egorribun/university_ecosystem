/**
 * @fileoverview Wave 127 Phase 5 SW4 — SSR-side theme + language cookie parsing.
 *
 * Mirrors `ssrAuth.ts` pattern. Pure utility module (no Node-specific imports).
 * Used by `src/server.ts` to extract theme/lang preferences from request cookies
 * so RootShell (W127 SW5) can render `<html class="dark" lang="en">` server-side,
 * matching client's THEME_INIT_SCRIPT pre-paint state without hydration mismatches.
 *
 * Cookie names mirror W127 SW2 + SW3 writers in:
 *   - `src/contexts/ThemeContext.tsx` (cookie name `ue-mode`)
 *   - `src/contexts/LanguageContext.tsx` (cookie name `ue:language`)
 */
import { parseCookie } from "./ssrAuth"

export type ResolvedTheme = "light" | "dark"
export type ResolvedLang = "ru" | "en"

const SUPPORTED_LANGS: readonly ResolvedLang[] = ["ru", "en"]

/**
 * Resolve theme cookie value to "light" | "dark" for server-side `<html class>`.
 *
 * Cookie values: "light" / "dark" / "system" / undefined / garbled.
 *   - "dark" → dark
 *   - "light" / "system" / missing / garbled → light
 *
 * "system" maps to light because the server cannot read prefers-color-scheme;
 * the inline THEME_INIT_SCRIPT picks up matchMedia client-side and applies
 * the dark class before React hydrates if system pref is dark — short flash
 * for system-pref users on first visit, acceptable per Phase 3 lightweight
 * design doc.
 */
export function resolveTheme(cookieValue: string | null | undefined): ResolvedTheme {
  if (cookieValue === "dark") return "dark"
  return "light"
}

/**
 * Resolve language cookie value to "ru" | "en" for server-side `<html lang>`.
 *
 * Cookie values: "ru" / "en" / undefined / garbled.
 *   - Recognized supported lang → that lang
 *   - Otherwise → "ru" (default per fallbackLng in `i18n/metadata.ts`)
 */
export function resolveLang(cookieValue: string | null | undefined): ResolvedLang {
  if (cookieValue && SUPPORTED_LANGS.includes(cookieValue as ResolvedLang)) {
    return cookieValue as ResolvedLang
  }
  return "ru"
}

/**
 * Extract theme from a Request's Cookie header.
 *
 * Defensive try/catch — any extraction failure (malformed cookie, unexpected
 * encoding) returns the safe default rather than throwing into the SSR
 * fetch handler.
 */
export function extractThemeFromRequest(request: Request): ResolvedTheme {
  try {
    const header = request.headers.get("cookie")
    return resolveTheme(parseCookie(header, "ue-mode"))
  } catch {
    return "light"
  }
}

/**
 * Extract language from a Request's Cookie header.
 *
 * Cookie name `ue:language` is NOT URL-encoded by browsers per RFC 6265
 * token grammar (colon is allowed in cookie names). `parseCookie` does a
 * literal string-prefix match so it reads the raw `ue:language=` segment.
 */
export function extractLangFromRequest(request: Request): ResolvedLang {
  try {
    const header = request.headers.get("cookie")
    return resolveLang(parseCookie(header, "ue:language"))
  } catch {
    return "ru"
  }
}
