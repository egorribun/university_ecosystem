import React, { createContext, useContext, useEffect, useState } from "react"

type Theme = "light" | "dark" | "system"

interface ThemeContextType {
  theme: Theme
  setTheme: (theme: Theme) => void
  resolvedTheme: "light" | "dark"
}

const ThemeContext = createContext<ThemeContextType | undefined>(undefined)

const VALID_THEMES: ReadonlySet<Theme> = new Set(["light", "dark", "system"])

const THEME_COOKIE_NAME = "ue-mode"
const COOKIE_MAX_AGE_SECONDS = 365 * 24 * 60 * 60 // 1 year

const readStoredTheme = (): Theme => {
  try {
    const raw = localStorage.getItem("ue-mode")
    return raw && VALID_THEMES.has(raw as Theme) ? (raw as Theme) : "system"
  } catch {
    return "system"
  }
}

// Wave 127 SW2 — cookie-mirror for SSR theme parity. Server (src/server.ts)
// reads this cookie + exposes via globalThis.__ssrThemeGetter__ (W127 SW4);
// RootShell renders <html class="dark"> server-side from the cookie value
// (W127 SW5), eliminating FOUC on returning users.
//
// Cookie attrs:
//   - Path=/ → sent on all routes (SSR may serve any page)
//   - SameSite=Lax → cookie sent on cross-site GET (user clicks external
//     link to /dashboard), critical for SSR perf wins on cold-load
//   - Secure conditional on HTTPS so dev on http://localhost still works
//   - 1-year Max-Age — theme is a long-lived UI preference
const setThemeCookie = (value: Theme) => {
  const isSecure = typeof location !== "undefined" && location.protocol === "https:"
  const secureAttr = isSecure ? "; Secure" : ""
  document.cookie = `${THEME_COOKIE_NAME}=${encodeURIComponent(value)}; Path=/; Max-Age=${COOKIE_MAX_AGE_SECONDS}; SameSite=Lax${secureAttr}`
}

const readCookieValue = (name: string): string | null => {
  const parts = document.cookie.split(/;\s*/)
  const prefix = `${name}=`
  for (const part of parts) {
    if (part.startsWith(prefix)) {
      try {
        return decodeURIComponent(part.slice(prefix.length))
      } catch {
        return null
      }
    }
  }
  return null
}

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setThemeState] = useState<Theme>(readStoredTheme)

  const [resolvedTheme, setResolvedTheme] = useState<"light" | "dark">("light")

  useEffect(() => {
    const root = window.document.documentElement
    const body = window.document.body

    const applyTheme = (t: "light" | "dark") => {
      root.classList.remove("light", "dark")
      body.classList.remove("light", "dark")
      root.classList.add(t)
      body.classList.add(t)
      root.dataset.colorScheme = t
      body.dataset.colorScheme = t
      setResolvedTheme(t)
    }

    if (theme === "system") {
      const mediaQuery = window.matchMedia?.("(prefers-color-scheme: dark)")

      if (mediaQuery) {
        const handleChange = () => {
          applyTheme(mediaQuery.matches ? "dark" : "light")
        }
        handleChange()
        mediaQuery.addEventListener("change", handleChange)
        return () => mediaQuery.removeEventListener("change", handleChange)
      } else {
        applyTheme("light")
      }
    } else {
      applyTheme(theme)
    }
  }, [theme])

  const setTheme = (t: Theme) => {
    setThemeState(t)
    try {
      localStorage.setItem("ue-mode", t)
    } catch {
      // ignore quota / private-browsing failures
    }
    // Wave 127 SW2 — cookie-mirror alongside localStorage write
    setThemeCookie(t)
  }

  // Wave 127 SW2 — backfill cookie for returning users who have localStorage
  // but no cookie (post-W127 deploy migration path). Only writes when cookie
  // is missing AND the in-memory theme value is non-default.
  useEffect(() => {
    if (readCookieValue(THEME_COOKIE_NAME) === null) {
      setThemeCookie(theme)
    }
  }, [theme])

  return (
    <ThemeContext.Provider value={{ theme, setTheme, resolvedTheme }}>
      {children}
    </ThemeContext.Provider>
  )
}

export function useTheme() {
  const context = useContext(ThemeContext)
  if (context === undefined) {
    throw new Error("useTheme must be used within a ThemeProvider")
  }
  return context
}
