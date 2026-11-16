import { act, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

const state = vi.hoisted(() => ({
  auth: { user: { id: "account-a" }, loading: false },
  totpError: "Wait for verification",
  emailMfaError: "Wait for verification",
  confirmTotp: vi.fn(),
  confirmEmail: vi.fn(),
}))

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))
vi.mock("@/contexts/AuthContext", () => ({ useAuth: () => state.auth }))
vi.mock("@/pages/settings/hooks", () => ({
  useEmailChange: () => ({}),
  usePasswordChange: () => ({}),
  useTotpEnrollment: () => ({
    totpDraft: { secret: crypto.randomUUID(), otpauth_url: "otpauth://totp/test" },
    totpBusy: false,
    totpError: state.totpError,
    activeTotp: [],
    handleConfirmTotp: state.confirmTotp,
  }),
  useEmailMfa: () => ({
    emailChallenge: { method: "email_otp", challenge_token: "challenge-token" },
    emailMfaBusy: false,
    emailMfaError: state.emailMfaError,
    handleConfirmEmailMfa: state.confirmEmail,
  }),
}))
vi.mock("@/pages/settings/sections", () => ({
  EmailSection: () => null,
  PasswordSection: () => null,
}))
vi.mock("@/components/settings", () => ({
  Alert: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AccordionSection: ({ children }: { children: React.ReactNode }) => <section>{children}</section>,
  Button: ({
    children,
    disabled,
    onClick,
  }: {
    children: React.ReactNode
    disabled?: boolean
    onClick?: () => void
  }) => (
    <button type="button" disabled={disabled} onClick={onClick}>
      {children}
    </button>
  ),
  SectionCard: ({ children }: { children: React.ReactNode }) => <section>{children}</section>,
  SectionTitle: ({ children }: { children: React.ReactNode }) => <h2>{children}</h2>,
  SectionSubtitle: ({ children }: { children: React.ReactNode }) => <p>{children}</p>,
}))
vi.mock("@/components/mfa/TotpQrDisplay", () => ({ TotpQrDisplay: () => null }))

import { SettingsSecurity } from "../SettingsSecurity"

const view = () => <SettingsSecurity setSnackbar={vi.fn()} openStepUpFor={vi.fn()} />
const paste = (input: HTMLElement) =>
  fireEvent.paste(input, { clipboardData: { getData: () => "123456" } })

beforeEach(() => {
  state.auth = { user: { id: "account-a" }, loading: false }
  state.totpError = "Wait for verification"
  state.emailMfaError = "Wait for verification"
  state.confirmTotp.mockReset()
  state.confirmEmail.mockReset()
})

afterEach(() => vi.restoreAllMocks())

describe("security OTP identity readiness", () => {
  it("does not restore a digit when focus had moved to the OTP submit button", async () => {
    vi.spyOn(document, "hasFocus").mockReturnValue(true)
    const { rerender } = render(view())
    paste(screen.getAllByRole("textbox")[0]!)
    const submit = screen.getAllByRole("button", { name: "mfa.otp.submit" })[0]!
    await act(async () => {
      submit.focus()
      await Promise.resolve()
    })
    expect(submit).toHaveFocus()

    act(() => {
      submit.blur()
      state.auth.loading = true
      rerender(view())
    })
    state.auth.loading = false
    rerender(view())
    expect(document.body).toHaveFocus()
  })

  it("retains complete codes while pending and automatically submits them once confirmed", () => {
    const { rerender } = render(view())
    const inputs = screen.getAllByRole("textbox")
    paste(inputs[0]!)
    paste(inputs[6]!)
    expect(state.confirmTotp).not.toHaveBeenCalled()
    expect(state.confirmEmail).not.toHaveBeenCalled()

    state.auth.loading = true
    state.totpError = ""
    state.emailMfaError = ""
    rerender(view())
    expect(screen.getAllByRole("textbox").every((input) => input.matches(":disabled"))).toBe(true)
    expect(
      screen.getAllByRole("textbox").map((input) => (input as HTMLInputElement).value)
    ).toEqual([..."123456", ..."123456"])
    expect(state.confirmTotp).not.toHaveBeenCalled()
    expect(state.confirmEmail).not.toHaveBeenCalled()

    state.auth.loading = false
    rerender(view())
    expect(state.confirmTotp).toHaveBeenCalledExactlyOnceWith("123456")
    expect(state.confirmEmail).toHaveBeenCalledExactlyOnceWith("123456")
  })

  it("clears a previous account's codes before enabling a different account", () => {
    const { rerender } = render(view())
    const inputs = screen.getAllByRole("textbox")
    paste(inputs[0]!)
    paste(inputs[6]!)
    state.auth = { user: { id: "account-b" }, loading: false }
    state.totpError = ""
    state.emailMfaError = ""
    rerender(view())

    expect(
      screen.getAllByRole("textbox").every((input) => (input as HTMLInputElement).value === "")
    ).toBe(true)
    expect(state.confirmTotp).not.toHaveBeenCalled()
    expect(state.confirmEmail).not.toHaveBeenCalled()
  })
})
