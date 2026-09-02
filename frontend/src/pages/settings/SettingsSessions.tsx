import { useMemo } from "react"
import { useTranslation } from "react-i18next"

import { useSessionManagement } from "./hooks"
import { SessionsSection } from "./sections"
import type { SetSnackbar } from "./types"

interface SettingsSessionsProps {
  setSnackbar: SetSnackbar
  openStepUpFor: (action: () => Promise<void>) => void
  isActive: boolean
}

export function SettingsSessions({ setSnackbar, openStepUpFor, isActive }: SettingsSessionsProps) {
  const { t } = useTranslation(["settings"])
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
  } = useSessionManagement({ setSnackbar, tabActive: isActive, openStepUpFor })

  const sessionsErrorMessage = useMemo(() => {
    if (!sessionsIsError) return null
    const err = sessionsError as {
      response?: { data?: { detail?: string | string[] } }
    }
    if (err?.response?.data?.detail) return String(err.response.data.detail)
    return sessionsError instanceof Error ? sessionsError.message : t("settings:sessions.error")
  }, [sessionsIsError, sessionsError, t])

  return (
    <div className="flex w-full flex-col gap-5 sm:gap-6 xl:max-w-(--layout-max-page) 2xl:max-w-(--layout-max-wide) animate-fade-in delay-200">
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
