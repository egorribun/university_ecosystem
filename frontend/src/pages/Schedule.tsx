import { useCallback, useState, useMemo, useRef } from "react"
import { useTranslation } from "react-i18next"
import { AnimatePresence, m } from "framer-motion"
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
import { ScheduleSettingsPanel } from "@/components/schedule/ScheduleSettingsPanel"
import { ConfirmDialog } from "@/components/ui/ConfirmDialog"
import { Alert, Snackbar } from "@/components/settings"
import { SEO } from "@/components/ui/SEO"
import { FeatureErrorBoundary } from "@/components/error/FeatureErrorBoundary"
import { useScheduleKeyboardNav } from "@/hooks/useScheduleKeyboardNav"
import { useScrollToElement } from "@/hooks/useScrollToElement"
import { useScheduleURLSync } from "@/hooks/useScheduleURLSync"
import {
  useWeekOffset,
  useScheduleDisplayPreferences,
  useScheduleUIActions,
} from "@/stores/scheduleUIStore"
import { useLessonNotesMap } from "@/hooks/useLessonNotes"
import api from "@/api/client"

function ScheduleContent() {
  const { t } = useTranslation(["schedule", "common"])
  const isOnline = useOnlineStatus()
  const isMobile = useMediaQuery(`(max-width: ${breakpoints.desktop})`)
  // Wave 112 SW3b — keep URL `?w=` in sync with Zustand `weekOffset` so
  // refresh/share both preserve the selected week (mirror of Events/News).
  useScheduleURLSync()
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

  const {
    snackbarMessage,
    snackbarSeverity,
    hideSnackbar,
    showSnackbar,
    openDialog,
    selectedLesson,
    activeDialog,
  } = useSchedulePage()

  /* ── Confirm dialog + export state ─────────────────────── */
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const gridRef = useRef<HTMLDivElement>(null)

  /* ── Past lessons filter ──────────────────────────────── */
  // PERF-70-04: use primitive minutesNow instead of Date object to stabilize dependency
  const minutesNow = nowTick.getHours() * 60 + nowTick.getMinutes()
  const displaySchedule = useMemo(() => {
    if (showPastLessons) {
      return schedule
    } else {
      const todayDay = hasToday ? weekdayBackend[todayIdx] : null
      return schedule.filter((lesson) => {
        if (lesson.weekday !== todayDay) {
          return true
        } else {
          const endStr = lesson.end_time
          if (!endStr) return true
          const [hours, minutes] = endStr.split(":").map(Number)
          if (hours === undefined || minutes === undefined || isNaN(hours) || isNaN(minutes)) {
            return true
          }
          return hours * 60 + minutes > minutesNow
        }
      })
    }
  }, [schedule, showPastLessons, hasToday, todayIdx, weekdayBackend, minutesNow])

  /* ── Keyboard navigation ──────────────────────────────── */
  const [shortcutsOpen, setShortcutsOpen] = useState(false)

  // PERF-70-05: compute rowCount inline — avoids duplicate buildTable() call (also in DesktopTable)
  const rowCount = useMemo(() => {
    const counts = weekdayBackend.map(
      (day) => displaySchedule.filter((l) => l.weekday === day).length
    )
    return Math.max(...counts, 0)
  }, [displaySchedule, weekdayBackend])

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
    rowCount,
    todayColIdx: todayIdx,
    enabled:
      !isMobile &&
      !shortcutsOpen &&
      activeDialog === null &&
      !settingsOpen &&
      pendingDeleteId === null,
    onEdit: handleKbEdit,
    onDelete: handleKbDelete,
    onToggleShortcuts: handleToggleShortcuts,
  })

  const getLessonTypeLabel = useCallback(
    (val?: string | null) => lessonTypeLabels.get(val ?? "") ?? val ?? "",
    [lessonTypeLabels]
  )
  const prefersReduced = useMediaQuery("(prefers-reduced-motion: reduce)")

  const confirmDeleteLesson = useCallback(async () => {
    const id = pendingDeleteId!
    setPendingDeleteId(null)

    const backup = [...rawSchedule]
    applyScheduleUpdate((prev) => prev.filter((l) => l.id !== id))
    if (!isOnline) {
      showSnackbar(t("schedule:snackbar.deleteError"), "error")
      applyScheduleUpdate(() => backup)
      return
    } else {
      try {
        await api.delete(`/schedule/${id}`)
        showSnackbar(t("schedule:snackbar.deleted"))
        refresh()
      } catch {
        showSnackbar(t("schedule:snackbar.deleteError"), "error")
        applyScheduleUpdate(() => backup)
      }
    }
  }, [pendingDeleteId, rawSchedule, applyScheduleUpdate, isOnline, showSnackbar, t, refresh])

  /* ── "All lessons filtered" detection (FIX-65-05) ──── */
  const allFilteredOut = displaySchedule.length === 0 && schedule.length > 0

  /* ── Scroll to current lesson on initial load (FIX-67-07, FIX-68-06) ── */
  useScrollToElement(!isLoading && currentLesson ? `lesson-card-${currentLesson.id}` : null, {
    behavior: "smooth",
    block: "center",
  })

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
    currentProgress: scheduleData.currentProgress, // FIX-70-05: was missing — glow urgency on desktop
    notesMap,
    todayComplete,
  }

  return (
    <PageLayout variant="full">
      <SEO title={t("schedule:title.default")} />
      <div className="schedule-theme relative w-full py-6 sm:py-8 md:py-10 px-4 sm:px-6 md:px-10 lg:px-14 text-text-primary">
        {/* ── Page-level aurora backdrop — lower orbs only (Wave 71b: orbs 1+2 moved into hero card) ── */}
        <div
          className="pointer-events-none absolute inset-0 -z-1 overflow-hidden"
          aria-hidden="true"
        >
          <div className="sched-orb-3 absolute bottom-20 left-1/4 h-32 w-32 rounded-full opacity-30 blur-[70px] sm:h-48 sm:w-48 lg:h-64 lg:w-64" />
          <div className="sched-orb-4 absolute right-1/3 top-1/2 h-28 w-28 rounded-full opacity-25 blur-[60px] sm:h-40 sm:w-40 lg:h-56 lg:w-56" />
        </div>

        <ScheduleHeader
          {...scheduleData}
          nowTick={nowTick}
          onOpenSettings={() => setSettingsOpen(true)}
        />

        <div className="flex gap-4 lg:gap-6">
          {/* ── Main content ──────────────────────────────── */}
          <section
            ref={gridRef}
            aria-label={t("schedule:title.default")}
            className="min-w-0 flex-1"
          >
            <SkeletonMorph loaded={!isLoading} skeleton={<ScheduleSkeleton />}>
              <FadeSection delay="var(--motion-duration-base)">
                {/* ── All lessons filtered out — show reset action (FIX-65-05) ── */}
                {allFilteredOut && (
                  <div className="mb-4 flex items-center gap-3 rounded-xl border border-amber-500/(--opacity-dim) bg-amber-500/(--opacity-subtle) px-4 py-3 text-sm text-text-secondary">
                    <span>{t("schedule:empty.allFiltered")}</span>
                    <button
                      type="button"
                      onClick={resetPreferences}
                      className="ml-auto shrink-0 rounded-lg bg-brand px-3 py-1 text-xs font-semibold text-[var(--sched-on-accent)] transition-colors hover:bg-brand-hover focus-visible:ring-2 focus-visible:ring-brand"
                    >
                      {t("schedule:empty.resetFilters")}
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
                      className="ml-auto shrink-0 rounded-lg bg-brand px-3 py-1 text-xs font-semibold text-[var(--sched-on-accent)] transition-colors hover:bg-brand-hover focus-visible:ring-2 focus-visible:ring-brand"
                    >
                      {t("schedule:error.retry")}
                    </button>
                  </div>
                )}
                {/* PERF-70-01: replaced AnimatePresence key-swap with animate prop —
                   avoids full unmount/remount of all cards on week navigation.
                   PERF-70-02: removed filter:blur — GPU-expensive, imperceptible at 200ms. */}
                {/* FEAT-71-02: animated view transition between desktop ↔ mobile */}
                <AnimatePresence mode="wait" initial={false}>
                  <m.div
                    key={isMobile ? "mobile" : "desktop"}
                    initial={prefersReduced ? false : { opacity: 0, scale: 0.98 }}
                    animate={{ opacity: 1, scale: 1 }}
                    exit={prefersReduced ? { opacity: 0 } : { opacity: 0, scale: 0.98 }}
                    transition={
                      prefersReduced
                        ? { duration: 0 }
                        : { duration: 0.2, ease: [0.25, 0.1, 0.25, 1] }
                    }
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
                  </m.div>
                </AnimatePresence>
              </FadeSection>
            </SkeletonMorph>
          </section>

          {/* ── Mini-calendar sidebar (desktop only) ──────── */}
          {/* RESP-71-02: adaptive width — w-48 on tablet, w-56 on large screens */}
          {!isMobile && (
            <aside className="hidden w-48 shrink-0 md:block lg:w-56">
              <FadeSection delay="var(--motion-duration-slow)">
                <ScheduleMiniCalendar
                  className="sticky top-20"
                  lessonDays={lessonDays}
                  isLoading={isLoading}
                />
              </FadeSection>
            </aside>
          )}
        </div>

        <ScheduleDialogs {...scheduleData} getLessonTypeLabel={getLessonTypeLabel} />
        <ScheduleShortcutsOverlay open={shortcutsOpen} onClose={() => setShortcutsOpen(false)} />

        {/* ── Settings panel ─────────────────────────────── */}
        <ScheduleSettingsPanel
          open={settingsOpen}
          onClose={() => setSettingsOpen(false)}
          weekdayLabels={weekdayLabels}
          currentParity={scheduleData.currentParity}
          setCurrentParity={scheduleData.setCurrentParity}
          gridRef={gridRef}
        />

        {/* ── Confirm deletion dialog ────────────────────── */}
        <ConfirmDialog
          open={pendingDeleteId !== null}
          title={t("schedule:confirm.deleteTitle")}
          message={t("schedule:confirm.deleteMessage")}
          confirmText={t("schedule:confirm.deleteConfirm")}
          cancelText={t("common:buttons.cancel")}
          variant="danger"
          onConfirm={confirmDeleteLesson}
          onCancel={() => setPendingDeleteId(null)}
        />

        {/* ── Week/parity announcement (a11y) ── */}
        <div className="sr-only" role="status" aria-live="polite">
          {weekOffset === 0
            ? t("schedule:toolbar.thisWeek")
            : t("schedule:toolbar.weekOffset", {
                offset: weekOffset > 0 ? `+${weekOffset}` : String(weekOffset),
              })}
          .{" "}
          {t(`schedule:parity.${scheduleData.currentParity}`, {
            defaultValue: scheduleData.currentParity,
          })}
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
