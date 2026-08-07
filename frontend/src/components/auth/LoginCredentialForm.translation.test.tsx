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
}))

type FormShape = {
  email: string
  password: string
  trustDevice: boolean
}

type FormStub = Parameters<typeof LoginCredentialForm>[0]["form"]

function Harness(): ReactNode {
  const rhf = useForm<FormShape>({
    defaultValues: { email: "", password: "", trustDevice: false },
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
    passkeyError: null,
    webauthnSupported: false,
    trustDevice: false,
    setTrustDevice: vi.fn(),
    handlePasskeyLogin: vi.fn(),
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
})
