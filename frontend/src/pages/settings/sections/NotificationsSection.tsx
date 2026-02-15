import { useCallback, type ChangeEvent } from "react"
import { useTranslation } from "react-i18next"
import { Bell } from "lucide-react"

import { usePushPreferences } from "../../../hooks/usePushPreferences"

import {
  TextField,
  SwitchControl,
  SectionCard,
  SectionTitle,
  SectionSubtitle,
  AccordionSection,
} from "../../../components/settings"

import type { SettingsSectionProps } from "../types"

interface NotificationsSectionProps extends SettingsSectionProps {
  dndEnabled: boolean
  dndStart: string
  dndEnd: string
  dndSaving: boolean
  onDndToggle: (event: ChangeEvent<HTMLInputElement>, checked: boolean) => void
  onDndStartChange: (event: ChangeEvent<HTMLInputElement>) => void
  onDndStartBlur: (event: React.FocusEvent<HTMLInputElement>) => void
  onDndEndChange: (event: ChangeEvent<HTMLInputElement>) => void
  onDndEndBlur: (event: React.FocusEvent<HTMLInputElement>) => void
}

export function NotificationsSection({
  setSnackbar,
  dndEnabled,
  dndStart,
  dndEnd,
  dndSaving,
  onDndToggle,
  onDndStartChange,
  onDndStartBlur,
  onDndEndChange,
  onDndEndBlur,
}: NotificationsSectionProps) {
  const { t } = useTranslation(["settings", "notifications"])

  const {
    pushSupported,
    notificationPermission,
    notificationsEnabled,
    pushBusy,
    pushInitializing,
    permissionText,
    enableNotifications,
    disableNotifications,
  } = usePushPreferences({ onNotify: setSnackbar })

  const handleNotificationsToggle = useCallback(
    (_: ChangeEvent<HTMLInputElement>, checked: boolean) => {
      if (pushBusy || pushInitializing) return
      if (checked) void enableNotifications()
      else void disableNotifications()
    },
    [disableNotifications, enableNotifications, pushBusy, pushInitializing]
  )

  const permissionDenied = notificationPermission === "denied"

  return (
    <SectionCard component="section">
      <div className="flex flex-col gap-2 mb-4">
        <SectionTitle variant="subtitle1">{t("settings:notifications.title")}</SectionTitle>
        <SectionSubtitle variant="body2">{t("settings:notifications.subtitle")}</SectionSubtitle>
      </div>

      <AccordionSection
        title={t("settings:notifications.push.title")}
        subtitle={t("settings:notifications.push.subtitle")}
      >
        {pushInitializing ? (
          <div className="flex items-center gap-2 py-2">
            <div className="animate-pulse w-4 h-4 rounded-full bg-(--border-strong)" />
            <span className="text-sm text-text-muted">{t("settings:notifications.loading")}</span>
          </div>
        ) : !pushSupported ? (
          <p className="text-sm text-text-muted-more">{t("settings:notifications.notSupported")}</p>
        ) : permissionDenied ? (
          <div className="flex flex-col gap-2">
            <div className="flex items-center gap-2.5">
              <Bell className="w-5 h-5 text-warning-text" />
              <div className="flex flex-col">
                <p className="text-sm font-semibold text-text-muted-more">
                  {t("settings:notifications.status", { status: permissionText })}
                </p>
              </div>
            </div>
          </div>
        ) : (
          <div className="flex flex-col gap-4">
            <label className="m-0 flex h-11 items-center gap-2.5 cursor-pointer">
              <SwitchControl
                checked={notificationsEnabled}
                onChange={handleNotificationsToggle}
                disabled={pushBusy || pushInitializing}
                aria-label={t("settings:notifications.toggles.notifications.aria")}
              />
              <span className="font-semibold text-text-soft">
                {t("settings:notifications.toggles.notifications.label")}
              </span>
            </label>

            <label className="m-0 flex min-h-(--min-h-touch) items-center gap-2.5 cursor-pointer">
              <SwitchControl
                checked={dndEnabled}
                onChange={onDndToggle}
                disabled={dndSaving}
                aria-label={t("settings:notifications.toggles.dnd.aria")}
              />
              <span className="font-semibold text-text-soft">
                {t("settings:notifications.toggles.dnd.label")}
              </span>
            </label>

            <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
              <TextField
                type="time"
                label={t("settings:dnd.start")}
                value={dndStart}
                onChange={onDndStartChange}
                onBlur={onDndStartBlur}
                disabled={!dndEnabled || dndSaving}
                size="small"
              />
              <TextField
                type="time"
                label={t("settings:dnd.end")}
                value={dndEnd}
                onChange={onDndEndChange}
                onBlur={onDndEndBlur}
                disabled={!dndEnabled || dndSaving}
                size="small"
              />
            </div>
          </div>
        )}
      </AccordionSection>
    </SectionCard>
  )
}
