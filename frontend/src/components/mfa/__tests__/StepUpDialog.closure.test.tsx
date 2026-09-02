import type { ComponentProps } from "react"
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"

import type { PendingMfaState } from "@/types/Auth"

const auth = vi.hoisted(() => ({
  value: {
    requireMfa: vi.fn(),
    submitMfaChallenge: vi.fn(),
  },
}))

const challengeErrors = vi.hoisted(() => {
  class MockChallengeLockedError extends Error {
    refreshable: boolean

    constructor(message: string, options?: { refreshable?: boolean }) {
      super(message)
      this.name = "ChallengeLockedError"
      this.refreshable = Boolean(options?.refreshable)
    }
  }

  return { MockChallengeLockedError }
})

vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => auth.value,
  ChallengeLockedError: challengeErrors.MockChallengeLockedError,
}))

vi.mock("react-i18next", () => {
  const t = (key: string, values?: { count?: number }) =>
    key === "mfa.otp.attemptsRemaining" ? `${values?.count ?? ""} attempts remaining` : key

  return {
    useTranslation: () => ({ t, i18n: { language: "en" } }),
  }
})

vi.mock("@/components/mfa/OtpEntry", () => ({
  default: ({
    loading,
    error,
    helperText,
    onSubmit,
  }: {
    loading?: boolean
    error?: string | null
    helperText?: string | null
    onSubmit: (code: string) => Promise<void> | void
  }) => (
    <div data-testid="otp-entry">
      {error && <p>{error}</p>}
      {helperText && <p>{helperText}</p>}
      <button type="button" disabled={loading} onClick={() => void onSubmit("123456")}>
        otp-submit
      </button>
    </div>
  ),
}))

import StepUpDialog from "@/components/mfa/StepUpDialog"

const makePending = (
  methodOverrides: Partial<PendingMfaState["methods"][number]> = {},
  methods?: PendingMfaState["methods"]
): PendingMfaState => ({
  status: "mfa_required",
  reason: "step-up",
  user_id: "0194d2e7-9b84-7f04-b2ff-c087ea96a257",
  session_id: "0194d2e7-9b84-7f04-b2ff-c087ea96a258",
  default_method: "totp",
  methods: methods ?? [
    {
      method: "totp",
      challenge_token: "challenge-token-1234567890",
      challenge_expires_at: "2026-08-01T12:00:00Z",
      attempt_count: 0,
      attempt_limit: 5,
      remaining_attempts: 2,
      ...methodOverrides,
    },
  ],
})

const renderDialog = (props: Partial<ComponentProps<typeof StepUpDialog>> = {}) =>
  render(<StepUpDialog open onClose={vi.fn()} {...props} />)

beforeEach(() => {
  auth.value.requireMfa.mockReset()
  auth.value.submitMfaChallenge.mockReset()
})

