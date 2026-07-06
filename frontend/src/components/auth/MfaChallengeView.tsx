import { useTranslation } from "react-i18next"
import { ShieldCheck, Fingerprint, Zap } from "lucide-react"

import ParticleAuthBackground from "@/components/ui/ParticleAuthBackground"
import OtpEntry from "@/components/mfa/OtpEntry"
import { Button } from "@/components/ui/Button"
import { Checkbox } from "@/components/ui/Checkbox"
import type { useMfaFlow } from "@/hooks/auth/useLoginFlow"

type MfaChallengeViewProps = {
  activeEmail: string
  trustDevice: boolean
  onTrustDeviceChange: (value: boolean) => void
  webauthnSupported: boolean
  mfa: ReturnType<typeof useMfaFlow>
}

export function MfaChallengeView({
  activeEmail,
  trustDevice,
  onTrustDeviceChange,
  webauthnSupported,
  mfa,
}: MfaChallengeViewProps) {
  const { t } = useTranslation(["auth"])

  const {
    otpChallenge,
    webauthnChallenge,
    mfaBusy,
    mfaError,
    mfaErrorSource,
    generalMfaError,
    handleOtpVerify,
    handleWebAuthnVerify,
    showRecoveryInput,
    setShowRecoveryInput,
    handleRecoveryVerify,
  } = mfa

  return (
    <div className="fixed inset-0 min-h-screen w-full bg-linear-to-b from-slate-50 to-slate-100 dark:from-slate-950 dark:to-slate-900">
      <ParticleAuthBackground />
      <div className="relative z-navbar flex min-h-screen items-center justify-center px-4 py-12 sm:px-6 lg:px-8">
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
              <div className="w-full rounded-md border border-error-border/(--opacity-medium) bg-error-bg/(--opacity-dim) px-4 py-3 text-sm font-semibold text-error-text">
                {generalMfaError}
              </div>
            ) : null}

            {showRecoveryInput ? (
              <div className="w-full space-y-4">
                <h3 className="text-lg font-black tracking-tight text-center text-text-primary">
                  {t("auth:mfa.recovery.heading", { defaultValue: "Ввод резервного кода" })}
                </h3>
                <p className="text-sm text-center text-(--text-secondary) font-medium leading-relaxed">
                  {t("auth:mfa.recovery.description", {
                    defaultValue:
                      "Введите один из ваших резервных кодов восстановления (19 символов).",
                  })}
                </p>
                <input
                  type="text"
                  placeholder="XXXX-XXXX-XXXX-XXXX"
                  disabled={mfaBusy}
                  className="w-full h-14 text-center text-xl font-mono tracking-widest rounded-2xl bg-(--bg-surface-raised)/(--opacity-medium) text-text-primary border-2 border-(--glass-border)/(--opacity-dim) focus:outline-none focus:border-(--brand-main) focus:ring-4 focus:ring-(--brand-main)/(--opacity-subtle) transition-all duration-base"
                  aria-label="MFA recovery code"
                  id="mfa-recovery-code-input"
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      const val = (e.target as HTMLInputElement).value.trim()
                      if (val) handleRecoveryVerify(val, trustDevice)
                    }
                  }}
                />
                <Button
                  type="button"
                  onClick={() => {
                    const input = document.getElementById(
                      "mfa-recovery-code-input"
                    ) as HTMLInputElement
                    const val = input?.value?.trim()
                    if (val) handleRecoveryVerify(val, trustDevice)
                  }}
                  disabled={mfaBusy}
                  loading={mfaBusy}
                  variant="solid"
                  size="lg"
                  fullWidth
                >
                  {t("auth:mfa.recovery.submit", { defaultValue: "Подтвердить код" })}
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="text-brand hover:underline"
                  onClick={() => setShowRecoveryInput(false)}
                >
                  {t("auth:mfa.recovery.useOtp", { defaultValue: "Использовать приложение" })}
                </Button>
              </div>
            ) : (
              <>
                {webauthnChallenge && (
                  <>
                    {webauthnSupported ? (
                      <Button
                        type="button"
                        onClick={() => handleWebAuthnVerify(trustDevice)}
                        disabled={mfaBusy}
                        loading={mfaBusy}
                        variant="solid"
                        size="lg"
                        fullWidth
                        leadingIcon={<Fingerprint className="h-6 w-6" />}
                        className="bg-brand/(--opacity-subtle) text-brand hover:bg-brand/(--opacity-dim)"
                      >
                        {t("auth:mfa.webauthn.useSecurityKey")}
                      </Button>
                    ) : (
                      <div className="w-full rounded-md border border-warning-border/(--opacity-medium) bg-warning-bg/(--opacity-subtle) px-4 py-3 text-sm font-semibold text-warning-text text-center">
                        {t("auth:mfa.webauthn.notSupported", {
                          defaultValue:
                            "WebAuthn is not available in this browser. Use HTTPS or the authenticator code below.",
                        })}
                      </div>
                    )}
                  </>
                )}

                {otpChallenge && (
                  <>
                    {webauthnChallenge && (
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
                        loading={mfaBusy}
                        error={mfaErrorSource === "totp" ? mfaError : null}
                        helperText={null}
                        onSubmit={(code) => handleOtpVerify(code, trustDevice)}
                      />
                    </div>

                    <div className="flex flex-col items-center gap-3">
                      <div className="flex items-center gap-3 text-sm font-medium text-text-primary">
                        <Checkbox
                          checked={trustDevice}
                          onCheckedChange={(checked) => onTrustDeviceChange(checked === true)}
                          disabled={mfaBusy}
                          aria-label={t("auth:actions.trustDevice", {
                            defaultValue: "Trust this device",
                          })}
                        />
                        {t("auth:actions.trustDevice", { defaultValue: "Trust this device" })}
                      </div>

                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        className="text-brand hover:underline"
                        onClick={() => setShowRecoveryInput(true)}
                        id="use-recovery-code-toggle"
                      >
                        {t("auth:mfa.recovery.useRecovery", {
                          defaultValue: "Войти с помощью резервного кода",
                        })}
                      </Button>
                    </div>
                  </>
                )}

                {!otpChallenge && !webauthnChallenge && (
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
