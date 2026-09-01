import { type ReactNode } from "react"
import { useForm } from "react-hook-form"
import { describe, expect, it, vi } from "vitest"
import { screen } from "@testing-library/react"

import { renderWithRouter } from "@/tests/helpers/renderWithRouter"
import { LoginCredentialForm } from "./LoginCredentialForm"

const translation = vi.hoisted(() => {
  const t = vi.fn((key: string, options?: Record<string, unknown>) => {
    if (key === "auth:actions.holdReveal") return undefined
    if (key === "auth:actions.showPassword") {
      return undefined
    }
    if (typeof options?.suggestion === "string") {
      return `${key}: ${options.suggestion}`
    }
    return key
  })
  return { t }
})

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: translation.t }),
  I18nextProvider: ({ children }: { children?: ReactNode }) => <>{children}</>,
}))

type FormShape = {
  email: string
  password: string
  rememberEmail: boolean
  trustDevice: boolean
}

type FormStub = Parameters<typeof LoginCredentialForm>[0]["form"]

function Harness(): ReactNode {
  const rhf = useForm<FormShape>({
    defaultValues: { email: "", password: "", rememberEmail: false, trustDevice: false },
  })
  const form = {
    form: rhf,
    caps: false,
    setCaps: vi.fn(),
    showPassword: false,
    setShowPassword: vi.fn(),
    emailSuggestion: null,
    applySuggestion: vi.fn(),
    handleEmailBlur: vi.fn(),
    activeEmail: "",
    submitting: false,
    submitError: undefined,
    onSubmit: vi.fn(),
    pendingMfa: null,
    savedEmail: "",
  } as FormStub
  return <LoginCredentialForm form={form} />
}

describe("LoginCredentialForm translation fallbacks", () => {
  it("handles optional title and aria-label translations", async () => {
    await renderWithRouter({
      ui: Harness,
      extraRoutes: [
        { path: "/forgot-password", Component: () => <div>forgot</div> },
        { path: "/register", Component: () => <div>register</div> },
      ],
    })

    const button = screen.getAllByRole("button")[0]
    expect(button).not.toHaveAttribute("title")
    expect(button).not.toHaveAttribute("aria-label")
  })

  it("preserves fallback copy, password toggle labels, and checkbox semantics", async () => {
    const previous = translation.t.getMockImplementation()
    translation.t.mockImplementation((key: string, options?: Record<string, unknown>) => {
      if (key === "auth:login.subtitle") return String(options?.defaultValue ?? "")
      return key
    })

    try {
      await renderWithRouter({
        ui: Harness,
        extraRoutes: [
          { path: "/forgot-password", Component: () => <div>forgot</div> },
          { path: "/register", Component: () => <div>register</div> },
        ],
      })

      expect(screen.getByText("Sign in to continue your university journey")).toBeInTheDocument()

      const reveal = screen.getByRole("button", { name: "auth:actions.showPassword" })
      expect(reveal).toHaveAttribute("title", "auth:actions.showPassword")
      expect(reveal).toHaveAttribute("aria-label", "auth:actions.showPassword")
      expect(reveal).toHaveTextContent("auth:actions.showPassword")

      expect(
        screen.getByRole("checkbox", { name: "auth:actions.rememberEmail" })
      ).toBeInTheDocument()
      expect(screen.getByRole("checkbox", { name: "auth:actions.trustDevice" })).toHaveAttribute(
        "aria-describedby",
        "trust-device-description"
      )

      const register = screen.getByRole("link", { name: "auth:login.ctaRegister" })
      expect(register.parentElement?.textContent).toBe(
        "auth:login.noAccount auth:login.ctaRegister"
      )
    } finally {
      translation.t.mockImplementation(previous!)
    }
  })
})
