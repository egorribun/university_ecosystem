import { useCallback, useState, useMemo } from "react"
import { useTranslation } from "react-i18next"
import { PageLayout } from "@/components/layout/PageLayout"
import useMediaQuery from "@/hooks/useMediaQuery"
import { breakpoints } from "@/theme/tokens"
import { useOnlineStatus } from "@/hooks/useOnlineStatus"
import { useScheduleData } from "@/hooks/useScheduleData"
import { ScheduleSkeleton } from "@/components/schedule/ScheduleSkeleton"
import FadeSection from "@/components/motion/FadeSection"
import { SchedulePageProvider, useSchedulePage } from "@/contexts/SchedulePageContext"
import { ScheduleHeader } from "@/components/schedule/ScheduleHeader"
import { ScheduleDesktopTable } from "@/components/schedule/ScheduleDesktopTable"
import { ScheduleMobileView } from "@/components/schedule/ScheduleMobileView"
import { ScheduleDialogs } from "@/components/schedule/ScheduleDialogs"
import { ScheduleShortcutsOverlay } from "@/components/schedule/ScheduleShortcutsOverlay"
import { ScheduleMiniCalendar } from "@/components/schedule/ScheduleMiniCalendar"
import { LessonSlideOver } from "@/components/schedule/LessonSlideOver"
import { Alert, Snackbar } from "@/components/settings"
import { SEO } from "@/components/ui/SEO"
import { FeatureErrorBoundary } from "@/components/error/FeatureErrorBoundary"
import { useScheduleKeyboardNav } from "@/hooks/useScheduleKeyboardNav"
import {
  useViewMode,
  useScheduleDisplayPreferences,
} from "@/stores/scheduleUIStore"
import { buildTable } from "@/components/schedule/scheduleUtils"
import api from "@/api/client"