describe("StepUpDialog closure", () => {
  it("returns null while closed, reports a missing challenge, and handles Escape", async () => {
    const user = userEvent.setup()
    const onClose = vi.fn()
    auth.value.requireMfa.mockResolvedValue(null)
    const { rerender } = render(<StepUpDialog open={false} onClose={onClose} />)

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()

    rerender(<StepUpDialog open onClose={onClose} />)
    expect(await screen.findByText("mfa.stepUp.requestFailed")).toBeInTheDocument()

    const preventedEscape = new KeyboardEvent("keydown", {
      key: "Escape",
      cancelable: true,
    })
    preventedEscape.preventDefault()
    window.dispatchEvent(preventedEscape)
    expect(onClose).not.toHaveBeenCalled()

    window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }))
    expect(onClose).toHaveBeenCalledTimes(1)

    rerender(<StepUpDialog open={false} onClose={onClose} />)
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
    await user.click(document.body)

    window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }))
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it("renders translated defaults and resets stale state across close and reopen", async () => {
    const onClose = vi.fn()
    auth.value.requireMfa.mockResolvedValueOnce(makePending()).mockResolvedValueOnce(null)

    const { rerender } = render(<StepUpDialog open onClose={onClose} />)
    expect(await screen.findByRole("heading", { name: "mfa.stepUp.title" })).toHaveClass(
      "text-xl",
      "font-bold"
    )
    expect(screen.getByText("mfa.stepUp.description")).toBeInTheDocument()

    rerender(<StepUpDialog open={false} onClose={onClose} />)
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
    rerender(<StepUpDialog open onClose={onClose} />)

    expect(await screen.findByText("mfa.stepUp.requestFailed")).toBeInTheDocument()
    expect(screen.queryByTestId("otp-entry")).not.toBeInTheDocument()
  })

  it("shows Error and non-Error request failures", async () => {
    auth.value.requireMfa.mockRejectedValueOnce(new Error("request unavailable"))
    const first = renderDialog()
    expect(await screen.findByText("request unavailable")).toBeInTheDocument()
    first.unmount()

    auth.value.requireMfa.mockRejectedValueOnce("request failed")
    renderDialog()
    expect(await screen.findByText("mfa.stepUp.requestFailed")).toBeInTheDocument()
  })

  it("submits a challenge, forwards callbacks, and exposes remaining attempts", async () => {
    const user = userEvent.setup()
    const pending = makePending()
    auth.value.requireMfa.mockResolvedValue(pending)
    auth.value.submitMfaChallenge.mockResolvedValue(undefined)
    const onCompleted = vi.fn()
    const onClose = vi.fn()

    renderDialog({ onCompleted, onClose, title: "Custom title", description: "Custom description" })

    expect(await screen.findByRole("heading", { name: "Custom title" })).toBeInTheDocument()
    expect(screen.getByText("Custom description")).toBeInTheDocument()
    expect(await screen.findByText("2 attempts remaining")).toBeInTheDocument()

    await user.click(await screen.findByRole("button", { name: "otp-submit" }))
    await waitFor(() => {
      expect(auth.value.submitMfaChallenge).toHaveBeenCalledWith({
        method: "totp",
        code: "123456",
        challengeToken: "challenge-token-1234567890",
      })
      expect(onCompleted).toHaveBeenCalledTimes(1)
      expect(onClose).toHaveBeenCalledTimes(1)
    })
  })

  it("submits the exact email OTP method selected by the challenge", async () => {
    const user = userEvent.setup()
    auth.value.requireMfa.mockResolvedValue(
      makePending({ method: "email_otp", delivery_hint: "u***@example.com" })
    )
    auth.value.submitMfaChallenge.mockResolvedValue(undefined)

    renderDialog()
    await user.click(await screen.findByRole("button", { name: "otp-submit" }))

    await waitFor(() =>
      expect(auth.value.submitMfaChallenge).toHaveBeenCalledWith({
        method: "email_otp",
        code: "123456",
        challengeToken: "challenge-token-1234567890",
      })
    )
  })

  it("prefers the configured default method when several challenges are available", async () => {
    const user = userEvent.setup()
    const email = {
      method: "email_otp" as const,
      challenge_token: "email-token",
      challenge_expires_at: "2026-08-01T12:00:00Z",
      attempt_count: 0,
      attempt_limit: 5,
      remaining_attempts: 4,
    }
    const totp = {
      method: "totp" as const,
      challenge_token: "totp-token",
      challenge_expires_at: "2026-08-01T12:00:00Z",
      attempt_count: 0,
      attempt_limit: 5,
      remaining_attempts: 1,
    }
    auth.value.requireMfa.mockResolvedValue({
      ...makePending(),
      default_method: "email_otp",
      methods: [totp, email],
    })
    auth.value.submitMfaChallenge.mockResolvedValue(undefined)

    renderDialog()
    await user.click(await screen.findByRole("button", { name: "otp-submit" }))

    await waitFor(() =>
      expect(auth.value.submitMfaChallenge).toHaveBeenCalledWith({
        method: "email_otp",
        code: "123456",
        challengeToken: "email-token",
      })
    )
  })

  it("handles generic verification failures and missing attempt metadata", async () => {
    const user = userEvent.setup()
    auth.value.requireMfa.mockResolvedValue(
      makePending({ attempt_limit: null, remaining_attempts: null })
    )
    auth.value.submitMfaChallenge.mockRejectedValueOnce(new Error("verification failed"))
    const onClose = vi.fn()

    renderDialog({ onClose })

    expect(await screen.findByTestId("otp-entry")).toBeInTheDocument()
    expect(screen.queryByText(/attempts remaining/)).not.toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "otp-submit" }))
    expect(await screen.findByText("verification failed")).toBeInTheDocument()
    expect(onClose).not.toHaveBeenCalled()
    expect(screen.getByRole("button", { name: "otp-submit" })).not.toBeDisabled()
  })

  it("uses the fallback verification message for non-Error failures", async () => {
    const user = userEvent.setup()
    auth.value.requireMfa.mockResolvedValue(
      makePending({ attempt_limit: 0, remaining_attempts: 0 })
    )
    auth.value.submitMfaChallenge.mockRejectedValueOnce("invalid code")

    renderDialog()

    await user.click(await screen.findByRole("button", { name: "otp-submit" }))
    expect(await screen.findByText("mfa.stepUp.verifyFailed")).toBeInTheDocument()
  })

  it("normalizes negative attempt counts and rejects invalid limits", async () => {
    auth.value.requireMfa.mockResolvedValue(
      makePending({ attempt_limit: -1, remaining_attempts: -2 })
    )
    const { rerender } = renderDialog()

    await waitFor(() => expect(screen.getByTestId("otp-entry")).toBeInTheDocument())
    expect(screen.queryByText(/attempts remaining/)).not.toBeInTheDocument()

    rerender(<StepUpDialog open={false} onClose={vi.fn()} />)
    auth.value.requireMfa.mockResolvedValue(
      makePending({ attempt_limit: 5, remaining_attempts: -2 })
    )
    rerender(<StepUpDialog open onClose={vi.fn()} />)
    await waitFor(() => expect(screen.getByText("0 attempts remaining")).toBeInTheDocument())
  })

  it("refreshes a refreshable locked challenge and invokes the reset callback", async () => {
    const user = userEvent.setup()
    const refreshed = makePending({ remaining_attempts: 5 })
    auth.value.requireMfa.mockResolvedValueOnce(makePending()).mockResolvedValueOnce(refreshed)
    auth.value.submitMfaChallenge.mockRejectedValueOnce(
      new challengeErrors.MockChallengeLockedError("Locked", { refreshable: true })
    )
    const onChallengeReset = vi.fn()

    renderDialog({ onChallengeReset })
    await user.click(await screen.findByRole("button", { name: "otp-submit" }))

    await waitFor(() => {
      expect(onChallengeReset).toHaveBeenCalledTimes(1)
      expect(screen.getByText("Locked")).toBeInTheDocument()
      expect(screen.getByText("5 attempts remaining")).toBeInTheDocument()
    })
  })

  it("keeps a non-refreshable lock error and handles a failed refresh", async () => {
    const user = userEvent.setup()
    auth.value.requireMfa.mockResolvedValue(makePending())
    auth.value.submitMfaChallenge.mockRejectedValueOnce(
      new challengeErrors.MockChallengeLockedError("Permanently locked", { refreshable: false })
    )

    const { unmount: unmountFirst } = renderDialog()
    await user.click(await screen.findByRole("button", { name: "otp-submit" }))
    expect(await screen.findByText("Permanently locked")).toBeInTheDocument()
    expect(auth.value.requireMfa).toHaveBeenCalledTimes(1)
    unmountFirst()

    auth.value.requireMfa.mockReset()
    auth.value.requireMfa
      .mockResolvedValueOnce(makePending())
      .mockRejectedValueOnce(new Error("refresh unavailable"))
    auth.value.submitMfaChallenge.mockReset()
    auth.value.submitMfaChallenge.mockRejectedValueOnce(
      new challengeErrors.MockChallengeLockedError("Temporarily locked", { refreshable: true })
    )

    const { unmount } = renderDialog()
    await user.click(await screen.findByRole("button", { name: "otp-submit" }))
    expect(await screen.findByText("refresh unavailable")).toBeInTheDocument()
    unmount()
  })

  it("does not reset when a refreshable lock refresh returns no challenge", async () => {
    const user = userEvent.setup()
    auth.value.requireMfa.mockResolvedValueOnce(makePending()).mockResolvedValueOnce(null)
    auth.value.submitMfaChallenge.mockRejectedValueOnce(
      new challengeErrors.MockChallengeLockedError("Locked", { refreshable: true })
    )
    const onChallengeReset = vi.fn()

    renderDialog({ onChallengeReset })
    await user.click(await screen.findByRole("button", { name: "otp-submit" }))
    await waitFor(() => expect(screen.getByText("Locked")).toBeInTheDocument())
    expect(onChallengeReset).not.toHaveBeenCalled()
  })

  it("uses the request fallback when a locked challenge refresh rejects a non-Error", async () => {
    const user = userEvent.setup()
    auth.value.requireMfa.mockResolvedValueOnce(makePending()).mockRejectedValueOnce("offline")
    auth.value.submitMfaChallenge.mockRejectedValueOnce(
      new challengeErrors.MockChallengeLockedError("Locked", { refreshable: true })
    )

    renderDialog()
    await user.click(await screen.findByRole("button", { name: "otp-submit" }))
    expect(await screen.findByText("mfa.stepUp.requestFailed")).toBeInTheDocument()
  })

  it("renders no OTP control when the provider returns an empty method list", async () => {
    auth.value.requireMfa.mockResolvedValue(makePending({}, []))

    renderDialog()

    await waitFor(() => expect(auth.value.requireMfa).toHaveBeenCalledTimes(1))
    expect(screen.queryByTestId("otp-entry")).not.toBeInTheDocument()
  })

  it("ignores a successful challenge response after unmount", async () => {
    let resolveChallenge!: (value: PendingMfaState) => void
    auth.value.requireMfa.mockReturnValueOnce(
      new Promise<PendingMfaState>((resolve) => {
        resolveChallenge = resolve
      })
    )
    const { unmount } = renderDialog()

    unmount()
    resolveChallenge(makePending())
    await Promise.resolve()

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
  })

  it("ignores a challenge request failure after unmount", async () => {
    let rejectChallenge!: (reason: unknown) => void
    auth.value.requireMfa.mockReturnValueOnce(
      new Promise<PendingMfaState | null>((_resolve, reject) => {
        rejectChallenge = reject
      })
    )
    const { unmount } = renderDialog()

    unmount()
    rejectChallenge(new Error("late failure"))
    await Promise.resolve()

    expect(screen.queryByText("late failure")).not.toBeInTheDocument()
  })
})
