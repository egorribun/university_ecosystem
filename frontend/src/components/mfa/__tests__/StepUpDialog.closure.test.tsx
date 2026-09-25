import type { ComponentProps } from "react"
import { act, render, screen, waitFor } from "@testing-library/react"
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

const i18n = vi.hoisted(() => {
  const makeT =
    (language: string) =>
    (key: string, values?: { count?: number }): string => {
      if (key !== "mfa.otp.attemptsRemaining") return key
      const count = String(values?.count ?? "")
      return language === "ru" ? `осталось попыток: ${count}` : `${count} attempts remaining`
    }
  return {
    language: "en",
    namespaces: [] as unknown[],
    translators: { en: makeT("en"), ru: makeT("ru") } as Record<string, ReturnType<typeof makeT>>,
  }
})

vi.mock("react-i18next", () => ({
  useTranslation: (namespaces?: unknown) => {
    i18n.namespaces.push(namespaces)
    return { t: i18n.translators[i18n.language], i18n: { language: i18n.language } }
  },
}))

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
  auth.value.requireMfa = vi.fn()
  auth.value.submitMfaChallenge.mockReset()
  i18n.language = "en"
  i18n.namespaces.length = 0
})

const deferred = <T,>() => {
  let resolve!: (value: T) => void
  let reject!: (reason: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

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

  it("does not request an MFA challenge while closed", async () => {
    auth.value.requireMfa.mockResolvedValue(makePending())

    render(<StepUpDialog open={false} onClose={vi.fn()} />)
    await Promise.resolve()

    expect(auth.value.requireMfa).not.toHaveBeenCalled()
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
  })

  it("clears a stale request error after closing and reopening successfully", async () => {
    auth.value.requireMfa
      .mockRejectedValueOnce(new Error("first request failed"))
      .mockResolvedValueOnce(makePending())
    const { rerender } = render(<StepUpDialog open onClose={vi.fn()} />)

    expect(await screen.findByText("first request failed")).toBeInTheDocument()
    rerender(<StepUpDialog open={false} onClose={vi.fn()} />)
    rerender(<StepUpDialog open onClose={vi.fn()} />)

    expect(await screen.findByTestId("otp-entry")).toBeInTheDocument()
    expect(screen.queryByText("first request failed")).not.toBeInTheDocument()
  })

  it("marks the OTP control busy until verification settles", async () => {
    const user = userEvent.setup()
    let resolveSubmit!: () => void
    auth.value.requireMfa.mockResolvedValue(makePending())
    auth.value.submitMfaChallenge.mockReturnValue(
      new Promise<void>((resolve) => {
        resolveSubmit = resolve
      })
    )
    const onClose = vi.fn()
    renderDialog({ onClose })

    const submit = await screen.findByRole("button", { name: "otp-submit" })
    await user.click(submit)
    expect(submit).toBeDisabled()

    resolveSubmit()
    await waitFor(() => expect(onClose).toHaveBeenCalledOnce())
    expect(submit).not.toBeDisabled()
  })

  it("rejects non-numeric attempt metadata instead of displaying misleading counts", async () => {
    auth.value.requireMfa.mockResolvedValue(
      makePending({ attempt_limit: "5" as never, remaining_attempts: 2 })
    )
    const first = renderDialog()
    await waitFor(() => expect(screen.getByTestId("otp-entry")).toBeInTheDocument())
    expect(screen.queryByText(/attempts remaining/)).not.toBeInTheDocument()
    first.unmount()

    auth.value.requireMfa.mockReset()
    auth.value.requireMfa.mockResolvedValue(
      makePending({ attempt_limit: 5, remaining_attempts: "2" as never })
    )
    renderDialog()
    await waitFor(() => expect(screen.getByTestId("otp-entry")).toBeInTheDocument())
    expect(screen.queryByText(/attempts remaining/)).not.toBeInTheDocument()
  })

  it("does not display attempts when the limit is zero or absent", async () => {
    auth.value.requireMfa.mockResolvedValue(
      makePending({ attempt_limit: 0, remaining_attempts: 2 })
    )
    const first = renderDialog()
    await waitFor(() => expect(screen.getByTestId("otp-entry")).toBeInTheDocument())
    expect(screen.queryByText(/attempts remaining/)).not.toBeInTheDocument()
    first.unmount()

    auth.value.requireMfa.mockReset()
    auth.value.requireMfa.mockResolvedValue(
      makePending({ attempt_limit: null, remaining_attempts: 2 })
    )
    renderDialog()
    await waitFor(() => expect(screen.getByTestId("otp-entry")).toBeInTheDocument())
    expect(screen.queryByText(/attempts remaining/)).not.toBeInTheDocument()
  })

  it("exposes keyboard-safe backdrop and panel semantics", async () => {
    auth.value.requireMfa.mockResolvedValue(makePending())
    renderDialog()
    await screen.findByTestId("otp-entry")

    const backdrop = screen.getByTestId("step-up-backdrop")
    expect(backdrop).toHaveAttribute("aria-label", "common:buttons.close")
    expect(backdrop).toHaveAttribute("tabindex", "-1")
    const dialog = screen.getByRole("dialog")
    expect(dialog).toHaveAttribute("aria-labelledby", "step-up-dialog-title")
    expect(dialog.firstElementChild).toHaveAttribute("tabindex", "-1")
    expect(screen.getByRole("button", { name: "common:buttons.cancel" })).toBeInTheDocument()
  })

  it("loads the auth and common namespaces it renders keys from", async () => {
    auth.value.requireMfa.mockResolvedValue(makePending())
    renderDialog()
    await screen.findByTestId("otp-entry")

    expect(i18n.namespaces.at(-1)).toEqual(["auth", "common"])
  })

  it("closes only on Escape, not on other keys", async () => {
    const onClose = vi.fn()
    auth.value.requireMfa.mockResolvedValue(makePending())
    renderDialog({ onClose })
    await screen.findByTestId("otp-entry")

    window.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter" }))
    window.dispatchEvent(new KeyboardEvent("keydown", { key: "a" }))
    expect(onClose).not.toHaveBeenCalled()

    window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }))
    expect(onClose).toHaveBeenCalledOnce()
  })

  it("never shows the previous challenge, error or busy state after reopening", async () => {
    const user = userEvent.setup()
    const verification = deferred<void>()
    auth.value.requireMfa.mockResolvedValueOnce(makePending())
    auth.value.submitMfaChallenge.mockReturnValueOnce(verification.promise)
    const onClose = vi.fn()
    const { rerender } = render(<StepUpDialog open onClose={onClose} />)

    await user.click(await screen.findByRole("button", { name: "otp-submit" }))
    expect(screen.getByRole("button", { name: "otp-submit" })).toBeDisabled()

    rerender(<StepUpDialog open={false} onClose={onClose} />)
    const pendingRefresh = deferred<PendingMfaState | null>()
    auth.value.requireMfa.mockReturnValueOnce(pendingRefresh.promise)
    rerender(<StepUpDialog open onClose={onClose} />)

    // The old challenge token must not be offered while the new one loads.
    expect(screen.queryByTestId("otp-entry")).not.toBeInTheDocument()
    expect(screen.queryByRole("alert")).not.toBeInTheDocument()

    pendingRefresh.resolve(makePending({ challenge_token: "fresh-challenge-token-000000" }))
    const submit = await screen.findByRole("button", { name: "otp-submit" })
    expect(submit).not.toBeDisabled()
  })

  it("does not carry a request error into a reopened dialog", async () => {
    auth.value.requireMfa.mockResolvedValueOnce(null)
    const { rerender } = render(<StepUpDialog open onClose={vi.fn()} />)
    expect(await screen.findByRole("alert")).toHaveTextContent("mfa.stepUp.requestFailed")

    rerender(<StepUpDialog open={false} onClose={vi.fn()} />)
    auth.value.requireMfa.mockReturnValueOnce(deferred<PendingMfaState | null>().promise)
    rerender(<StepUpDialog open onClose={vi.fn()} />)

    expect(screen.queryByRole("alert")).not.toBeInTheDocument()
  })

  it("re-requests with the current auth provider and clears its earlier failure", async () => {
    const firstRequest = vi.fn().mockResolvedValue(null)
    auth.value.requireMfa = firstRequest
    const { rerender } = render(<StepUpDialog open onClose={vi.fn()} />)
    expect(await screen.findByRole("alert")).toHaveTextContent("mfa.stepUp.requestFailed")

    const secondRequest = vi.fn().mockResolvedValue(makePending())
    auth.value.requireMfa = secondRequest
    rerender(<StepUpDialog open onClose={vi.fn()} />)

    expect(await screen.findByTestId("otp-entry")).toBeInTheDocument()
    expect(secondRequest).toHaveBeenCalledOnce()
    expect(firstRequest).toHaveBeenCalledOnce()
    expect(screen.queryByText("mfa.stepUp.requestFailed")).not.toBeInTheDocument()
  })

  it("ignores a superseded request that settles after the dialog was reopened", async () => {
    const stale = deferred<PendingMfaState | null>()
    auth.value.requireMfa.mockReturnValueOnce(stale.promise)
    const { rerender } = render(<StepUpDialog open onClose={vi.fn()} />)

    rerender(<StepUpDialog open={false} onClose={vi.fn()} />)
    auth.value.requireMfa.mockResolvedValueOnce(null)
    rerender(<StepUpDialog open onClose={vi.fn()} />)
    expect(await screen.findByRole("alert")).toHaveTextContent("mfa.stepUp.requestFailed")

    await act(async () => {
      stale.resolve(null)
      await stale.promise
    })
    expect(screen.getByRole("alert")).toHaveTextContent("mfa.stepUp.requestFailed")
  })

  it("ignores a superseded request failure after the dialog was reopened", async () => {
    const stale = deferred<PendingMfaState | null>()
    auth.value.requireMfa.mockReturnValueOnce(stale.promise)
    const { rerender } = render(<StepUpDialog open onClose={vi.fn()} />)

    rerender(<StepUpDialog open={false} onClose={vi.fn()} />)
    auth.value.requireMfa.mockReturnValueOnce(deferred<PendingMfaState | null>().promise)
    rerender(<StepUpDialog open onClose={vi.fn()} />)

    await act(async () => {
      stale.reject(new Error("superseded failure"))
      await stale.promise.catch(() => undefined)
    })
    expect(screen.queryByRole("alert")).not.toBeInTheDocument()
    expect(screen.queryByText("superseded failure")).not.toBeInTheDocument()
  })

  it("clears the previous verification error while a retry is verifying", async () => {
    const user = userEvent.setup()
    const retry = deferred<void>()
    auth.value.requireMfa.mockResolvedValue(makePending())
    auth.value.submitMfaChallenge
      .mockRejectedValueOnce(new Error("verification failed"))
      .mockReturnValueOnce(retry.promise)
    renderDialog()

    await user.click(await screen.findByRole("button", { name: "otp-submit" }))
    expect(await screen.findByText("verification failed")).toBeInTheDocument()

    await user.click(screen.getByRole("button", { name: "otp-submit" }))
    expect(screen.queryByText("verification failed")).not.toBeInTheDocument()

    await act(async () => {
      retry.resolve()
      await retry.promise
    })
  })

  it("invokes the latest completion callbacks passed by the parent", async () => {
    const user = userEvent.setup()
    auth.value.requireMfa.mockResolvedValue(makePending())
    auth.value.submitMfaChallenge.mockResolvedValue(undefined)
    const staleClose = vi.fn()
    const staleCompleted = vi.fn()
    const { rerender } = render(
      <StepUpDialog open onClose={staleClose} onCompleted={staleCompleted} />
    )
    await screen.findByTestId("otp-entry")

    const onClose = vi.fn()
    const onCompleted = vi.fn()
    rerender(<StepUpDialog open onClose={onClose} onCompleted={onCompleted} />)
    await user.click(screen.getByRole("button", { name: "otp-submit" }))

    await waitFor(() => expect(onClose).toHaveBeenCalledOnce())
    expect(onCompleted).toHaveBeenCalledOnce()
    expect(staleClose).not.toHaveBeenCalled()
    expect(staleCompleted).not.toHaveBeenCalled()
  })

  it("re-translates the remaining attempts when the language changes", async () => {
    auth.value.requireMfa.mockResolvedValue(makePending({ remaining_attempts: 3 }))
    const { rerender } = renderDialog()
    expect(await screen.findByText("3 attempts remaining")).toBeInTheDocument()

    i18n.language = "ru"
    rerender(<StepUpDialog open onClose={vi.fn()} />)

    expect(await screen.findByText("осталось попыток: 3")).toBeInTheDocument()
  })
})
