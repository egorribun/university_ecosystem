import React, { createContext, useContext, useEffect, useState } from "react"

type Theme = "light" | "dark" | "system"

interface ThemeContextType {
  theme: Theme
  setTheme: (theme: Theme) => void
  resolvedTheme: "light" | "dark"
}

const ThemeContext = createContext<ThemeContextType | undefined>(undefined)

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setThemeState] = useState<Theme>(() => {
    return (localStorage.getItem("ue-mode") as Theme) || "system"
  })

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
      const handleChange = () => {
        if (!mediaQuery) return
        applyTheme(mediaQuery.matches ? "dark" : "light")
      }

      if (mediaQuery) {
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
    localStorage.setItem("ue-mode", t)
  }

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




