/**
 * @fileoverview Wave 129 SW1 — i18n locale resolver for TanStack Router loaders.
 *
 * Loaders run in BOTH server (SSR / build-time prerender) and client (SPA
 * navigation) contexts. This helper resolves the user's language from the
 * appropriate source per environment:
 *
 *   - SSR path: `globalThis.__ssrLangGetter__` (W127 SW4 — wired in
 *     `src/server.ts` from `ue:language` HttpOnly cookie via AsyncLocalStorage).
 *   - Client path: `localStorage.getItem("ue:language")` — mirror of the
 *     cookie set by `src/contexts/LanguageContext.tsx` (W127 SW3).
 *   - Fallback: `"ru"` (matches `fallbackLng` in `i18n/metadata.ts` +
 *     ResolvedLang default in `src/ssrTheme.ts:resolveLang`).
 *
 * Used by W129 per-route SSR loaders for /events, /events/$id, /news,
 * /news/$id to choose the correct cursor-pagination cache key for
 * prefetchInfiniteQuery / ensureQueryData calls.
 */
import type { ResolvedLang } from "@/ssrTheme"

const SUPPORTED_LANGS: readonly ResolvedLang[] = ["ru", "en"]
const STORAGE_KEY = "ue:language"
const DEFAULT_LANG: ResolvedLang = "ru"

export const resolveLoaderLang = (): ResolvedLang => {
  // SSR path — server.ts populates the getter per-request from the
  // `ue:language` cookie. During build-time prerender the request has no
  // cookie header, getter returns DEFAULT_LANG.
  const ssrLang = globalThis.__ssrLangGetter__?.()
  if (ssrLang) return ssrLang

  // Client path — read the localStorage mirror of the cookie. Wrapped in
  // try/catch for Safari private-browsing (RZ-31-03 pattern).
  if (typeof window !== "undefined") {
    try {
      const stored = localStorage.getItem(STORAGE_KEY)
      if (stored && SUPPORTED_LANGS.includes(stored as ResolvedLang)) {
        return stored as ResolvedLang
      }
    } catch {
      // Safari private browsing — localStorage throws on access
    }
  }

  return DEFAULT_LANG
}