function ScheduleContent() {
  const { t } = useTranslation(["schedule", "common"])
  const isOnline = useOnlineStatus()
  const isMobile = useMediaQuery(`(max-width: ${breakpoints.ultrawide})`)
  const viewMode = useViewMode()
  const { showPastLessons } = useScheduleDisplayPreferences()

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
    currentLesson,
    selectedGroup,
  } = scheduleData

  const { snackbarMessage, hideSnackbar, showSnackbar, openDialog, closeDialog, selectedLesson, activeDialog } =
    useSchedulePage()

  /* ── Past lessons filter ──────────────────────────────── */
  const displaySchedule = useMemo(() => {
    if (showPastLessons) return schedule
    // Only filter on today's column
    const now = new Date()
    const minutesNow = now.getHours() * 60 + now.getMinutes()
    const todayDay = hasToday ? weekdayBackend[todayIdx] : null
    return schedule.filter((l) => {
      if (l.weekday !== todayDay) return true
      const endStr = l.end_time
      if (!endStr) return true
      const [h, m] = endStr.split(":").map(Number)
      if (isNaN(h) || isNaN(m)) return true
      return h * 60 + m > minutesNow
    })
  }, [schedule, showPastLessons, hasToday, todayIdx, weekdayBackend])

  /* ── Keyboard navigation ──────────────────────────────── */
  const [shortcutsOpen, setShortcutsOpen] = useState(false)

  const tableRows = useMemo(
    () => buildTable(displaySchedule, weekdayBackend),
    [displaySchedule, weekdayBackend],
  )

  const handleKbOpen = useCallback(() => {
    if (selectedLesson) openDialog("details", selectedLesson)
  }, [selectedLesson, openDialog])

  const handleKbEdit = useCallback(() => {
    if (selectedLesson && (user?.role === "admin" || user?.role === "teacher")) {
      openDialog("edit", selectedLesson)
    }
  }, [selectedLesson, user?.role, openDialog])

  const handleToggleShortcuts = useCallback(() => setShortcutsOpen((v) => !v), [])

  useScheduleKeyboardNav({
    colCount: weekdayBackend.length,
    rowCount: tableRows.length,
    todayColIdx: todayIdx,
    enabled: !isMobile && !shortcutsOpen,
    onOpen: handleKbOpen,
    onEdit: handleKbEdit,
    onToggleShortcuts: handleToggleShortcuts,
  })

  /* ── iCalendar export ─────────────────────────────────── */
  const handleExportIcs = useCallback(async () => {
    if (!selectedGroup) return
    try {
      const res = await api.get(`/schedule/ics`, {
        params: { group: selectedGroup },
        responseType: "blob",
      })
      const url = URL.createObjectURL(res.data as Blob)
      const a = document.createElement("a")
      a.href = url
      a.download = "schedule.ics"
      a.click()
      URL.revokeObjectURL(url)
    } catch {
      showSnackbar(t("schedule:snackbar.deleteError"))
    }
  }, [selectedGroup, showSnackbar, t])

  const getLessonTypeLabel = useCallback(
    (val?: string | null) => lessonTypeLabels.get(val ?? "") ?? val ?? "",
    [lessonTypeLabels],
  )

  const handleDeleteLesson = useCallback(
    async (id: string) => {
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
    [rawSchedule, applyScheduleUpdate, isOnline, showSnackbar, t, refresh],
  )

  if (isLoading) {
    return (
      <PageLayout variant="wide">
        <div className="schedule-theme">
          <ScheduleSkeleton />
        </div>
      </PageLayout>
    )
  }

  /* ── Determine which view to render ───────────────────── */
  const useMobileLayout = isMobile || viewMode === "day"

  return (
    <PageLayout variant="wide">
      <SEO title={t("schedule:title.default")} />
      <div className="schedule-theme w-full text-text-primary">
        <ScheduleHeader
          {...scheduleData}
          onExportIcs={selectedGroup ? handleExportIcs : undefined}
        />

        <div className="flex gap-6 max-w-(--layout-max-ultrawide)">
          {/* ── Main content ──────────────────────────────── */}
          <section aria-label={t("schedule:title.default")} className="min-w-0 flex-1">
            <FadeSection delay="var(--motion-duration-base)">
              {useMobileLayout ? (
                <ScheduleMobileView
                  schedule={displaySchedule}
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
                  currentLesson={currentLesson}
                />
              ) : (
                <ScheduleDesktopTable
                  schedule={displaySchedule}
                  weekdayBackend={weekdayBackend}
                  weekdayLabels={weekdayLabels}
                  hasToday={hasToday}
                  todayIdx={todayIdx}
                  conflictedIds={conflictedIds}
                  user={user}
                  rawSchedule={rawSchedule}
                  refresh={refresh}
                  isOnline={isOnline}
                  lessonTypeLabels={lessonTypeLabels}
                  getLessonTypeColor={getLessonTypeColor}
                  onDeleteLesson={handleDeleteLesson}
                  currentLesson={currentLesson}
                />
              )}
            </FadeSection>
          </section>

          {/* ── Mini-calendar sidebar (desktop only) ──────── */}
          {!isMobile && (
            <aside className="hidden w-56 shrink-0 lg:block">
              <FadeSection delay="var(--motion-duration-slow)">
                <ScheduleMiniCalendar className="sticky top-20" />
              </FadeSection>
            </aside>
          )}
        </div>

        {/* ── Slide-over panel (desktop) / Dialogs (mobile) ── */}
        {!isMobile && selectedLesson && activeDialog === "details" ? (
          <LessonSlideOver
            lesson={selectedLesson}
            open={activeDialog === "details"}
            onClose={closeDialog}
            onEdit={() => openDialog("edit", selectedLesson)}
            onDelete={() => handleDeleteLesson(selectedLesson.id)}
            canEdit={user?.role === "admin" || user?.role === "teacher"}
            getLessonTypeColor={getLessonTypeColor}
            getLessonTypeLabel={getLessonTypeLabel}
          />
        ) : null}
        <ScheduleDialogs {...scheduleData} getLessonTypeLabel={getLessonTypeLabel} />
        <ScheduleShortcutsOverlay
          open={shortcutsOpen}
          onClose={() => setShortcutsOpen(false)}
        />

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
      <FeatureErrorBoundary featureName="schedule">
        <ScheduleContent />
      </FeatureErrorBoundary>
    </SchedulePageProvider>
  )
}
