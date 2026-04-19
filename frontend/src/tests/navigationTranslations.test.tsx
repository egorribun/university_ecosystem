import { describe, expect, it } from "vitest"
import { screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import type { ComponentType, ReactNode } from "react"

import Footer from "@/components/layout/Footer"
import MobileBottomNav from "@/components/layout/MobileBottomNav"
import { useLanguage } from "@/contexts/LanguageContext"
import { renderWithRouter } from "@/tests/helpers/renderWithRouter"

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

async function renderWithLanguage(Ui: ComponentType, initialEntry = "/dashboard") {
  const user = userEvent.setup()

  const Wrapped = () => (
    <LanguageToggleHarness>
      <Ui />
    </LanguageToggleHarness>
  )

  const result = await renderWithRouter({
    ui: Wrapped,
    path: initialEntry,
    initialPath: initialEntry,
  })

  return { user, ...result }
}

describe("navigation components translations", () => {
  it("updates footer translations when switching languages", async () => {
    const { user } = await renderWithLanguage(Footer)

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
    const { user } = await renderWithLanguage(MobileBottomNav)

    const toggle = screen.getByTestId("lang-toggle")

    expect(await screen.findByRole("link", { name: "Home" })).toBeInTheDocument()
    expect(screen.getByRole("link", { name: "Schedule" })).toBeInTheDocument()

    await user.click(toggle)

    expect(await screen.findByRole("link", { name: "Главная" })).toBeInTheDocument()
    expect(screen.getByRole("link", { name: "Расписание" })).toBeInTheDocument()
  })
})
