/** @vitest-environment node */

import { renderToString } from "react-dom/server"
import { describe, expect, it, vi } from "vitest"

vi.mock("@/i18n/config", () => ({
  default: { language: "" },
}))

import { LanguageProvider, useLanguage } from "@/contexts/LanguageContext"

const Probe = () => <span>{useLanguage().language}</span>

describe("LanguageContext SSR guard", () => {
  it("uses the fallback language when i18n has not selected one", () => {
    expect(typeof window).toBe("undefined")
    expect(
      renderToString(
        <LanguageProvider>
          <Probe />
        </LanguageProvider>
      )
    ).toContain("<span>en</span>")
  })
})
