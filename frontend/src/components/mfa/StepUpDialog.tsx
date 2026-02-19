import { useCallback, useEffect, useMemo, useState } from "react"
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

export const StepUpDialog = ({
  open,
  onClose,
  title,
  description,
  onCompleted,
  onChallengeReset,
}: StepUpDialogProps) => {
  const { t } = useTranslation(["auth", "common"])
  const { requireMfa, submitMfaChallenge } = useAuth()
  const [pending, setPending] = useState<PendingMfaState | null>(null)
  const [verifying, setVerifying] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const challenge = useMemo<ChallengeMethod>(() => pending?.methods?.[0] ?? null, [pending])
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

  const handleSubmit = useCallback(
    async (payload: SubmitMfaChallengePayload) => {
      setVerifying(true)
      setError(null)
      try {
        await submitMfaChallenge(payload)
        onCompleted?.()
        onClose()
      } catch (err) {
        if (err instanceof ChallengeLockedError) {
          setError(err.message)
          if (err.refreshable) {
            try {
              const refreshed = await refreshChallenges()
              if (refreshed) {
                onChallengeReset?.()
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
      if (!challenge) {
        setError(t("mfa.stepUp.missingChallenge"))
        return
      }
      await handleSubmit({ code, challengeToken: challenge.challenge_token })
    },
    [challenge, handleSubmit, t]
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

  const helperText = useMemo(
    () => formatRemainingAttempts(challenge),
    [challenge, formatRemainingAttempts]
  )

  if (!open) return null

  return (
    <div className="fixed inset-0 z-navbar flex items-center justify-center p-4">
      <div
        className="fixed inset-0 bg-black/(--opacity-medium) transition-opacity"
        aria-hidden="true"
        onClick={onClose}
      />
      {/* eslint-disable-next-line jsx-a11y/no-noninteractive-element-interactions */}
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="step-up-dialog-title"
        className="bg-card relative z-content w-full max-w-sm rounded-2xl shadow-2xl"
        onKeyDown={(e) => {
          if (e.key === "Escape") onClose()
        }}
        tabIndex={-1}
      >
        <h2
          id="step-up-dialog-title"
          className="px-6 pb-2 pt-6 text-xl font-bold text-(--text-primary)"
        >
          {title ?? t("mfa.stepUp.title")}
        </h2>
        <div className="px-6 py-4">
          <div className="mt-2 flex flex-col gap-6">
            <p className="text-sm text-(--text-secondary)">
              {description ?? t("mfa.stepUp.description")}
            </p>
            {challenge ? (
              <OtpEntry
                loading={verifying}
                error={error}
                helperText={helperText}
                onSubmit={handleOtpSubmit}
              />
            ) : null}
          </div>
        </div>
        <div className="flex justify-end gap-2 px-6 pb-6 pt-2">
          <button
            onClick={onClose}
            className="text-base font-bold text-(--text-primary) transition-all duration-fast hover:bg-(--text-primary)/(--opacity-subtle) inline-flex items-center justify-center gap-2 rounded-lg px-4 py-2"
          >
            {t("common:buttons.cancel")}
          </button>
        </div>
      </div>
    </div>
  )
}

export default StepUpDialog
