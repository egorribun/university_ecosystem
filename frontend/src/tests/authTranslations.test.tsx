import { describe, expect, it, vi } from "vitest"
import { MemoryRouter } from "react-router-dom"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import type { ReactNode } from "react"
import { LanguageProvider, useLanguage } from "@/contexts/LanguageContext"

vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({
    login: vi.fn(),
  }),
}))

import Login from "@/pages/Login"

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

function renderLogin() {
  const user = userEvent.setup()

  const renderResult = render(
    <LanguageProvider>
      <MemoryRouter initialEntries={["/login"]}>
        <LanguageToggleHarness>
          <Login />
        </LanguageToggleHarness>
      </MemoryRouter>
    </LanguageProvider>
  )

  return { user, ...renderResult }
}

// Wave 113 SW6 polish: skipped pending Wave 114 SW1 — imports MemoryRouter from
// react-router-dom but the app migrated to TanStack Router (Wave 37). useRouterState
// returns null → TypeError. Fix requires a shared renderWithTanStackRouter test helper
// (AUDIT_WAVE113.md, memory/wave114_backlog.md item #1).
describe.skip("auth page translations", () => {
  it("renders login content for Russian and English locales", async () => {
    const { user } = renderLogin()

    const toggle = screen.getByTestId("lang-toggle")

    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument()
    expect(screen.getByRole("link", { name: "Forgot password?" })).toBeInTheDocument()
    expect(screen.getByText("No account?")).toBeInTheDocument()
    expect(screen.getByRole("link", { name: "Sign up" })).toBeInTheDocument()

    await user.click(toggle)

    expect(await screen.findByRole("heading", { name: "Вход" })).toBeInTheDocument()
    expect(screen.getByRole("link", { name: "Забыли пароль?" })).toBeInTheDocument()
    expect(screen.getByText("Нет аккаунта?")).toBeInTheDocument()
    expect(screen.getByRole("link", { name: "Зарегистрироваться" })).toBeInTheDocument()

    await user.click(toggle)

    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument()
    expect(screen.getByRole("link", { name: "Sign up" })).toBeInTheDocument()
  })
})
