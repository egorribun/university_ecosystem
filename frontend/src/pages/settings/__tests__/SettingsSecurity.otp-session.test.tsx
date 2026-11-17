import { act, fireEvent, render, screen } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { acceptBrowserSessionGeneration, rotateBrowserSession } from "@/stores/sessionEpoch"

const state = vi.hoisted(() => ({
  user: {
    id: "account-a",
    email: "account-a@example.test",
    email_verified_at: "2026-01-01T00:00:00Z",
    totp_enrollments: [],
  },
  loading: false,
  setUser: vi.fn(),
  startTotp: vi.fn(),
  confirmTotp: vi.fn(),
  startEmail: vi.fn(),
  confirmEmail: vi.fn(),
}))

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))
vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({ user: state.user, loading: state.loading, setUser: state.setUser }),
}))
vi.mock("@/api/mfa", () => ({
  startTotpEnrollment: state.startTotp,
  confirmTotpEnrollment: state.confirmTotp,
  deleteTotpEnrollment: vi.fn(),
  deletePendingTotpEnrollment: vi.fn(),
  startEmailMfaEnablement: state.startEmail,
  startEmailVerification: vi.fn(),
  verifyMfaChallenge: state.confirmEmail,
  resendEmailMfaChallenge: vi.fn(),
  disableEmailMfa: vi.fn(),
}))
vi.mock("@/hooks/auth/useProfileSync", () => ({
  currentUserQueryKey: ["users", "me"],
  fetchCurrentUser: vi.fn(),
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

const setSnackbar = vi.fn()
const openStepUpFor = vi.fn()
const challenge = {
  method: "email_otp",
  challenge_token: "challenge-token",
  challenge_expires_at: "2026-12-01T00:00:00Z",
}

beforeEach(() => {
  rotateBrowserSession()
  state.user = {
    id: "account-a",
    email: "account-a@example.test",
    email_verified_at: "2026-01-01T00:00:00Z",
    totp_enrollments: [],
  }
  state.loading = false
  vi.clearAllMocks()
  state.startTotp.mockResolvedValue({
    enrollment: { id: "enrollment-a", user_id: "account-a" },
    secret: crypto.randomUUID(),
    otpauth_url: "otpauth://totp/test",
  })
  state.startEmail.mockResolvedValue(challenge)
  state.confirmTotp.mockImplementation(() => new Promise(() => {}))
  state.confirmEmail.mockImplementation(() => new Promise(() => {}))
})

afterEach(() => vi.restoreAllMocks())

async function beginChallenge(kind: "totp" | "email") {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const view = () => (
    <QueryClientProvider client={queryClient}>
      <button type="button">outside</button>
      <SettingsSecurity setSnackbar={setSnackbar} openStepUpFor={openStepUpFor} />
    </QueryClientProvider>
  )
  const rendered = render(view())
  fireEvent.click(
    screen.getByRole("button", {
      name: kind === "totp" ? "settings:security.totp.add" : "settings:security.emailMfa.enable",
    })
  )
  const inputs = await screen.findAllByRole("textbox")
  expect(inputs).toHaveLength(6)
  return {
    ...rendered,
    view,
    firstInput: inputs[0]!,
    request: kind === "totp" ? state.confirmTotp : state.confirmEmail,
  }
}

function completeCodeWhileIdentityPauses(firstInput: HTMLElement, rerender: () => void) {
  act(() => {
    fireEvent.paste(firstInput, { clipboardData: { getData: () => "123456" } })
    state.loading = true
    rerender()
  })
}

describe("security OTP session readiness with real MFA hooks", () => {
  it("restores a focused digit after a same-session pause when focus stayed on the body", async () => {
    vi.spyOn(document, "hasFocus").mockReturnValue(true)
    const { rerender, view, firstInput } = await beginChallenge("totp")
    act(() => firstInput.focus())
    expect(firstInput).toHaveFocus()

    // jsdom does not blur an input when its fieldset becomes disabled.
    act(() => {
      firstInput.blur()
      state.loading = true
      rerender(view())
    })
    expect(document.body).toHaveFocus()

    state.loading = false
    rerender(view())
    expect(firstInput).toHaveFocus()
  })

  it("does not restore OTP focus after the user focuses elsewhere during a pause", async () => {
    const { rerender, view, firstInput } = await beginChallenge("totp")
    act(() => firstInput.focus())
    act(() => {
      firstInput.blur()
      state.loading = true
      rerender(view())
    })
    const outside = screen.getByRole("button", { name: "outside" })
    act(() => outside.focus())

    state.loading = false
    rerender(view())
    expect(outside).toHaveFocus()
  })

  it.each(["pointer", "keyboard"] as const)(
    "does not restore OTP focus after %s activity during a pause",
    async (inputKind) => {
      vi.spyOn(document, "hasFocus").mockReturnValue(true)
      const { rerender, view, firstInput } = await beginChallenge("totp")
      act(() => firstInput.focus())
      act(() => {
        firstInput.blur()
        state.loading = true
        rerender(view())
      })
      if (inputKind === "pointer") fireEvent.pointerDown(document.body)
      else fireEvent.keyDown(document.body, { key: "Tab" })

      state.loading = false
      rerender(view())
      expect(document.body).toHaveFocus()
    }
  )

  it("does not remember a digit after the user moved away before the pause", async () => {
    vi.spyOn(document, "hasFocus").mockReturnValue(true)
    const { rerender, view, firstInput } = await beginChallenge("totp")
    act(() => firstInput.focus())
    const outside = screen.getByRole("button", { name: "outside" })
    await act(async () => {
      outside.focus()
      await Promise.resolve()
    })
    act(() => outside.blur())
    state.loading = true
    rerender(view())
    state.loading = false
    rerender(view())
    expect(document.body).toHaveFocus()
  })

  it("does not restore focus from a previous session after rotation", async () => {
    vi.spyOn(document, "hasFocus").mockReturnValue(true)
    const { rerender, view, firstInput } = await beginChallenge("totp")
    act(() => firstInput.focus())
    act(() => {
      firstInput.blur()
      state.loading = true
      rerender(view())
    })
    rotateBrowserSession()
    state.loading = false
    rerender(view())
    expect(screen.queryAllByRole("textbox")).toHaveLength(0)
    expect(document.body).toHaveFocus()
  })

  it.each(["totp", "email"] as const)(
    "submits the retained %s code exactly once when the same session becomes ready",
    async (kind) => {
      const { rerender, view, firstInput, request } = await beginChallenge(kind)
      completeCodeWhileIdentityPauses(firstInput, () => rerender(view()))
      expect(screen.getAllByRole("textbox").every((input) => input.matches(":disabled"))).toBe(true)
      expect(request).not.toHaveBeenCalled()

      state.loading = false
      rerender(view())
      expect(request).toHaveBeenCalledOnce()
      expect(request).toHaveBeenCalledWith(
        kind === "totp"
          ? { enrollment_id: "enrollment-a", code: "123456" }
          : { method: "email_otp", challenge_token: challenge.challenge_token, code: "123456" }
      )
    }
  )

  it.each(["totp", "email"] as const)(
    "discards the %s challenge after a same-account session rotation",
    async (kind) => {
      const { rerender, view, firstInput, request } = await beginChallenge(kind)
      completeCodeWhileIdentityPauses(firstInput, () => rerender(view()))
      expect(request).not.toHaveBeenCalled()

      rotateBrowserSession()
      state.loading = false
      rerender(view())
      expect(screen.queryAllByRole("textbox")).toHaveLength(0)
      expect(request).not.toHaveBeenCalled()
    }
  )

  it.each(["totp", "email"] as const)(
    "does not submit an old %s challenge when the session rotates before rerender",
    async (kind) => {
      const { firstInput, request } = await beginChallenge(kind)
      act(() => {
        fireEvent.paste(firstInput, { clipboardData: { getData: () => "123456" } })
        rotateBrowserSession()
      })
      expect(request).not.toHaveBeenCalled()
    }
  )

  it.each(["totp", "email"] as const)(
    "does not submit an old %s challenge after a browser-session generation change",
    async (kind) => {
      const { firstInput, request } = await beginChallenge(kind)
      act(() => {
        fireEvent.paste(firstInput, { clipboardData: { getData: () => "123456" } })
        localStorage.setItem(
          "ecosystem.session.generation.v1",
          JSON.stringify({ nonce: "other-session", hash: null })
        )
        acceptBrowserSessionGeneration()
      })
      expect(request).not.toHaveBeenCalled()
    }
  )

  it.each(["totp", "email"] as const)(
    "does not submit the %s challenge after an account switch",
    async (kind) => {
      const { rerender, view, firstInput, request } = await beginChallenge(kind)
      completeCodeWhileIdentityPauses(firstInput, () => rerender(view()))
      state.user = { ...state.user, id: "account-b", email: "account-b@example.test" }
      state.loading = false
      rerender(view())
      expect(screen.queryAllByRole("textbox")).toHaveLength(0)
      expect(request).not.toHaveBeenCalled()
    }
  )
})
