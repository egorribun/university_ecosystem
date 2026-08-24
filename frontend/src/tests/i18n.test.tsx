import { describe, expect, it } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { LanguageProvider, useLanguage } from "@/contexts/LanguageContext"
import { useTranslation } from "react-i18next"

describe("i18n integration", () => {
  function Harness() {
    const { language, setLanguage } = useLanguage()
    const { t } = useTranslation("auth")
    return (
      <div>
        <span data-testid="label">{t("login.title")}</span>
        <button type="button" onClick={() => setLanguage(language === "ru" ? "en" : "ru")}>
          toggle
        </button>
      </div>
    )
  }

  it("renders default locale and responds to language changes", async () => {
    const user = userEvent.setup()
    render(
      <LanguageProvider>
        <Harness />
      </LanguageProvider>
    )

    expect(await screen.findByText("Вход")).toBeInTheDocument()
    expect(document.documentElement.getAttribute("lang")).toBe("ru")

    await user.click(screen.getByText("toggle"))

    expect(await screen.findByText("Sign in")).toBeInTheDocument()
    expect(document.documentElement.getAttribute("lang")).toBe("en")

    await user.click(screen.getByText("toggle"))

    expect(await screen.findByText("Вход")).toBeInTheDocument()
    expect(document.documentElement.getAttribute("lang")).toBe("ru")
  })
})
