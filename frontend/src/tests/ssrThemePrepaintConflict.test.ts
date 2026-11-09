import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import { runInContext } from "node:vm"
import { JSDOM } from "jsdom"
import { expect, it } from "vitest"

import { extractThemeFromRequest } from "@/ssrTheme"

const script = readFileSync(resolve(process.cwd(), "public/theme-init.js"), "utf8")

it.each([
  ["dark", "dark", "light", true, false],
  ["dark", "dark", "system", false, false],
  ["dark", "dark", null, false, false],
  ["dark", "dark", "invalid", false, false],
  ["dark", "dark", "system", null, false],
  ["dark", "dark", "dark", false, true],
  ["light", "light", "dark", false, true],
  ["system", "light", "system", true, true],
  ["system", "light", "system", false, false],
] as const)(
  "resolves SSR cookie %s to %s, then storage %s with system dark=%s",
  (cookie, expectedServerTheme, stored, systemDark, expectedDark) => {
    const request = new Request("https://example.test/", {
      headers: { cookie: `ue-mode=${cookie}` },
    })
    const serverTheme = extractThemeFromRequest(request)
    expect(serverTheme).toBe(expectedServerTheme)

    // RootShell uses the resolved cookie to put only the dark class on html.
    // Keep an unrelated shell class to verify that theme correction preserves it.
    const serverClasses = serverTheme === "dark" ? "dark lhci-mode" : "lhci-mode"
    const dom = new JSDOM(`<!doctype html><html class="${serverClasses}"><head></head></html>`, {
      url: "https://example.test/",
      runScripts: "outside-only",
    })

    try {
      dom.window.document.cookie = `ue-mode=${cookie}; Path=/`
      dom.window.document.cookie = "ue:language=en; Path=/"
      if (stored !== null) dom.window.localStorage.setItem("ue-mode", stored)
      Object.defineProperty(dom.window, "matchMedia", {
        configurable: true,
        value:
          systemDark === null
            ? undefined
            : (query: string) => ({
                matches: query === "(prefers-color-scheme: dark)" && systemDark,
              }),
      })

      expect(dom.window.document.documentElement.classList.contains("dark")).toBe(
        serverTheme === "dark"
      )
      runInContext(script, dom.getInternalVMContext(), { timeout: 1000 })

      const html = dom.window.document.documentElement
      expect(html.classList.contains("dark")).toBe(expectedDark)
      expect(html.classList.contains("lhci-mode")).toBe(true)
      expect(html.lang).toBe("en")
      expect(dom.window.localStorage.getItem("ue-mode")).toBe(stored)
      expect(dom.window.document.cookie).toContain(`ue-mode=${cookie}`)
      expect(Reflect.get(dom.window, "__UE_THEME_INIT_SCRIPT_RAN__")).toBe(true)
    } finally {
      dom.window.close()
    }
  }
)
