import { createPortal } from "react-dom"
import { useCallback, useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { useAuth, ChallengeLockedError } from "@/contexts/AuthContext"
import type { PendingMfaState, SubmitMfaChallengePayload } from "@/types/Auth"
import OtpEntry from "./OtpEntry"

type StepUpDialogProps = {
  open: boolean
  onClose: () => void
  title?: string
  description?: string
  onCompleted?: () => void
  onChallengeReset?: () => void
}

type ChallengeMethod = PendingMfaState["methods"][number] | null

type ChallengeWithAttempts = NonNullable<ChallengeMethod> &
  Partial<{ attempt_limit: number | null; remaining_attempts: number | null }>

const NOOP_CALLBACK = () => undefined

export const StepUpDialog = ({
  open,
  onClose,
  title,
  description,
  onCompleted = NOOP_CALLBACK,
  onChallengeReset = NOOP_CALLBACK,
}: StepUpDialogProps) => {
  const { t } = useTranslation(["auth", "common"])
  const { requireMfa, submitMfaChallenge } = useAuth()
  const [pending, setPending] = useState<PendingMfaState | null>(null)
  const [verifying, setVerifying] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const challenge: ChallengeMethod = pending
    ? (pending.methods.find((candidate) => candidate.method === pending.default_method) ??
      pending.methods[0] ??
      null)
    : null
  const refreshChallenges = useCallback(async () => {
    const result = await requireMfa()
    setPending(result)
    return result
  }, [requireMfa])

  useEffect(() => {
    if (!open) {
      setPending(null)
      setError(null)
      setVerifying(false)
      return
    }

    let cancelled = false
    void (async () => {
      try {
        const result = await refreshChallenges()
        if (!cancelled && !result) {
          setError(t("mfa.stepUp.requestFailed"))
        } else if (!cancelled) {
          setError(null)
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : t("mfa.stepUp.requestFailed"))
        }
      }
    })()

    return () => {
      cancelled = true
    }
  }, [open, refreshChallenges, t])

  // Handle Escape key globally
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && open && !e.defaultPrevented) {
        onClose()
      }
    }
    window.addEventListener("keydown", handleKeyDown)
    return () => window.removeEventListener("keydown", handleKeyDown)
  }, [open, onClose])

  const handleSubmit = useCallback(
    async (payload: SubmitMfaChallengePayload) => {
      setVerifying(true)
      setError(null)
      try {
        await submitMfaChallenge(payload)
        onCompleted()
        onClose()
      } catch (err) {
        if (err instanceof ChallengeLockedError) {
          setError(err.message)
          if (err.refreshable) {
            try {
              const refreshed = await refreshChallenges()
              if (refreshed) {
                onChallengeReset()
              }
            } catch (refreshError) {
              setError(
                refreshError instanceof Error ? refreshError.message : t("mfa.stepUp.requestFailed")
              )
            }
          }
        } else {
          setError(err instanceof Error ? err.message : t("mfa.stepUp.verifyFailed"))
        }
      } finally {
        setVerifying(false)
      }
    },
    [onChallengeReset, onClose, onCompleted, refreshChallenges, submitMfaChallenge, t]
  )

  const handleOtpSubmit = useCallback(
    async (code: string) => {
      // OtpEntry is mounted only while a challenge exists.
      await handleSubmit({
        method: challenge!.method,
        code,
        challengeToken: challenge!.challenge_token,
      })
    },
    [challenge, handleSubmit]
  )

  const formatRemainingAttempts = useCallback(
    (challenge: ChallengeMethod | null) => {
      if (!challenge) return null
      const meta = challenge as ChallengeWithAttempts
      const limit = typeof meta.attempt_limit === "number" ? meta.attempt_limit : null
      const remaining = typeof meta.remaining_attempts === "number" ? meta.remaining_attempts : null
      if (!limit || limit <= 0 || remaining === null) {
        return null
      }
      return t("mfa.otp.attemptsRemaining", { count: Math.max(remaining, 0) })
    },
    [t]
  )

  const helperText = formatRemainingAttempts(challenge)

  if (!open) return null

  return createPortal(
    <>
      <button
        type="button"
        className="mobile-drawer-backdrop fixed inset-0 z-overlay flex items-center justify-center p-4 bg-black/(--opacity-medium) border-none w-full h-full text-left outline-none cursor-default"
        onClick={onClose}
        aria-label={t("common:buttons.close")}
        tabIndex={-1}
        data-testid="step-up-backdrop"
      />

      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="step-up-dialog-title"
        className="fixed inset-0 z-overlay flex items-center justify-center pointer-events-none"
      >
        <div
          className="bg-card rounded-2xl shadow-2xl w-full max-w-[24rem] pointer-events-auto"
          // Removed onKeyDown, handled by useEffect
          tabIndex={-1}
        >
          <h2
            id="step-up-dialog-title"
            className="text-xl font-bold text-text-primary px-6 pt-6 pb-2"
          >
            {title ?? t("mfa.stepUp.title")}
          </h2>
          <div className="px-6 py-4">
            <div className="flex flex-col gap-6 mt-2">
              <p className="text-sm text-(--text-secondary)">
                {description ?? t("mfa.stepUp.description")}
              </p>
              {challenge ? (
                <OtpEntry
                  method={challenge.method}
                  loading={verifying}
                  error={error}
                  helperText={helperText}
                  onSubmit={handleOtpSubmit}
                />
              ) : error ? (
                <p role="alert" className="text-sm font-bold text-error-text">
                  {error}
                </p>
              ) : null}
            </div>
          </div>
          <div className="flex gap-2 justify-end px-6 pb-6 pt-2">
            <button
              onClick={onClose}
              className="inline-flex items-center justify-center gap-2 px-4 py-2 text-base font-bold rounded-lg transition-all duration-fast text-text-primary hover:bg-(--text-primary)/(--opacity-subtle)"
            >
              {t("common:buttons.cancel")}
            </button>
          </div>
        </div>
      </div>
    </>,
    document.body
  )
}

export default StepUpDialog
