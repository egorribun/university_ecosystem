import { useCallback } from "react"
import { useTranslation } from "react-i18next"
import { PageLayout } from "@/components/PageLayout"
import useMediaQuery from "@/hooks/useMediaQuery"
import { breakpoints } from "@/theme/tokens"
import { useOnlineStatus } from "@/hooks/useOnlineStatus"
import { useScheduleData } from "@/hooks/useScheduleData"
import { ScheduleSkeleton } from "@/components/schedule/ScheduleSkeleton"
import FadeSection from "@/components/FadeSection"
import { SchedulePageProvider, useSchedulePage } from "@/contexts/SchedulePageContext"
import { ScheduleHeader } from "@/components/schedule/ScheduleHeader"
import { ScheduleDesktopTable } from "@/components/schedule/ScheduleDesktopTable"
import { ScheduleMobileView } from "@/components/schedule/ScheduleMobileView"
import { ScheduleDialogs } from "@/components/schedule/ScheduleDialogs"
import { Alert, Snackbar } from "@/components/settings"
import api from "@/api/client"

function ScheduleContent() {
  const { t } = useTranslation(["schedule", "common"])
  const isOnline = useOnlineStatus()
  const isMobile = useMediaQuery(`(max-width: ${breakpoints.ultrawide})`)

  const scheduleData = useScheduleData()
  const {
    isLoading,
    schedule,
    weekdayBackend,
    weekdayLabels,
    weekdayShort,
    hasToday,
    todayIdx,
    conflictedIds,
    user,
    rawSchedule,
    refresh,
    lessonTypeLabels,
    getDayLabel,
    getLessonTypeColor,
    applyScheduleUpdate,
  } = scheduleData

  const { snackbarMessage, hideSnackbar, showSnackbar } = useSchedulePage()

  const getLessonTypeLabel = useCallback(
    (val?: string | null) => lessonTypeLabels.get(val ?? "") ?? val ?? "",
    [lessonTypeLabels]
  )

  const handleDeleteLesson = useCallback(
    async (id: string) => {
      // Optimistic delete
      const backup = [...rawSchedule]
      applyScheduleUpdate((prev) => prev.filter((l) => l.id !== id))

      try {
        if (isOnline) {
          await api.delete(`/schedule/${id}`)
          showSnackbar(t("schedule:snackbar.deleted"))
          refresh()
        } else {
          throw new Error("Offline")
        }
      } catch {
        showSnackbar(t("schedule:snackbar.deleteError"))
        applyScheduleUpdate(() => backup)
      }
    },
    [rawSchedule, applyScheduleUpdate, isOnline, showSnackbar, t, refresh]
  )

  if (isLoading) {
    return (
      <PageLayout variant="wide">
        <ScheduleSkeleton />
      </PageLayout>
    )
  }

  return (
    <PageLayout variant="wide">
      <div className="w-full text-text-primary">
        <ScheduleHeader {...scheduleData} />

        <section aria-label={t("schedule:title.default")}>
          <FadeSection
            delay="var(--motion-duration-base)"
            className="max-w-(--layout-max-ultrawide)"
          >
            {isMobile ? (
              <ScheduleMobileView
                schedule={schedule}
                weekdayBackend={weekdayBackend}
                weekdayLabels={weekdayLabels}
                weekdayShort={weekdayShort}
                hasToday={hasToday}
                todayIdx={todayIdx}
                getDayLabel={getDayLabel}
                rawSchedule={rawSchedule}
                refresh={refresh}
                user={user}
                conflictedIds={conflictedIds}
                lessonTypeLabels={lessonTypeLabels}
                isOnline={isOnline}
                onDeleteLesson={handleDeleteLesson}
                getLessonTypeColor={getLessonTypeColor}
              />
            ) : (
              <ScheduleDesktopTable
                schedule={schedule}
                weekdayBackend={weekdayBackend}
                weekdayLabels={weekdayLabels}
                hasToday={hasToday}
                todayIdx={todayIdx}
                conflictedIds={conflictedIds}
                user={user}
                rawSchedule={rawSchedule}
                refresh={refresh}
                isLoading={isLoading}
                isOnline={isOnline}
                lessonTypeLabels={lessonTypeLabels}
                getLessonTypeColor={getLessonTypeColor}
                onDeleteLesson={handleDeleteLesson}
              />
            )}
          </FadeSection>
        </section>

        <ScheduleDialogs {...scheduleData} getLessonTypeLabel={getLessonTypeLabel} />

        <Snackbar
          open={!!snackbarMessage}
          autoHideDuration={4000}
          onClose={hideSnackbar}
          anchorOrigin={{ vertical: "bottom", horizontal: "center" }}
        >
          <Alert severity="success" onClose={hideSnackbar}>
            {snackbarMessage}
          </Alert>
        </Snackbar>
      </div>
    </PageLayout>
  )
}

export default function Schedule() {
  return (
    <SchedulePageProvider>
      <ScheduleContent />
    </SchedulePageProvider>
  )
}
