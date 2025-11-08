import { useEffect } from "react"
import { render, screen } from "@testing-library/react"
import { afterEach, describe, expect, it } from "vitest"

import MapFallback from "@/components/MapFallback"
import { LanguageProvider, useLanguage, type SupportedLanguage } from "@/contexts/LanguageContext"

const storageKey = "ue:language"

function LanguageSetter({ language }: { language: SupportedLanguage }) {
  const { setLanguage } = useLanguage()

  useEffect(() => {
    setLanguage(language)
  }, [language, setLanguage])

  return null
}

function renderWithLanguage(language: SupportedLanguage) {
  window.localStorage.setItem(storageKey, language)
  render(
    <LanguageProvider>
      <LanguageSetter language={language} />
      <MapFallback reason="load-error" />
    </LanguageProvider>
  )
}

describe("MapFallback", () => {
  afterEach(() => {
    window.localStorage.removeItem(storageKey)
  })

  it("renders localized campus points for english", async () => {
    renderWithLanguage("en")

    expect(
      await screen.findByRole("heading", { name: "Main building" })
    ).toBeInTheDocument()
    expect(
      screen.getByText(
        "Admissions, student services, and major lecture halls are located here."
      )
    ).toBeInTheDocument()
  })

  it("renders localized campus points for russian", async () => {
    renderWithLanguage("ru")

    expect(
      await screen.findByRole("heading", { name: "Главный корпус" })
    ).toBeInTheDocument()
    expect(
      screen.getByText(
        "Здесь находятся приёмная комиссия, студенческие сервисы и основные лекционные аудитории."
      )
    ).toBeInTheDocument()
  })
})
