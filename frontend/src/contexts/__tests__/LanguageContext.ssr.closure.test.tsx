/** @vitest-environment node */

import { renderToString } from "react-dom/server"
import { afterEach, describe, expect, it } from "vitest"

import { LanguageProvider, useLanguage } from "@/contexts/LanguageContext"
import { createI18nInstance } from "@/i18n/config"

const Probe = () => <span>{useLanguage().language}</span>

describe("LanguageContext SSR guard", () => {
  afterEach(() => {
    delete globalThis.__ssrI18nGetter__
  })

  it("uses the request-scoped language instance during SSR", () => {
    expect(typeof window).toBe("undefined")
    const requestI18n = createI18nInstance("ru")
    globalThis.__ssrI18nGetter__ = () => requestI18n
    expect(
      renderToString(
        <LanguageProvider>
          <Probe />
        </LanguageProvider>
      )
    ).toContain("<span>ru</span>")
  })
})
