import { renderToString } from "react-dom/server"
import { afterEach, describe, expect, it, vi } from "vitest"
import { LanguageProvider } from "@/contexts/LanguageContext"
import { createI18nInstance } from "@/i18n/config"
import enNews from "@/i18n/locales/en/news.json"
import ruNews from "@/i18n/locales/ru/news.json"
import { NewsHeader } from "../NewsHeader"
import { matchesNewsSearchLocale } from "../../../../../tests/e2e-live/ssr-news-locale.mjs"

type Language = "en" | "ru"

function renderHeader(language: Language, missing: Language[] = [], sharedPlaceholder?: string) {
  // Fork the request instance's store, then replace complete namespace copies.
  // The application catalog and the other request instances remain untouched.
  const instance = createI18nInstance(language).cloneInstance({ forkResourceStore: true })
  for (const candidate of ["en", "ru"] as const) {
    if (!missing.includes(candidate) && !(candidate === language && sharedPlaceholder)) continue
    const catalog: { search: { placeholder?: string } } = structuredClone(
      candidate === "en" ? enNews : ruNews
    )
    if (missing.includes(candidate)) delete catalog.search.placeholder
    if (candidate === language && sharedPlaceholder) catalog.search.placeholder = sharedPlaceholder
    instance.removeResourceBundle(candidate, "news")
    instance.addResourceBundle(candidate, "news", catalog)
  }
  globalThis.__ssrI18nGetter__ = () => instance
  vi.stubGlobal("window", undefined)
  try {
    return renderToString(
      <LanguageProvider>
        <div id="root">
          <div className="news-theme">
            <NewsHeader
              onAddClick={() => undefined}
              isAdmin={false}
              searchQuery=""
              onSearchChange={() => undefined}
              activeCategory="all"
              onCategoryChange={() => undefined}
              sortMode="newest"
              onSortChange={() => undefined}
            />
          </div>
        </div>
      </LanguageProvider>
    )
  } finally {
    vi.unstubAllGlobals()
    globalThis.__ssrI18nGetter__ = undefined
  }
}

function renderedSearch(markup: string) {
  return new DOMParser()
    .parseFromString(markup, "text/html")
    .querySelector("#root .news-theme header input[placeholder]")
}

afterEach(() => {
  vi.unstubAllGlobals()
  globalThis.__ssrI18nGetter__ = undefined
})

describe("AUD-137 News SSR locale landmark", () => {
  it.each([
    ["en", enNews.search.placeholder],
    ["ru", ruNews.search.placeholder],
  ] as const)("accepts the actual %s request's search placeholder", (language, expected) => {
    const markup = renderHeader(language)
    expect(renderedSearch(markup)?.getAttribute("placeholder")).toBe(expected)
    expect(renderedSearch(markup)?.getAttribute("aria-label")).toBe(expected)
    expect(matchesNewsSearchLocale(markup, expected)).toBe(true)
  })

  it("rejects ordinary Russian fallback from the real English SSR consumer", () => {
    const markup = renderHeader("en", ["en"])
    const actual = renderedSearch(markup)?.getAttribute("placeholder")
    expect(actual).toBe(ruNews.search.placeholder)
    expect(actual).not.toMatch(/\b[a-z][a-z0-9_-]*:[a-z][a-z0-9_.-]*\b/iu)
    expect(matchesNewsSearchLocale(markup, enNews.search.placeholder)).toBe(false)
    expect(matchesNewsSearchLocale(markup, undefined)).toBe(false)
  })

  it("rejects i18next's unqualified missing key when neither language contains it", () => {
    const markup = renderHeader("en", ["en", "ru"])
    expect(renderedSearch(markup)?.getAttribute("placeholder")).toBe("search.placeholder")
    expect(matchesNewsSearchLocale(markup, enNews.search.placeholder)).toBe(false)
  })

  it("accepts a translation deliberately shared by both languages", () => {
    const shared = ruNews.search.placeholder
    const markup = renderHeader("en", [], shared)
    expect(renderedSearch(markup)?.getAttribute("placeholder")).toBe(shared)
    expect(matchesNewsSearchLocale(markup, shared)).toBe(true)
  })

  it("rejects absent or ambiguous landmarks and invalid catalog values", () => {
    const valid = renderHeader("en")
    const input = renderedSearch(valid)!
    input.removeAttribute("aria-label")
    expect(
      matchesNewsSearchLocale(
        input.ownerDocument.documentElement.outerHTML,
        enNews.search.placeholder
      )
    ).toBe(false)
    expect(matchesNewsSearchLocale(valid, " ")).toBe(false)
    expect(matchesNewsSearchLocale(valid, null)).toBe(false)
    expect(matchesNewsSearchLocale(null, enNews.search.placeholder)).toBe(false)
    expect(matchesNewsSearchLocale("<main></main>", enNews.search.placeholder)).toBe(false)
    expect(matchesNewsSearchLocale('<div id="root"></div>', enNews.search.placeholder)).toBe(false)
    expect(
      matchesNewsSearchLocale(
        valid.replace("</header>", `${input.outerHTML}</header>`),
        enNews.search.placeholder
      )
    ).toBe(false)
  })
})
