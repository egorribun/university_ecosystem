/** @vitest-environment node */

import { renderToString } from "react-dom/server"
import { describe, expect, it } from "vitest"

import { LanguageProvider, useLanguage } from "@/contexts/LanguageContext"

const Probe = () => <span>{useLanguage().language}</span>

describe("LanguageContext SSR guard", () => {
  it("uses i18n/fallback language without touching browser globals", () => {
    expect(typeof window).toBe("undefined")
    expect(
      renderToString(
        <LanguageProvider>
          <Probe />
        </LanguageProvider>
      )
    ).toMatch(/<span>(en|ru)<\/span>/)
  })
})
