import { useTranslation } from "react-i18next"
import { useAuth } from "@/contexts/AuthContext"

import { EmailSection, PasswordSection } from "./sections"

import { useEmailChange, usePasswordChange, useTotpEnrollment, useEmailMfa } from "./hooks"

import {
  SectionCard,
  SectionTitle,
  SectionSubtitle,
  AccordionSection,
  Button,
  Alert,
} from "@/components/settings"

import { TotpQrDisplay } from "@/components/mfa/TotpQrDisplay"
import { OtpEntry } from "@/components/mfa/OtpEntry"
import { MailCheck, Smartphone } from "lucide-react"

import type { SetSnackbar } from "./types"

interface SettingsSecurityProps {
  setSnackbar: SetSnackbar
  openStepUpFor: (action: () => Promise<void>) => void
  /** Kept optional for compatibility with embedded security surfaces. */
  isActive?: boolean
}

export function SettingsSecurity({ setSnackbar, openStepUpFor }: SettingsSecurityProps) {
  const { t } = useTranslation(["settings", "common"])
  const { user } = useAuth()

  // --- Email Change ---
  const {
    emailValue,
    emailPassword,
    emailBusy,
    emailError,
    emailPasswordError,
    pendingEmail,
    setEmailValue,
    setEmailPassword,
    handleEmailSubmit,
  } = useEmailChange({
    setSnackbar,
    openStepUpFor,
  })

  // --- Password Change ---
  const {
    currentPasswordValue,
    newPasswordValue,
    confirmPasswordValue,
    passwordBusy,
    passwordError,
    currentPasswordError,
    isNewPasswordError,
    confirmPasswordMessage,
    setCurrentPasswordValue,
    setNewPasswordValue,
    setConfirmPasswordValue,
    handlePasswordSubmit,
  } = usePasswordChange({
    setSnackbar,
    sessionsQueryKey: ["auth", "sessions", user?.id ?? "me"],
    openStepUpFor,
  })

  // --- TOTP ---
  // --- TOTP ---
  const {
    totpDraft,
    totpBusy,
    totpError,
    activeTotp,
    handleStartTotp,
    handleConfirmTotp,
    handleCancelTotp,
    handleDisableTotp,
    formatDateTime,
  } = useTotpEnrollment({
    setSnackbar,
    openStepUpFor,
  })

  // --- Email MFA ---
  const {
    emailChallenge,
    emailMfaBusy,
    emailMfaError,
    emailMfaEnabled,
    emailVerified,
    handleStartEmailMfa,
    handleConfirmEmailMfa,
    handleResendEmailMfa,
    handleCancelEmailMfa,
    handleDisableEmailMfa,
  } = useEmailMfa({
    setSnackbar,
    openStepUpFor,
  })

  return (
    <div className="flex w-full flex-col gap-5 sm:gap-6 xl:max-w-(--layout-max-page) 2xl:max-w-(--layout-max-wide) animate-fade-in delay-200">
      <EmailSection
        setSnackbar={setSnackbar}
        emailValue={emailValue}
        emailPassword={emailPassword}
        emailBusy={emailBusy}
        emailError={emailError}
        emailPasswordError={emailPasswordError}
        pendingEmail={pendingEmail}
        onEmailChange={setEmailValue}
        onPasswordChange={setEmailPassword}
        onSubmit={handleEmailSubmit}
      />

      <PasswordSection
        setSnackbar={setSnackbar}
        currentPasswordValue={currentPasswordValue}
        newPasswordValue={newPasswordValue}
        confirmPasswordValue={confirmPasswordValue}
        currentPasswordError={currentPasswordError}
        passwordError={passwordError}
        isNewPasswordError={isNewPasswordError}
        confirmPasswordMessage={confirmPasswordMessage}
        passwordBusy={passwordBusy}
        onCurrentPasswordChange={setCurrentPasswordValue}
        onNewPasswordChange={setNewPasswordValue}
        onConfirmPasswordChange={setConfirmPasswordValue}
        onSubmit={handlePasswordSubmit}
      />

      {/* MFA Section */}
      <SectionCard component="section">
        <div className="flex flex-col gap-2 mb-4">
          <SectionTitle variant="subtitle1">{t("settings:security.title")}</SectionTitle>
          <SectionSubtitle variant="body2">{t("settings:security.subtitle")}</SectionSubtitle>
        </div>

        <div className="flex flex-col gap-3">
          {/* TOTP */}
          <AccordionSection
            title={t("settings:security.method.totp")}
            subtitle={t("settings:security.totp.description")}
          >
            <div className="flex flex-col gap-4">
              {totpError ? <Alert severity="error">{totpError}</Alert> : null}

              {/* Active Enrollment */}
              {activeTotp.map((enrollment) => (
                <div
                  key={enrollment.id}
                  className="flex items-center justify-between p-3 rounded-xs bg-(--bg-surface-hover) border border-(--border-subtle)"
                >
                  <div className="flex items-center gap-3">
                    <Smartphone className="w-5 h-5 text-(--text-secondary)" />
                    <div className="flex flex-col">
                      <span className="font-semibold text-sm">
                        {enrollment.label || t("settings:security.totp.unnamed", { index: 1 })}
                      </span>
                      <span className="text-xs text-(--text-secondary)">
                        {t("settings:security.totp.added", {
                          value: formatDateTime(enrollment.created_at),
                        })}
                      </span>
                    </div>
                  </div>
                  <Button
                    size="small"
                    variant="outlined"
                    color="error"
                    disabled={totpBusy}
                    onClick={() => handleDisableTotp(enrollment.id)}
                  >
                    {t("settings:security.totp.remove")}
                  </Button>
                </div>
              ))}

              {/* Draft Enrollment Flow */}
              {totpDraft ? (
                <div className="flex flex-col gap-4 p-4 rounded-xs border border-(--border-subtle) bg-(--bg-surface-active)">
                  <div className="flex flex-col gap-1">
                    <h4 className="text-sm font-bold text-text-primary">
                      {t("settings:security.totp.pendingTitle")}
                    </h4>
                    <p className="text-xs text-(--text-secondary)">
                      {t("settings:security.totp.pendingDescription")}
                    </p>
                  </div>

                  <TotpQrDisplay secret={totpDraft.secret} otpauthUrl={totpDraft.otpauth_url} />

                  <div className="flex flex-col gap-2">
                    <OtpEntry loading={totpBusy} onSubmit={handleConfirmTotp} error={totpError} />

                    <p className="text-xs text-(--text-tertiary) text-center px-2">
                      {t("settings:security.totp.pendingHelper")}
                    </p>

                    <Button
                      variant="text"
                      color="error"
                      size="small"
                      onClick={handleCancelTotp}
                      className="self-center mt-1"
                    >
                      {t("settings:security.totp.cancel")}
                    </Button>
                  </div>
                </div>
              ) : activeTotp.length === 0 ? (
                <Button
                  variant="outlined"
                  onClick={() => handleStartTotp()}
                  disabled={totpBusy}
                  className="self-start"
                >
                  {t("settings:security.totp.add")}
                </Button>
              ) : (
                <p className="text-sm text-(--text-secondary) bg-glass-tint1 border border-glass-border rounded-sm px-4 py-3 shadow-glass">
                  {t("settings:security.totp.limitReached")}
                </p>
              )}
            </div>
          </AccordionSection>

          {/* Email OTP */}
          <AccordionSection
            title={t("settings:security.method.emailOtp")}
            subtitle={t("settings:security.emailMfa.description")}
          >
            <div className="flex flex-col gap-4">
              {emailMfaError ? <Alert severity="error">{emailMfaError}</Alert> : null}
              {emailChallenge ? (
                <div className="flex flex-col gap-3 rounded-xl border border-border-subtle bg-surface-raised p-4">
                  <div className="flex items-start gap-3">
                    <MailCheck className="mt-0.5 h-5 w-5 text-brand" aria-hidden="true" />
                    <p className="text-sm text-text-secondary">
                      {t("settings:security.emailMfa.sentTo", {
                        hint: emailChallenge.delivery_hint ?? user?.email ?? "",
                      })}
                    </p>
                  </div>
                  <OtpEntry
                    method="email_otp"
                    loading={emailMfaBusy}
                    error={emailMfaError}
                    onSubmit={handleConfirmEmailMfa}
                  />
                  <div className="flex flex-wrap gap-2">
                    <Button
                      variant="outlined"
                      size="small"
                      disabled={emailMfaBusy}
                      onClick={handleResendEmailMfa}
                    >
                      {t("settings:security.emailMfa.resend")}
                    </Button>
                    <Button
                      variant="text"
                      size="small"
                      disabled={emailMfaBusy}
                      onClick={handleCancelEmailMfa}
                    >
                      {t("common:buttons.cancel")}
                    </Button>
                  </div>
                </div>
              ) : (
                <Button
                  variant="outlined"
                  color={emailMfaEnabled ? "error" : undefined}
                  onClick={
                    emailMfaEnabled ? handleDisableEmailMfa : () => void handleStartEmailMfa()
                  }
                  disabled={emailMfaBusy}
                  className="self-start"
                >
                  {emailMfaEnabled
                    ? t("settings:security.emailMfa.disable")
                    : emailVerified
                      ? t("settings:security.emailMfa.enable")
                      : t("settings:security.emailMfa.verifyEmail")}
                </Button>
              )}
            </div>
          </AccordionSection>
        </div>
      </SectionCard>
    </div>
  )
}
