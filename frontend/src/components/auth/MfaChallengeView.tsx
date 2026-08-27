import { useState } from "react"
import { useTranslation } from "react-i18next"
import { Mail, RotateCcw, ShieldCheck, Zap } from "lucide-react"

import ParticleAuthBackground from "@/components/ui/ParticleAuthBackground"
import OtpEntry from "@/components/mfa/OtpEntry"
import { Button } from "@/components/ui/Button"
import type { useMfaFlow } from "@/hooks/auth/useLoginFlow"

type MfaChallengeViewProps = {
  activeEmail: string
  mfa: ReturnType<typeof useMfaFlow>
}

export function MfaChallengeView({ activeEmail, mfa }: MfaChallengeViewProps) {
  const { t } = useTranslation(["auth"])
  const [recoveryCode, setRecoveryCode] = useState("")

  const {
    otpChallenge,
    emailChallenge,
    resendSeconds,
    mfaBusy,
    mfaError,
    mfaErrorSource,
    generalMfaError,
    handleOtpVerify,
    handleEmailOtpVerify,
    handleResendEmailOtp,
    showRecoveryInput,
    setShowRecoveryInput,
    handleRecoveryVerify,
  } = mfa

  return (
    <div className="fixed inset-0 min-h-screen w-full overflow-y-auto overscroll-contain bg-linear-to-b from-slate-50 to-slate-100 dark:from-slate-950 dark:to-slate-900">
      <ParticleAuthBackground />
      <div className="relative z-navbar flex min-h-screen items-center justify-center px-4 py-12 pt-[max(3rem,var(--safe-area-top))] pb-[max(3rem,var(--safe-area-bottom))] sm:px-6 lg:px-8">
        <div className="w-full max-w-[42rem] rounded-4xl glass-high-fidelity p-8">
          <div className="flex flex-col items-center gap-6 text-center">
            <div className="inline-flex items-center gap-2 rounded-full border border-glass-border-subtle bg-surface-hover/(--opacity-subtle) px-4 py-1 text-sm font-semibold tracking-wide text-text-primary">
              <ShieldCheck className="h-4 w-4" aria-hidden="true" />
              {t("auth:mfa.verifyTitle")}
            </div>
            <div className="space-y-3">
              <h1 className="text-3xl font-extrabold leading-tight sm:text-4xl">
                {t("auth:mfa.verifySubtitle", {
                  email: activeEmail || t("auth:mfa.unknownEmail"),
                })}
              </h1>
            </div>

            {generalMfaError ? (
              <div
                role="alert"
                aria-live="assertive"
                className="w-full rounded-md border border-error-border/(--opacity-medium) bg-error-bg/(--opacity-dim) px-4 py-3 text-sm font-semibold text-error-text"
              >
                {generalMfaError}
              </div>
            ) : null}

            {showRecoveryInput ? (
              <form
                className="w-full space-y-4"
                onSubmit={(event) => {
                  event.preventDefault()
                  const value = recoveryCode.trim()
                  if (value) handleRecoveryVerify(value)
                }}
              >
                <h3 className="text-lg font-black tracking-tight text-center text-text-primary">
                  {t("auth:mfa.recovery.heading")}
                </h3>
                <p className="text-sm text-center text-(--text-secondary) font-medium leading-relaxed">
                  {t("auth:mfa.recovery.description")}
                </p>
                <input
                  type="text"
                  placeholder="XXXX-XXXX-XXXX-XXXX"
                  autoComplete="one-time-code"
                  disabled={mfaBusy}
                  className="w-full h-14 text-center text-xl font-mono tracking-widest rounded-2xl bg-(--bg-surface-raised)/(--opacity-medium) text-text-primary border-2 border-(--glass-border)/(--opacity-dim) focus:outline-none focus:border-(--brand-main) focus:ring-4 focus:ring-(--brand-main)/(--opacity-subtle) transition-all duration-base"
                  aria-label={t("auth:mfa.recovery.inputLabel")}
                  value={recoveryCode}
                  onChange={(event) => setRecoveryCode(event.target.value)}
                />
                <Button
                  type="submit"
                  disabled={mfaBusy}
                  loading={mfaBusy}
                  variant="solid"
                  size="lg"
                  fullWidth
                >
                  {t("auth:mfa.recovery.submit")}
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="text-brand hover:underline"
                  onClick={() => {
                    setRecoveryCode("")
                    setShowRecoveryInput(false)
                  }}
                >
                  {t("auth:mfa.recovery.useOtp")}
                </Button>
              </form>
            ) : (
              <>
                {emailChallenge ? (
                  <div className="w-full space-y-4 rounded-2xl border border-border-subtle bg-surface-raised p-4 text-start">
                    <div className="flex items-start gap-3">
                      <Mail className="mt-0.5 h-5 w-5 shrink-0 text-brand" aria-hidden="true" />
                      <div>
                        <h2 className="font-bold text-text-primary">{t("auth:mfa.email.title")}</h2>
                        <p className="text-sm text-text-secondary">
                          {t("auth:mfa.email.sentTo", {
                            hint: emailChallenge.delivery_hint ?? activeEmail,
                          })}
                        </p>
                      </div>
                    </div>
                    <OtpEntry
                      method="email_otp"
                      loading={mfaBusy}
                      error={mfaErrorSource === "email_otp" ? mfaError : null}
                      helperText={t("auth:mfa.email.expires")}
                      onSubmit={handleEmailOtpVerify}
                    />
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      fullWidth
                      disabled={mfaBusy || resendSeconds > 0}
                      onClick={handleResendEmailOtp}
                      leadingIcon={<RotateCcw className="h-4 w-4" aria-hidden="true" />}
                    >
                      {resendSeconds > 0
                        ? t("auth:mfa.email.resendIn", { seconds: resendSeconds })
                        : t("auth:mfa.email.resend")}
                    </Button>
                  </div>
                ) : null}

                {otpChallenge && (
                  <>
                    {emailChallenge && (
                      <div className="relative z-base w-full py-2">
                        <div className="absolute inset-0 flex items-center">
                          <div className="w-full border-t border-glass-border-subtle"></div>
                        </div>
                        <div className="relative flex justify-center text-xs uppercase">
                          <span className="bg-surface px-2 text-text-secondary">
                            {t("auth:mfa.or", { defaultValue: "OR" })}
                          </span>
                        </div>
                      </div>
                    )}

                    <div className="w-full">
                      <OtpEntry
                        method="totp"
                        loading={mfaBusy}
                        error={mfaErrorSource === "totp" ? mfaError : null}
                        helperText={null}
                        onSubmit={handleOtpVerify}
                      />
                    </div>
                  </>
                )}

                {otpChallenge || emailChallenge ? (
                  <div className="flex flex-col items-center gap-3">
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      className="text-brand hover:underline"
                      onClick={() => setShowRecoveryInput(true)}
                      id="use-recovery-code-toggle"
                    >
                      {t("auth:mfa.recovery.useRecovery")}
                    </Button>
                  </div>
                ) : null}

                {!otpChallenge && !emailChallenge && (
                  <div className="w-full rounded-md border border-warning-border/(--opacity-medium) bg-warning-bg/(--opacity-subtle) px-4 py-3 text-sm font-semibold text-warning-text">
                    {t("auth:mfa.noMethods")}
                  </div>
                )}
              </>
            )}

            <Button
              type="button"
              onClick={() => window.location.reload()}
              variant="outline"
              size="sm"
              className="rounded-full border-brand/(--opacity-medium) text-brand hover:bg-brand/(--opacity-subtle)"
              leadingIcon={<Zap className="h-4 w-4" aria-hidden="true" />}
            >
              {t("auth:mfa.startOver")}
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}
