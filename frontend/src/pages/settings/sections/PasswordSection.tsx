import { useTranslation } from "react-i18next"

import { Button, TextField, CircularProgress, AccordionSection } from "@/components/settings"

import type { SettingsSectionProps } from "@/pages/settings/types"

interface PasswordSectionProps extends SettingsSectionProps {
  currentPasswordValue: string
  newPasswordValue: string
  confirmPasswordValue: string
  currentPasswordError: string | null
  passwordError: string | null
  isNewPasswordError: boolean
  confirmPasswordMessage: string | null
  passwordBusy: boolean
  onCurrentPasswordChange: (value: string) => void
  onNewPasswordChange: (value: string) => void
  onConfirmPasswordChange: (value: string) => void
  onSubmit: () => Promise<void>
}

export function PasswordSection({
  currentPasswordValue,
  newPasswordValue,
  confirmPasswordValue,
  currentPasswordError,
  passwordError,
  isNewPasswordError,
  confirmPasswordMessage,
  passwordBusy,
  onCurrentPasswordChange,
  onNewPasswordChange,
  onConfirmPasswordChange,
  onSubmit,
}: PasswordSectionProps) {
  const { t } = useTranslation(["settings"])

  return (
    <AccordionSection
      title={t("settings:security.password.title")}
      subtitle={t("settings:security.password.subtitle")}
    >
      <form
        className="flex flex-col gap-3"
        onSubmit={(event) => {
          event.preventDefault()
          void onSubmit()
        }}
      >
        <div className="flex flex-col sm:flex-row gap-2.5">
          <TextField
            fullWidth
            type="password"
            size="sm"
            label={t("settings:security.password.currentLabel")}
            value={currentPasswordValue}
            onChange={(event) => onCurrentPasswordChange(event.target.value)}
            error={Boolean(currentPasswordError)}
            helperText={currentPasswordError ?? undefined}
            autoComplete="current-password"
          />
          <TextField
            fullWidth
            type="password"
            size="sm"
            label={t("settings:security.password.newLabel")}
            value={newPasswordValue}
            onChange={(event) => onNewPasswordChange(event.target.value)}
            error={isNewPasswordError}
            helperText={isNewPasswordError ? (passwordError ?? undefined) : undefined}
            autoComplete="new-password"
          />
        </div>
        <div className="flex flex-col sm:flex-row gap-2.5 items-start sm:items-center">
          <TextField
            fullWidth
            type="password"
            size="sm"
            label={t("settings:security.password.confirmLabel")}
            value={confirmPasswordValue}
            onChange={(event) => onConfirmPasswordChange(event.target.value)}
            error={Boolean(confirmPasswordMessage)}
            helperText={confirmPasswordMessage ?? undefined}
            autoComplete="new-password"
          />
          <Button
            type="submit"
            variant="solid"
            disabled={passwordBusy}
            leadingIcon={passwordBusy ? <CircularProgress size={18} color="inherit" /> : undefined}
          >
            {passwordBusy
              ? t("settings:security.password.updating")
              : t("settings:security.password.updateButton")}
          </Button>
        </div>
      </form>
    </AccordionSection>
  )
}
