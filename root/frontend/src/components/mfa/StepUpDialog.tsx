import { useCallback, useEffect, useMemo, useState } from "react"
import { useTranslation } from "react-i18next"
import { useAuth } from "@/contexts/AuthContext"
import type { PendingMfaState, SubmitMfaChallengePayload } from "@/contexts/AuthContext"
import type { MfaMethod } from "@/types/Mfa"
import OtpEntry, { type OtpMethod } from "./OtpEntry"
import WebAuthnPrompt from "./WebAuthnPrompt"

type StepUpDialogProps = {
  open: boolean
  onClose: () => void
  title?: string
  description?: string
  onCompleted?: () => void
}

type ChallengeMethod = PendingMfaState["methods"][number]

const resolveMethods = (pending: PendingMfaState | null) => pending?.methods ?? []

export const StepUpDialog = ({
  open,
  onClose,
  title,
  description,
  onCompleted,
}: StepUpDialogProps) => {
  const { t } = useTranslation(["auth", "common"])
  const { requireMfa, submitMfaChallenge } = useAuth()
  const [pending, setPending] = useState<PendingMfaState | null>(null)
  const [verifying, setVerifying] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const methods = useMemo(() => resolveMethods(pending), [pending])
  const defaultMethod = pending?.default_method ?? methods[0]?.method ?? null

  const hasTotp = methods.some((entry) => entry.method === "totp")
  const hasRecovery = methods.some((entry) => entry.method === "recovery")
  const hasWebAuthn = methods.some((entry) => entry.method === "webauthn")

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
        const result = await requireMfa()
        if (!cancelled) {
          setPending(result)
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
  }, [open, requireMfa, t])

  const getChallenge = useCallback(
    (method: MfaMethod): ChallengeMethod | null =>
      methods.find((entry) => entry.method === method) ?? null,
    [methods]
  )

  const handleSubmit = useCallback(
    async (payload: SubmitMfaChallengePayload) => {
      setVerifying(true)
      setError(null)
      try {
        await submitMfaChallenge(payload)
        onCompleted?.()
        onClose()
      } catch (err) {
        setError(err instanceof Error ? err.message : t("mfa.stepUp.verifyFailed"))
      } finally {
        setVerifying(false)
      }
    },
    [onClose, onCompleted, submitMfaChallenge, t]
  )

  const otpMethods = useMemo<OtpMethod[]>(() => {
    const result: OtpMethod[] = []
    if (hasTotp) result.push("totp")
    if (hasRecovery) result.push("recovery")
    return result
  }, [hasRecovery, hasTotp])

  const handleOtpSubmit = useCallback(
    async (method: Extract<MfaMethod, "totp" | "recovery">, code: string) => {
      const challenge = getChallenge(method)
      if (!challenge) {
        setError(t("mfa.stepUp.missingChallenge"))
        return
      }
      await handleSubmit({ method, code, challengeToken: challenge.challenge_token })
    },
    [getChallenge, handleSubmit, t]
  )

  const webAuthnChallenge = useMemo(() => getChallenge("webauthn"), [getChallenge])

  if (!open) return null

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50"
      onClick={onClose}
    >
      <div
        className="bg-card rounded-2xl shadow-2xl w-full max-w-sm"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="text-xl font-bold text-page-text px-6 pt-6 pb-2">
          {title ?? t("mfa.stepUp.title")}
        </h2>
        <div className="px-6 py-4">
          <div className="flex flex-col gap-6 mt-2">
            <p className="text-sm text-page-text/70">
              {description ?? t("mfa.stepUp.description")}
            </p>
            {otpMethods.length ? (
              <OtpEntry
                availableMethods={otpMethods}
                defaultMethod={
                  defaultMethod && defaultMethod !== "webauthn"
                    ? (defaultMethod as Extract<MfaMethod, "totp" | "recovery">)
                    : otpMethods[0]
                }
                loading={verifying}
                error={error}
                onSubmit={handleOtpSubmit}
              />
            ) : null}
            {hasWebAuthn && webAuthnChallenge ? (
              <WebAuthnPrompt
                options={webAuthnChallenge.options ?? null}
                autoStart
                loading={verifying}
                error={error}
                onResolve={async (credential) => {
                  await handleSubmit({
                    method: "webauthn",
                    credential: credential as unknown as Record<string, unknown>,
                    challengeToken: webAuthnChallenge.challenge_token,
                  })
                }}
              />
            ) : null}
          </div>
        </div>
        <div className="flex gap-2 justify-end px-6 pb-6 pt-2">
          <button
            onClick={onClose}
            className="inline-flex items-center justify-center gap-2 px-4 py-2 text-base font-bold rounded-lg transition-all duration-200 text-page-text hover:bg-page-text/10"
          >
            {t("common:buttons.cancel")}
          </button>
        </div>
      </div>
    </div>
  )
}

export default StepUpDialog
