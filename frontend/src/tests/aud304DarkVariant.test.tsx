import { act, fireEvent, render, screen } from "@testing-library/react"
import postcss, { type Rule } from "postcss"
import { afterEach, beforeEach, expect, it, vi } from "vitest"

import { ThemeProvider, useTheme } from "@/contexts/ThemeContext"
import compiledCss from "@/styles/tailwind.css?inline"

const stylesheet = postcss.parse(compiledCss)

function backgroundRules(selectorFragment: string, valueFragment: string): Rule[] {
  const rules: Rule[] = []
  stylesheet.walkRules((rule) => {
    if (
      rule.selector.includes(selectorFragment) &&
      rule.nodes?.some(
        (node) =>
          node.type === "decl" &&
          node.prop === "background-color" &&
          node.value.includes(valueFragment)
      )
    ) {
      rules.push(rule)
    }
  })
  return rules
}

function expectClassControlledBackground(element: HTMLElement, rules: Rule[], dark: boolean) {
  expect(rules.length).toBeGreaterThan(0)
  for (const rule of rules) {
    let parent = rule.parent
    while (parent) {
      if (parent.type === "atrule" && parent.name === "media") {
        expect(parent.params).not.toMatch(/prefers-color-scheme/u)
      }
      parent = parent.parent
    }
  }
  expect(rules.some((rule) => element.matches(rule.selector))).toBe(dark)
}

function ThemeProbes() {
  const { setTheme } = useTheme()
  return (
    <>
      <div data-testid="utility" className="dark:bg-page" />
      <div data-testid="applied" className="skeleton" />
      <button type="button" onClick={() => setTheme("dark")}>
        Dark
      </button>
      <button type="button" onClick={() => setTheme("system")}>
        System
      </button>
    </>
  )
}

function mediaQuery(initialDark: boolean) {
  let dark = initialDark
  const listeners = new Set<() => void>()
  const media = {
    get matches() {
      return dark
    },
    addEventListener: (_type: string, listener: () => void) => {
      listeners.add(listener)
    },
    removeEventListener: (_type: string, listener: () => void) => {
      listeners.delete(listener)
    },
  }
  vi.spyOn(window, "matchMedia").mockReturnValue(media as unknown as MediaQueryList)
  return (nextDark: boolean) => {
    dark = nextDark
    act(() => listeners.forEach((listener) => listener()))
  }
}

const utilityRules = backgroundRules(CSS.escape("dark:bg-page"), "var(--color-page)")
const appliedRules = backgroundRules(".skeleton", "var(--opacity-medium)")

function expectProbeStyles(dark: boolean) {
  expectClassControlledBackground(screen.getByTestId("utility"), utilityRules, dark)
  expectClassControlledBackground(screen.getByTestId("applied"), appliedRules, dark)
}

let htmlClass: string | null
let bodyClass: string | null
let htmlColorScheme: string | null
let bodyColorScheme: string | null
let storedTheme: string | null
let themeCookie: string | undefined

beforeEach(() => {
  htmlClass = document.documentElement.getAttribute("class")
  bodyClass = document.body.getAttribute("class")
  htmlColorScheme = document.documentElement.getAttribute("data-color-scheme")
  bodyColorScheme = document.body.getAttribute("data-color-scheme")
  storedTheme = localStorage.getItem("ue-mode")
  themeCookie = document.cookie.split(/;\s*/u).find((cookie) => cookie.startsWith("ue-mode="))
  document.documentElement.classList.remove("dark", "light")
  document.body.classList.remove("dark", "light")
  localStorage.removeItem("ue-mode")
  document.cookie = "ue-mode=; Max-Age=0; Path=/"
})

afterEach(() => {
  for (const [element, name, value] of [
    [document.documentElement, "class", htmlClass],
    [document.body, "class", bodyClass],
    [document.documentElement, "data-color-scheme", htmlColorScheme],
    [document.body, "data-color-scheme", bodyColorScheme],
  ] as const) {
    if (value === null) element.removeAttribute(name)
    else element.setAttribute(name, value)
  }
  if (storedTheme === null) localStorage.removeItem("ue-mode")
  else localStorage.setItem("ue-mode", storedTheme)
  document.cookie = themeCookie ? `${themeCookie}; Path=/` : "ue-mode=; Max-Age=0; Path=/"
  vi.restoreAllMocks()
})

it.each([
  ["light", false, false],
  ["light", true, false],
  ["dark", false, true],
  ["dark", true, true],
  ["system", false, false],
  ["system", true, true],
] as const)(
  "matches compiled dark utilities for %s preference with system dark=%s",
  (preference, systemDark, expectedDark) => {
    localStorage.setItem("ue-mode", preference)
    mediaQuery(systemDark)
    render(
      <ThemeProvider>
        <ThemeProbes />
      </ThemeProvider>
    )

    expect(document.documentElement.classList.contains("dark")).toBe(expectedDark)
    expect(document.body.classList.contains("dark")).toBe(expectedDark)
    expectProbeStyles(expectedDark)
  }
)

it("updates compiled dark selectors on system changes and keeps an explicit choice", () => {
  localStorage.setItem("ue-mode", "system")
  const setSystemDark = mediaQuery(false)
  render(
    <ThemeProvider>
      <ThemeProbes />
    </ThemeProvider>
  )

  expectProbeStyles(false)
  setSystemDark(true)
  expectProbeStyles(true)
  setSystemDark(false)
  expectProbeStyles(false)
  fireEvent.click(screen.getByRole("button", { name: "Dark" }))
  setSystemDark(true)
  expectProbeStyles(true)
  setSystemDark(false)
  expectProbeStyles(true)
  expect(localStorage.getItem("ue-mode")).toBe("dark")
  fireEvent.click(screen.getByRole("button", { name: "System" }))
  expectProbeStyles(false)
  expect(localStorage.getItem("ue-mode")).toBe("system")
})

it("matches the compiled variants when the server supplies only the html dark class", () => {
  document.documentElement.classList.add("dark")
  const utility = document.createElement("div")
  utility.className = "dark:bg-page"
  const applied = document.createElement("div")
  applied.className = "skeleton"
  document.body.append(utility, applied)
  try {
    expectClassControlledBackground(utility, utilityRules, true)
    expectClassControlledBackground(applied, appliedRules, true)
  } finally {
    utility.remove()
    applied.remove()
  }
})
