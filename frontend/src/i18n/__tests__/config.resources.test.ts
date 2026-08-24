import { describe, expect, it, vi } from "vitest"

import {
  buildResources,
  createI18nInstance,
  localeModules,
  namespaces,
  resolveBootstrapLanguage,
  resources,
  supportedLngs,
} from "@/i18n/config"

describe("bundled i18n resources", () => {
  it("contains every declared namespace for every supported language", () => {
    for (const language of supportedLngs) {
      for (const namespace of namespaces) {
        expect(localeModules[`./locales/${language}/${namespace}.json`]).toBeDefined()
        expect(resources[language]?.[namespace]).toBeDefined()
      }
    }
  })

  it("initializes translated resources synchronously", () => {
    const russian = createI18nInstance("ru")
    const english = createI18nInstance("en")

    expect(russian.isInitialized).toBe(true)
    expect(english.isInitialized).toBe(true)
    expect(russian.t("navigation:brandName")).toBe("Экосистема ГУУ")
    expect(english.t("navigation:brandName")).toBe("GUU Ecosystem")
  })

  it("keeps request-scoped instances isolated", async () => {
    const russian = createI18nInstance("ru")
    const english = createI18nInstance("en")

    expect(russian.language).toBe("ru")
    expect(english.language).toBe("en")
    await russian.changeLanguage("en")

    expect(russian.language).toBe("en")
    expect(english.language).toBe("en")
    await english.changeLanguage("ru")
    expect(russian.language).toBe("en")
    expect(english.language).toBe("ru")
  })

  it("ignores malformed locale module paths and empty segments", () => {
    const resource = { greeting: "hello" }

    expect(
      buildResources({
        "not-a-locale-module": resource,
        "./locales//common.json": resource,
        "./locales/en/.json": resource,
        "./locales/en/common.json": resource,
      })
    ).toEqual({ en: { common: resource } })
  })

  it("resolves the bootstrap language from supported and unsupported selections", () => {
    window.__UE_SELECTED_LANG__ = "en"
    expect(resolveBootstrapLanguage()).toBe("en")

    Object.defineProperty(window, "__UE_SELECTED_LANG__", {
      configurable: true,
      value: "de",
    })
    expect(resolveBootstrapLanguage()).toBe("ru")
  })

  it("uses the fallback during server rendering", () => {
    vi.stubGlobal("window", undefined)
    expect(resolveBootstrapLanguage()).toBe("ru")
    vi.unstubAllGlobals()
  })
})
