import { useTranslation } from "react-i18next"
import {
  Button,
  TextField,
  Alert,
  CircularProgress,
  SectionCard,
  SectionTitle,
  SectionSubtitle,
  AccordionSection,
} from "@/components/settings"

import type { SettingsSectionProps } from "@/pages/settings/types"

interface EmailSectionProps extends SettingsSectionProps {
  emailValue: string
  emailPassword: string
  emailBusy: boolean
  emailError: string | null
  emailPasswordError: string | null
  pendingEmail: string | null
  onEmailChange: (value: string) => void
  onPasswordChange: (value: string) => void
  onSubmit: () => Promise<void>
}

export function EmailSection({
  emailValue,
  emailPassword,
  emailBusy,
  emailError,
  emailPasswordError,
  pendingEmail,
  onEmailChange,
  onPasswordChange,
  onSubmit,
}: EmailSectionProps) {
  const { t } = useTranslation(["settings", "common"])

  return (
    <SectionCard component="section">
      <div className="flex flex-col gap-2 mb-4">
        <SectionTitle variant="subtitle1">{t("settings:security.account.title")}</SectionTitle>
        <SectionSubtitle variant="body2">{t("settings:security.account.subtitle")}</SectionSubtitle>
      </div>

      <div className="flex flex-col gap-3">
        <AccordionSection
          title={t("settings:security.email.title")}
          subtitle={t("settings:security.email.subtitle")}
        >
          <form
            className="flex flex-col gap-3"
            onSubmit={(event) => {
              event.preventDefault()
              void onSubmit()
            }}
          >
            {pendingEmail ? (
              <Alert severity="info">
                {t("settings:security.email.pendingNotice", { email: pendingEmail })}
              </Alert>
            ) : null}

            <div className="flex flex-col sm:flex-row gap-2.5 items-start sm:items-end">
              <TextField
                fullWidth
                size="sm"
                label={t("settings:security.email.newLabel")}
                type="email"
                value={emailValue}
                onChange={(e) => onEmailChange(e.target.value)}
                error={Boolean(emailError)}
                helperText={emailError ?? undefined}
                disabled={emailBusy}
              />
              <TextField
                fullWidth
                size="sm"
                label={t("settings:security.email.passwordLabel")}
                type="password"
                value={emailPassword}
                onChange={(e) => onPasswordChange(e.target.value)}
                error={Boolean(emailPasswordError)}
                helperText={emailPasswordError ?? undefined}
                disabled={emailBusy}
                autoComplete="current-password"
              />
              <Button
                type="submit"
                variant="solid"
                disabled={emailBusy || !emailValue || !emailPassword}
                className="h-10 shrink-0 w-full sm:w-auto"
                leadingIcon={emailBusy ? <CircularProgress size={18} color="inherit" /> : undefined}
              >
                {t("common:buttons.save")}
              </Button>
            </div>
          </form>
        </AccordionSection>
      </div>
    </SectionCard>
  )
}
