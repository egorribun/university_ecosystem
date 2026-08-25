import { useDndSettings } from "./hooks"
import { NotificationsSection } from "./sections"
import type { SetSnackbar } from "./types"

interface SettingsNotificationsProps {
  setSnackbar: SetSnackbar
}

export function SettingsNotifications({ setSnackbar }: SettingsNotificationsProps) {
  const {
    dndEnabled,
    dndStart,
    dndEnd,
    dndSaving,
    handleDndToggle,
    handleDndStartChange,
    handleDndStartBlur,
    handleDndEndChange,
    handleDndEndBlur,
  } = useDndSettings(setSnackbar)

  return (
    <div className="flex w-full flex-col gap-8 sm:gap-10 xl:max-w-(--layout-max-page) 2xl:gap-12 animate-fade-in delay-200">
      <NotificationsSection
        setSnackbar={setSnackbar}
        dndEnabled={dndEnabled}
        dndStart={dndStart}
        dndEnd={dndEnd}
        dndSaving={dndSaving}
        onDndToggle={handleDndToggle}
        onDndStartChange={handleDndStartChange}
        onDndStartBlur={handleDndStartBlur}
        onDndEndChange={handleDndEndChange}
        onDndEndBlur={handleDndEndBlur}
      />
    </div>
  )
}
