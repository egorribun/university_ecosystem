import { useCallback, useState, useMemo, useRef, useEffect } from "react"
import { useTranslation } from "react-i18next"
import { AnimatePresence, motion } from "framer-motion"
import { PageLayout } from "@/components/layout/PageLayout"
import useMediaQuery from "@/hooks/useMediaQuery"
import { breakpoints } from "@/theme/tokens"
import { useOnlineStatus } from "@/hooks/useOnlineStatus"
import { useScheduleData } from "@/hooks/useScheduleData"
import { ScheduleSkeleton } from "@/components/schedule/ScheduleSkeleton"
import { SkeletonMorph } from "@/components/ui/SkeletonMorph"
import FadeSection from "@/components/motion/FadeSection"
import { SchedulePageProvider, useSchedulePage } from "@/contexts/SchedulePageContext"
import { ScheduleHeader } from "@/components/schedule/ScheduleHeader"
import { ScheduleDesktopTable } from "@/components/schedule/ScheduleDesktopTable"
import { ScheduleMobileView } from "@/components/schedule/ScheduleMobileView"
import { ScheduleDialogs } from "@/components/schedule/ScheduleDialogs"
import { ScheduleShortcutsOverlay } from "@/components/schedule/ScheduleShortcutsOverlay"
import { ScheduleMiniCalendar } from "@/components/schedule/ScheduleMiniCalendar"
import { LessonSlideOver } from "@/components/schedule/LessonSlideOver"
import { LessonBottomSheet } from "@/components/schedule/LessonBottomSheet"
import { ScheduleSettingsPanel } from "@/components/schedule/ScheduleSettingsPanel"
import { ConfirmDialog } from "@/components/ui/ConfirmDialog"
import { Alert, Snackbar } from "@/components/settings"
import { SEO } from "@/components/ui/SEO"
import { FeatureErrorBoundary } from "@/components/error/FeatureErrorBoundary"
import { useScheduleKeyboardNav } from "@/hooks/useScheduleKeyboardNav"
import { useScrollToElement } from "@/hooks/useScrollToElement"
import {
  useWeekOffset,
  useScheduleDisplayPreferences,
  useScheduleUIActions,
} from "@/stores/scheduleUIStore"
import { buildTable } from "@/components/schedule/scheduleUtils"
import { useLessonNotesMap } from "@/hooks/useLessonNotes"
import api from "@/api/client"

