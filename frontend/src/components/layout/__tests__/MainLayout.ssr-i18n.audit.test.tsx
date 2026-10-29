import { renderToString } from "react-dom/server"
import { afterEach, describe, expect, it, vi } from "vitest"
import { LanguageProvider } from "@/contexts/LanguageContext"
import { createI18nInstance } from "@/i18n/config"
import enCommon from "@/i18n/locales/en/common.json"
import ruCommon from "@/i18n/locales/ru/common.json"
import { matchesMainSkipLinkLocale } from "../../../../tests/e2e-live/ssr-common-locale.mjs"
import { MainLayout } from "../MainLayout"

vi.mock("@/hooks/useRouteType", () => ({
  useRouteType: () => ({ isCompactPage: false, hideFooter: false, isMessenger: false }),
}))
vi.mock("@/components/navbar", () => ({ default: () => <nav /> }))
vi.mock("@/components/layout/Footer", () => ({ default: () => <footer /> }))
vi.mock("@/components/motion/BackToTop", () => ({ default: () => null }))
vi.mock("@/components/layout/MobileBottomNav", () => ({ default: () => <nav /> }))

type Language = "en" | "ru"

function renderLayout(language: Language, missing: Language[] = [], sharedText?: string) {
  const instance = createI18nInstance(language).cloneInstance({ forkResourceStore: true })
  for (const candidate of ["en", "ru"] as const) {
    if (!missing.includes(candidate) && !(candidate === language && sharedText !== undefined)) {
      continue
    }
    const catalog: { skipToMain?: string } = structuredClone(
      candidate === "en" ? enCommon : ruCommon
    )
    if (missing.includes(candidate)) delete catalog.skipToMain
    if (candidate === language && sharedText !== undefined) catalog.skipToMain = sharedText
    instance.removeResourceBundle(candidate, "common")
    instance.addResourceBundle(candidate, "common", catalog)
  }
  globalThis.__ssrI18nGetter__ = () => instance
  vi.stubGlobal("window", undefined)
  try {
    return renderToString(
      <LanguageProvider>
        <div id="root">
          <MainLayout>Content</MainLayout>
        </div>
      </LanguageProvider>
    )
  } finally {
    vi.unstubAllGlobals()
    globalThis.__ssrI18nGetter__ = undefined
  }
}

function renderedSkipLink(markup: string) {
  return new DOMParser()
    .parseFromString(markup, "text/html")
    .querySelector('#root a.skip-link[href="#main-content"]')
}

afterEach(() => {
  vi.unstubAllGlobals()
  globalThis.__ssrI18nGetter__ = undefined
})

describe("AUD-137 MainLayout SSR locale landmark", () => {
  it.each([
    ["en", enCommon.skipToMain],
    ["ru", ruCommon.skipToMain],
  ] as const)("accepts the real %s request's skip link", (language, expected) => {
    const markup = renderLayout(language)
    expect(renderedSkipLink(markup)?.textContent).toBe(expected)
    expect(matchesMainSkipLinkLocale(markup, expected)).toBe(true)
  })

  it("rejects ordinary Russian fallback from the real English SSR consumer", () => {
    const markup = renderLayout("en", ["en"])
    const actual = renderedSkipLink(markup)?.textContent
    expect(actual).toBe(ruCommon.skipToMain)
    expect(actual).not.toMatch(/\b[a-z][a-z0-9_-]*:[a-z][a-z0-9_.-]*\b/iu)
    expect(matchesMainSkipLinkLocale(markup, enCommon.skipToMain)).toBe(false)
    expect(matchesMainSkipLinkLocale(markup, undefined)).toBe(false)
  })

  it("rejects i18next's unqualified key when both resources are missing", () => {
    const markup = renderLayout("en", ["en", "ru"])
    expect(renderedSkipLink(markup)?.textContent).toBe("skipToMain")
    expect(matchesMainSkipLinkLocale(markup, enCommon.skipToMain)).toBe(false)
  })

  it("accepts a translation deliberately shared by both languages", () => {
    const shared = ruCommon.skipToMain
    const markup = renderLayout("en", [], shared)
    expect(renderedSkipLink(markup)?.textContent).toBe(shared)
    expect(matchesMainSkipLinkLocale(markup, shared)).toBe(true)
  })

  it("rejects missing, duplicate or mismatched links and invalid catalog values", () => {
    const valid = renderLayout("en")
    const link = renderedSkipLink(valid)!
    expect(matchesMainSkipLinkLocale(valid, " ")).toBe(false)
    expect(matchesMainSkipLinkLocale(valid, null)).toBe(false)
    expect(matchesMainSkipLinkLocale(null, enCommon.skipToMain)).toBe(false)
    expect(matchesMainSkipLinkLocale("<main></main>", enCommon.skipToMain)).toBe(false)
    expect(matchesMainSkipLinkLocale('<div id="root"></div>', enCommon.skipToMain)).toBe(false)
    expect(matchesMainSkipLinkLocale(valid.replace(link.outerHTML, ""), enCommon.skipToMain)).toBe(
      false
    )
    expect(
      matchesMainSkipLinkLocale(
        valid.replace(link.outerHTML, link.outerHTML.repeat(2)),
        enCommon.skipToMain
      )
    ).toBe(false)
    expect(matchesMainSkipLinkLocale(valid, ruCommon.skipToMain)).toBe(false)
  })
})
