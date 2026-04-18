import { describe, expect, it, vi } from "vitest"
import { screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import type { ReactNode } from "react"

import { useLanguage } from "@/contexts/LanguageContext"
import { renderWithRouter } from "@/tests/helpers/renderWithRouter"

vi.mock("@/contexts/AuthContext", () => ({
  // Passthrough AuthProvider so renderWithRouter's import still resolves while
  // useAuth is mocked for this translations-focused test.
  AuthProvider: ({ children }: { children: ReactNode }) => children,
  useAuth: () => ({
    login: vi.fn(),
  }),
}))

import Login from "@/pages/Login"

function LoginWithLanguageToggle() {
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
      <Login />
    </>
  )
}

async function renderLogin() {
  const user = userEvent.setup()
  const result = await renderWithRouter({
    ui: LoginWithLanguageToggle,
    path: "/login",
    initialPath: "/login",
  })
  return { user, ...result }
}

describe("auth page translations", () => {
  it("renders login content for Russian and English locales", async () => {
    const { user } = await renderLogin()

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
