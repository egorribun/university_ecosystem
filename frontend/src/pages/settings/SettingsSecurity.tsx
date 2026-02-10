import React from "react"
import { useTranslation } from "react-i18next"
import { useAuth } from "../../contexts/AuthContext"

import { EmailSection, PasswordSection, SessionsSection } from "./sections"

import {
  useEmailChange,
  usePasswordChange,
  useSessionManagement,
  useTotpEnrollment,
  useWebAuthn,
} from "./hooks"

import {
  SectionCard,
  SectionTitle,
  SectionSubtitle,
  AccordionSection,
  Button,
  Chip,
  Alert,
} from "../../components/settings"

import { TotpQrDisplay } from "../../components/mfa/TotpQrDisplay"
import { OtpEntry } from "../../components/mfa/OtpEntry"
import { Smartphone, Lock, Fingerprint, Trash2 } from "lucide-react"

import type { SetSnackbar } from "./types"

interface SettingsSecurityProps {
  setSnackbar: SetSnackbar
  openStepUpFor: (action: () => Promise<void>) => void
  isActive: boolean
}

export function SettingsSecurity({ setSnackbar, openStepUpFor, isActive }: SettingsSecurityProps) {
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

  // --- Sessions ---
  const {
    sessions,
    sortedSessions,
    sessionsFetching,
    sessionsIsError,
    sessionsError,
    handleRevokeSession,
    handleRevokeAllSessions,
    revokeSessionBusy,
    revokeAllSessionsBusy,
    formatSessionTimestamp,
  } = useSessionManagement({
    setSnackbar,
    tabActive: isActive,
    openStepUpFor,
  })

  const sessionsErrorMessage = React.useMemo(() => {
    if (!sessionsIsError) return null
    const err = sessionsError as any
    if (err?.response?.data?.detail) {
      return String(err.response.data.detail)
    }
    return sessionsError instanceof Error ? sessionsError.message : t("settings:sessions.error")
  }, [sessionsIsError, sessionsError, t])

  // --- TOTP ---
  // --- TOTP ---
  const {
    totpDraft,
    totpBusy,
    totpError,
    activeTotp,
    pendingTotpEnrollment,
    defaultMethodText,
    handleStartTotp,
    handleConfirmTotp,
    handleCancelTotp,
    handleDisableTotp,
    formatDateTime,
  } = useTotpEnrollment({
    setSnackbar,
    openStepUpFor,
  })

  // --- WebAuthn ---
  const {
    credentials: webauthnCredentials,
    credentialsLoading: webauthnFetching,
    busy: webauthnBusy,
    supported: webauthnSupported,
    handleRegister: handleRegisterWebAuthn,
    handleDelete: handleDeleteWebAuthn,
  } = useWebAuthn({
    setSnackbar,
    tabActive: isActive,
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
          <SectionTitle variant="subtitle1">{t("settings:security.mfa.title")}</SectionTitle>
          <SectionSubtitle variant="body2">{t("settings:security.mfa.subtitle")}</SectionSubtitle>
        </div>

        <div className="flex flex-col gap-3">
          {/* TOTP */}
          <AccordionSection
            title={t("settings:security.mfa.totp.title")}
            subtitle={t("settings:security.mfa.totp.subtitle")}
          >
            <div className="flex flex-col gap-4">
              {totpError ? (
                <Alert severity="error" variant="outlined">
                  {totpError}
                </Alert>
              ) : null}

              {/* Active Enrollment */}
              {activeTotp.map((enrollment) => (
                <div
                  key={enrollment.id}
                  className="flex items-center justify-between p-3 rounded-lg bg-(--bg-surface-hover) border border-(--border-subtle)"
                >
                  <div className="flex items-center gap-3">
                    <Smartphone className="w-5 h-5 text-(--text-secondary)" />
                    <div className="flex flex-col">
                      <span className="font-semibold text-sm">
                        {enrollment.label ||
                          t("settings:security.mfa.totp.defaultLabel", "Authenticator App")}
                      </span>
                      <span className="text-xs text-(--text-secondary)">
                        {t("settings:security.mfa.totp.addedOn", {
                          date: formatDateTime(enrollment.created_at),
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
                    {t("settings:security.mfa.remove")}
                  </Button>
                </div>
              ))}

              {/* Draft Enrollment Flow */}
              {totpDraft ? (
                <div className="flex flex-col gap-4 p-4 rounded-lg border border-(--border-subtle) bg-(--bg-surface-active)">
                  <TotpQrDisplay secret={totpDraft.secret} otpauthUrl={totpDraft.otpauth_url} />
                  <div className="flex flex-col gap-2">
                    <OtpEntry loading={totpBusy} onSubmit={handleConfirmTotp} />
                    <Button
                      variant="text"
                      color="error"
                      size="small"
                      onClick={handleCancelTotp}
                      className="self-center"
                    >
                      {t("common:buttons.cancel")}
                    </Button>
                  </div>
                </div>
              ) : (
                activeTotp.length === 0 && (
                  <Button
                    variant="outlined"
                    onClick={() => handleStartTotp()}
                    disabled={totpBusy}
                    className="self-start"
                  >
                    {t("settings:security.mfa.totp.add")}
                  </Button>
                )
              )}
            </div>
          </AccordionSection>

          {/* WebAuthn */}
          <AccordionSection
            title={t("settings:security.mfa.webauthn.title")}
            subtitle={t("settings:security.mfa.webauthn.subtitle")}
          >
            <div className="flex flex-col gap-4">
              {!webauthnSupported ? (
                <Alert severity="warning" variant="outlined">
                  {t("settings:security.mfa.webauthn.notSupported")}
                </Alert>
              ) : (
                <>
                  <div className="flex flex-col gap-2">
                    {webauthnCredentials.map((cred) => (
                      <div
                        key={cred.id}
                        className="flex items-center justify-between p-3 rounded-lg bg-(--bg-surface-hover) border border-(--border-subtle)"
                      >
                        <div className="flex items-center gap-3">
                          <Fingerprint className="w-5 h-5 text-(--text-secondary)" />
                          <div className="flex flex-col">
                            <span className="font-semibold text-sm">
                              {cred.label ||
                                t("settings:security.mfa.webauthn.defaultLabel", "Passkey")}
                            </span>
                            <span className="text-xs text-(--text-secondary)">
                              {t("settings:security.mfa.webauthn.addedOn", {
                                date: formatDateTime(cred.created_at),
                              })}
                            </span>
                          </div>
                        </div>
                        <Button
                          size="small"
                          color="error"
                          onClick={() => handleDeleteWebAuthn(cred.id)}
                          disabled={webauthnBusy}
                        >
                          <Trash2 className="w-4 h-4" />
                        </Button>
                      </div>
                    ))}
                  </div>

                  <Button
                    variant="outlined"
                    onClick={() => handleRegisterWebAuthn()}
                    disabled={webauthnBusy}
                    className="self-start"
                  >
                    {t("settings:security.mfa.webauthn.add")}
                  </Button>
                </>
              )}
            </div>
          </AccordionSection>
        </div>
      </SectionCard>

      <SessionsSection
        setSnackbar={setSnackbar}
        sessions={sessions}
        sortedSessions={sortedSessions}
        sessionsFetching={sessionsFetching}
        sessionsErrorMessage={sessionsErrorMessage}
        revokeAllPending={revokeAllSessionsBusy}
        revokeSessionPending={revokeSessionBusy}
        onRevokeSession={handleRevokeSession}
        onRevokeAllSessions={handleRevokeAllSessions}
        formatSessionTimestamp={formatSessionTimestamp}
      />
    </div>
  )
}