function ScheduleContent() {
  const { t } = useTranslation(["schedule", "common"])
  const isOnline = useOnlineStatus()
  const isMobile = useMediaQuery(`(max-width: ${breakpoints.desktop})`)
  const weekOffset = useWeekOffset()
  const { showPastLessons } = useScheduleDisplayPreferences()
  const { resetPreferences } = useScheduleUIActions()

  const scheduleData = useScheduleData()
  const {
    isLoading,
    error: scheduleError,
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
    getDayLabel,
    getLessonTypeColor,
    applyScheduleUpdate,
    currentLesson,
    nextLesson,
    nowTick,
    lessonDays,
    lessonTypeLabels,
    todayLessons,
  } = scheduleData

  /* ── Day complete flag for confetti (FIX-68-23) ── */
  const todayComplete = hasToday && !currentLesson && !nextLesson && todayLessons.length > 0

  /* ── Lesson notes map for card indicators (FIX-67-02) ── */
  const lessonIds = useMemo(() => schedule.map((l) => l.id), [schedule])
  const notesMap = useLessonNotesMap(lessonIds)

  const { snackbarMessage, snackbarSeverity, hideSnackbar, showSnackbar, openDialog, closeDialog, selectedLesson, activeDialog } =
    useSchedulePage()

  /* ── Confirm dialog + export state ─────────────────────── */
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const gridRef = useRef<HTMLDivElement>(null)

  /* ── Week navigation direction for slide animation (FIX-68-12) ── */
  const prevWeekOffsetRef = useRef(weekOffset)
  const slideDirection = weekOffset > prevWeekOffsetRef.current ? 1 : weekOffset < prevWeekOffsetRef.current ? -1 : 0
  useEffect(() => { prevWeekOffsetRef.current = weekOffset }, [weekOffset])

  /* ── Past lessons filter ──────────────────────────────── */
  const displaySchedule = useMemo(() => {
    if (showPastLessons) return schedule
    // Only filter on today's column — use nowTick from useScheduleData ticker
    const minutesNow = nowTick.getHours() * 60 + nowTick.getMinutes()
    const todayDay = hasToday ? weekdayBackend[todayIdx] : null
    return schedule.filter((l) => {
      if (l.weekday !== todayDay) return true
      const endStr = l.end_time
      if (!endStr) return true
      const [h, m] = endStr.split(":").map(Number)
      if (isNaN(h) || isNaN(m)) return true
      return h * 60 + m > minutesNow
    })
  }, [schedule, showPastLessons, hasToday, todayIdx, weekdayBackend, nowTick])

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

  /* ── Deletion with confirmation ────────────────────────── */
  const requestDeleteLesson = useCallback((id: string) => {
    setPendingDeleteId(id)
  }, [])

  const handleKbDelete = useCallback(() => {
    if (selectedLesson && (user?.role === "admin" || user?.role === "teacher")) {
      requestDeleteLesson(selectedLesson.id)
    }
  }, [selectedLesson, user?.role, requestDeleteLesson])

  useScheduleKeyboardNav({
    colCount: weekdayBackend.length,
    rowCount: tableRows.length,
    todayColIdx: todayIdx,
    enabled: !isMobile && !shortcutsOpen && activeDialog === null && !settingsOpen && pendingDeleteId === null,
    onOpen: handleKbOpen,
    onEdit: handleKbEdit,
    onDelete: handleKbDelete,
    onToggleShortcuts: handleToggleShortcuts,
  })



  const getLessonTypeLabel = useCallback(
    (val?: string | null) => lessonTypeLabels.get(val ?? "") ?? val ?? "",
    [lessonTypeLabels],
  )

  const confirmDeleteLesson = useCallback(async () => {
    const id = pendingDeleteId
    if (!id) return
    setPendingDeleteId(null)

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
      showSnackbar(t("schedule:snackbar.deleteError"), "error")
      applyScheduleUpdate(() => backup)
    }
  }, [pendingDeleteId, rawSchedule, applyScheduleUpdate, isOnline, showSnackbar, t, refresh])

  /* ── "All lessons filtered" detection (FIX-65-05) ──── */
  const allFilteredOut = displaySchedule.length === 0 && schedule.length > 0

  /* ── Scroll to current lesson on initial load (FIX-67-07, FIX-68-06) ── */
  useScrollToElement(
    !isLoading && currentLesson ? `lesson-card-${currentLesson.id}` : null,
    { behavior: "smooth", block: "center" },
  )

  const sharedViewProps = {
    schedule: displaySchedule,
    weekdayBackend,
    weekdayLabels,
    hasToday,
    todayIdx,
    rawSchedule,
    refresh,
    user,
    conflictedIds,
    isOnline,
    onDeleteLesson: requestDeleteLesson,
    getLessonTypeColor,
    currentLesson,
    notesMap,
    todayComplete,
  }

  return (
    <PageLayout variant="full">
      <SEO title={t("schedule:title.default")} />
      <div className="schedule-theme relative w-full px-4 sm:px-6 md:px-8 lg:px-10 py-6 text-text-primary xl:mx-auto xl:max-w-[96rem]">
        {/* ── Page-level aurora backdrop (DESIGN-63-02) ───── */}
        <div className="pointer-events-none absolute inset-0 -z-1 overflow-hidden" aria-hidden="true">
          <div className="sched-orb-1 absolute -left-32 top-40 h-48 w-48 rounded-full opacity-50 blur-[80px] sm:h-64 sm:w-64 lg:h-96 lg:w-96" />
          <div className="sched-orb-2 absolute -right-24 top-80 h-40 w-40 rounded-full opacity-40 blur-[60px] sm:h-56 sm:w-56 lg:h-80 lg:w-80" />
          <div className="sched-orb-3 absolute bottom-20 left-1/4 h-32 w-32 rounded-full opacity-30 blur-[70px] sm:h-48 sm:w-48 lg:h-64 lg:w-64" />
        </div>

        <ScheduleHeader
          {...scheduleData}
          onOpenSettings={() => setSettingsOpen(true)}
          gridRef={gridRef}
        />

        <div className="flex gap-4 lg:gap-6">
          {/* ── Main content ──────────────────────────────── */}
          <section ref={gridRef} aria-label={t("schedule:title.default")} className="min-w-0 flex-1">
            <SkeletonMorph loaded={!isLoading} skeleton={<ScheduleSkeleton />}>
              <FadeSection delay="var(--motion-duration-base)">
                {/* ── All lessons filtered out — show reset action (FIX-65-05) ── */}
                {allFilteredOut && (
                  <div className="mb-4 flex items-center gap-3 rounded-xl border border-amber-500/(--opacity-dim) bg-amber-500/(--opacity-subtle) px-4 py-3 text-sm text-text-secondary">
                    <span>{t("schedule:empty.allFiltered", { defaultValue: "All lessons are hidden by current filters" })}</span>
                    <button
                      type="button"
                      onClick={resetPreferences}
                      className="ml-auto shrink-0 rounded-lg bg-brand px-3 py-1 text-xs font-semibold text-white transition-colors hover:bg-brand-hover focus-visible:ring-2 focus-visible:ring-brand"
                    >
                      {t("schedule:empty.resetFilters", { defaultValue: "Reset filters" })}
                    </button>
                  </div>
                )}
                {/* Error banner (FIX-67-06) */}
                {scheduleError && !isLoading && (
                  <div className="mb-4 flex items-center gap-3 rounded-xl border border-error/(--opacity-dim) bg-error/(--opacity-subtle) px-4 py-3 text-sm text-text-secondary">
                    <span>{t("schedule:error.loadFailed")}</span>
                    <button
                      type="button"
                      onClick={refresh}
                      className="ml-auto shrink-0 rounded-lg bg-brand px-3 py-1 text-xs font-semibold text-white transition-colors hover:bg-brand-hover focus-visible:ring-2 focus-visible:ring-brand"
                    >
                      {t("schedule:error.retry")}
                    </button>
                  </div>
                )}
                {/* Week slide animation: directional crossfade (FIX-68-12) */}
                <AnimatePresence mode="wait" initial={false}>
                  <motion.div
                    key={weekOffset}
                    initial={{ opacity: 0, x: slideDirection * 30, filter: "blur(2px)" }}
                    animate={{ opacity: 1, x: 0, filter: "blur(0px)" }}
                    exit={{ opacity: 0, x: slideDirection * -30, filter: "blur(2px)" }}
                    transition={{ duration: 0.2, ease: [0.25, 0.1, 0.25, 1] }}
                  >
                    {isMobile ? (
                      <ScheduleMobileView
                        {...sharedViewProps}
                        weekdayShort={weekdayShort}
                        getDayLabel={getDayLabel}
                        getLessonTypeLabel={getLessonTypeLabel}
                      />
                    ) : (
                      <ScheduleDesktopTable
                        {...sharedViewProps}
                        getLessonTypeLabel={getLessonTypeLabel}
                      />
                    )}
                  </motion.div>
                </AnimatePresence>
              </FadeSection>
            </SkeletonMorph>
          </section>

          {/* ── Mini-calendar sidebar (desktop only) ──────── */}
          {!isMobile && (
            <aside className="hidden w-56 shrink-0 lg:block">
              <FadeSection delay="var(--motion-duration-slow)">
                <ScheduleMiniCalendar className="sticky top-20" lessonDays={lessonDays} isLoading={isLoading} />
              </FadeSection>
            </aside>
          )}
        </div>

        {/* ── Lesson detail: slide-over (desktop) / bottom sheet (mobile) ── */}
        {!isMobile ? (
          <LessonSlideOver
            lesson={selectedLesson}
            open={activeDialog === "details" && selectedLesson !== null}
            onClose={closeDialog}
            onEdit={() => selectedLesson && openDialog("edit", selectedLesson)}
            onDelete={() => selectedLesson && requestDeleteLesson(selectedLesson.id)}
            canEdit={user?.role === "admin" || user?.role === "teacher"}
            getLessonTypeColor={getLessonTypeColor}
            getLessonTypeLabel={getLessonTypeLabel}
          />
        ) : (
          <LessonBottomSheet
            lesson={selectedLesson}
            open={activeDialog === "details" && selectedLesson !== null}
            onClose={closeDialog}
            onEdit={() => selectedLesson && openDialog("edit", selectedLesson)}
            onDelete={() => selectedLesson && requestDeleteLesson(selectedLesson.id)}
            canEdit={user?.role === "admin" || user?.role === "teacher"}
            getLessonTypeColor={getLessonTypeColor}
            getLessonTypeLabel={getLessonTypeLabel}
          />
        )}
        <ScheduleDialogs {...scheduleData} getLessonTypeLabel={getLessonTypeLabel} />
        <ScheduleShortcutsOverlay
          open={shortcutsOpen}
          onClose={() => setShortcutsOpen(false)}
        />

        {/* ── Settings panel ─────────────────────────────── */}
        <ScheduleSettingsPanel
          open={settingsOpen}
          onClose={() => setSettingsOpen(false)}
          weekdayLabels={weekdayLabels}
        />

        {/* ── Confirm deletion dialog ────────────────────── */}
        <ConfirmDialog
          open={pendingDeleteId !== null}
          title={t("schedule:confirm.deleteTitle")}
          message={t("schedule:confirm.deleteMessage")}
          confirmText={t("schedule:confirm.deleteConfirm")}
          cancelText={t("common:buttons.cancel", { defaultValue: "Cancel" })}
          variant="danger"
          onConfirm={confirmDeleteLesson}
          onCancel={() => setPendingDeleteId(null)}
        />

        {/* ── Week/parity announcement (a11y) ── */}
        <div className="sr-only" role="status" aria-live="polite">
          {weekOffset === 0
            ? t("schedule:toolbar.thisWeek")
            : t("schedule:toolbar.weekOffset", { offset: weekOffset > 0 ? `+${weekOffset}` : String(weekOffset) })}.{" "}
          {t(`schedule:parity.${scheduleData.currentParity}`, { defaultValue: scheduleData.currentParity })}
        </div>

        <Snackbar
          open={!!snackbarMessage}
          autoHideDuration={4000}
          onClose={hideSnackbar}
          anchorOrigin={{ vertical: "bottom", horizontal: "center" }}
        >
          <Alert severity={snackbarSeverity} onClose={hideSnackbar}>
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
