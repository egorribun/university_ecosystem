import { describe, expect, it } from "vitest"
import { MemoryRouter } from "react-router-dom"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import Footer from "@/components/Footer"
import MobileBottomNav from "@/components/MobileBottomNav"
import { LanguageProvider, useLanguage } from "@/contexts/LanguageContext"
import type { ReactNode } from "react"

function LanguageToggleHarness({ children }: { children: ReactNode }) {
  const { language, setLanguage } = useLanguage()

  return (
    <>
      <button
        type="button"
        data-testid="lang-toggle"
        onClick={() => setLanguage(language === "ru" ? "en" : "ru")}
      >
        toggle
      </button>
      {children}
    </>
  )
}

function renderWithLanguage(ui: ReactNode, initialEntry = "/dashboard") {
  const user = userEvent.setup()

  const renderResult = render(
    <LanguageProvider>
      <MemoryRouter initialEntries={[initialEntry]}>
        <LanguageToggleHarness>{ui}</LanguageToggleHarness>
      </MemoryRouter>
    </LanguageProvider>
  )

  return { user, ...renderResult }
}

describe("navigation components translations", () => {
  it("updates footer translations when switching languages", async () => {
    const { user } = renderWithLanguage(<Footer />)

    const toggle = screen.getByTestId("lang-toggle")

    expect(await screen.findByText("Explore")).toBeInTheDocument()
    const year = new Date().getFullYear()
    expect(
      screen.getByText((content) => content.includes(`© ${year} GUU Ecosystem`))
    ).toBeInTheDocument()

    await user.click(toggle)

    expect(await screen.findByText("Разделы")).toBeInTheDocument()
    expect(
      screen.getByText((content) => content.includes(`© ${year} Экосистема ГУУ`))
    ).toBeInTheDocument()

    await user.click(toggle)

    expect(await screen.findByText("Explore")).toBeInTheDocument()
  })

  it("switches bottom navigation labels with locale", async () => {
    const { user } = renderWithLanguage(<MobileBottomNav />)

    const toggle = screen.getByTestId("lang-toggle")

    expect(await screen.findByRole("link", { name: "Home" })).toBeInTheDocument()
    expect(screen.getByRole("link", { name: "Schedule" })).toBeInTheDocument()

    await user.click(toggle)

    expect(await screen.findByRole("link", { name: "Главная" })).toBeInTheDocument()
    expect(screen.getByRole("link", { name: "Расписание" })).toBeInTheDocument()
  })
})

