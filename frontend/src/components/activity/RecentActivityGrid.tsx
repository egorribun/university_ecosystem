import { useCallback, useRef } from "react"
import { useTranslation } from "react-i18next"
import { motion } from "framer-motion"
import { motion as motionTokens } from "@/theme/tokens"
import {
  CalendarCheck as EventAvailableIcon,
  GraduationCap as SchoolIcon,
  Award as EmojiEventsIcon,
} from "lucide-react"
import { useVirtualizer } from "@tanstack/react-virtual"

import CardShell from "@/components/activity/CardShell"
import type {
  AttendanceStats,
  GradeStats,
  ParticipationStats,
} from "@/components/activity/activityTypes"
import type { DetailSection } from "@/components/activity/activityTypes"
import { cn } from "@/utils/cn"

type RecentActivityGridProps = {
  attendance?: AttendanceStats | null
  grades?: GradeStats | null
  participation?: ParticipationStats | null
  loading?: boolean
  hasInitiallyLoaded: boolean
  reduceMotion: boolean
  onDetailClick: (section: DetailSection) => void
  separator: string
  attendanceLessonFallback: string
  attendanceStatusLabel: (status: "present" | "absent" | "late") => string
  formatDate: (date: string) => string
}

/** Visible scroll area height — ~5 rows before the user needs to scroll */
const LIST_HEIGHT = 208
/** Approximate row height used by the virtualizer for initial layout */
const ITEM_ESTIMATE_SIZE = 44

// PERF-27-02: Removed React.memo() — React Compiler "infer" mode handles memoization
export function RecentActivityGrid({
  attendance,
  grades,
  participation,
  loading,
  hasInitiallyLoaded,
  reduceMotion,
  onDetailClick,
  separator,
  attendanceLessonFallback,
  attendanceStatusLabel,
  formatDate,
}: RecentActivityGridProps) {
  const { t } = useTranslation(["activity"])

  // Scroll container refs — one per virtualized list
  const attendanceParentRef = useRef<HTMLDivElement>(null)
  const gradesParentRef = useRef<HTMLDivElement>(null)
  const participationParentRef = useRef<HTMLDivElement>(null)

  const attendanceItems = attendance?.recent ?? []
  const gradesItems = grades?.recent ?? []
  const participationItems = participation?.recent ?? []

  const attendanceVirtualizer = useVirtualizer({
    count: attendanceItems.length,
    getScrollElement: () => attendanceParentRef.current,
    estimateSize: () => ITEM_ESTIMATE_SIZE,
    overscan: 3,
  })

  const gradesVirtualizer = useVirtualizer({
    count: gradesItems.length,
    getScrollElement: () => gradesParentRef.current,
    estimateSize: () => ITEM_ESTIMATE_SIZE,
    overscan: 3,
  })

  const participationVirtualizer = useVirtualizer({
    count: participationItems.length,
    getScrollElement: () => participationParentRef.current,
    estimateSize: () => ITEM_ESTIMATE_SIZE,
    overscan: 3,
  })

  const pickKeyCandidate = useCallback((value: unknown): string | number | undefined => {
    return typeof value === "number" || typeof value === "string" ? value : undefined
  }, [])

  const attendanceItemKey = useCallback(
    (item: AttendanceStats["recent"][number], index: number) =>
      `${item?.date ?? index}-${item?.course ?? index}-${item?.status ?? ""}`,
    []
  )

  const gradeItemKey = useCallback(
    (item: GradeStats["recent"][number], index: number) =>
      `${item?.date ?? index}-${item?.course ?? index}-${item?.score ?? ""}-${item?.max ?? ""}`,
    []
  )

  const participationItemKey = useCallback(
    (item: ParticipationStats["recent"][number], index: number) =>
      `${item?.date ?? index}-${item?.title ?? index}-${item?.role ?? ""}`,
    []
  )

  // Cap stagger delay so first-visible rows animate in quickly
  const staggerDelay = (i: number) =>
    reduceMotion || hasInitiallyLoaded ? 0 : Math.min(i, 4) * motionTokens.staggerFast

  const itemVariants = {
    hidden: { opacity: 0, y: reduceMotion ? 0 : 6 },
    show: { opacity: 1, y: 0, transition: { duration: motionTokens.durationBase } },
  }

  const noDataText = t("activity:common.noData")

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 md:grid-cols-3 md:gap-6">
      {/* Attendance Recent */}
      <CardShell
        onClick={() => onDetailClick("attendance")}
        hasInitiallyLoaded={hasInitiallyLoaded}
        reduceMotion={reduceMotion}
      >
        <div className="flex flex-col">
          <div className="mb-2 flex items-center gap-2">
            <EventAvailableIcon className="text-base text-brand" />
            <h3 className="font-black text-text-primary">
              {t("activity:sections.attendance.recent")}
            </h3>
          </div>
          <div
            ref={attendanceParentRef}
            style={{ height: LIST_HEIGHT, overflowY: "auto" }}
            className="relative"
          >
            {attendanceItems.length === 0 && !loading ? (
              <p className="px-1 py-1 text-sm text-(--text-label)">{noDataText}</p>
            ) : (
              <div style={{ height: attendanceVirtualizer.getTotalSize(), position: "relative" }}>
                {attendanceVirtualizer.getVirtualItems().map((virtualRow) => {
                  const r = attendanceItems[virtualRow.index]
                  const i = virtualRow.index

                  const statusStyles = {
                    present: "bg-success-text ring-success-text/15",
                    late: "bg-warning-text ring-warning-text/15",
                    absent: "bg-error-text ring-error-text/15",
                  }
                  const statusClass =
                    r.status && r.status in statusStyles
                      ? statusStyles[r.status as keyof typeof statusStyles]
                      : "bg-error-text ring-error-text/15"

                  const attendanceRecord = r as Partial<{
                    id?: number | string
                    lesson_id?: number | string
                  }>
                  const itemKey =
                    pickKeyCandidate(attendanceRecord.id) ??
                    pickKeyCandidate(attendanceRecord.lesson_id) ??
                    attendanceItemKey(r, i)

                  return (
                    <motion.div
                      key={itemKey}
                      ref={attendanceVirtualizer.measureElement}
                      data-index={virtualRow.index}
                      variants={itemVariants}
                      initial={hasInitiallyLoaded ? false : "hidden"}
                      animate="show"
                      transition={{ delay: staggerDelay(i) }}
                      style={{ position: "absolute", top: virtualRow.start, left: 0, right: 0 }}
                      className="py-1"
                    >
                      <div className="flex items-center gap-2">
                        <div className={cn("h-2 w-2 rounded-full ring", statusClass)} />
                        <div className="flex min-w-0 flex-1 flex-wrap items-baseline gap-1.5">
                          <span className="font-bold text-text-primary">
                            {r.course || attendanceLessonFallback}
                          </span>
                          <span className="text-sm text-(--text-label)">
                            {attendanceStatusLabel(r.status)}
                          </span>
                        </div>
                      </div>
                      <p className="ml-4 text-xs text-(--text-label)">{formatDate(r.date)}</p>
                    </motion.div>
                  )
                })}
              </div>
            )}
          </div>
        </div>
      </CardShell>

      {/* Grades Recent */}
      <CardShell
        onClick={() => onDetailClick("grades")}
        hasInitiallyLoaded={hasInitiallyLoaded}
        reduceMotion={reduceMotion}
      >
        <div className="flex flex-col">
          <div className="mb-2 flex items-center gap-2">
            <SchoolIcon className="text-base text-(--primary-main)" />
            <h3 className="font-black text-text-primary">{t("activity:sections.grades.recent")}</h3>
          </div>
          <div
            ref={gradesParentRef}
            style={{ height: LIST_HEIGHT, overflowY: "auto" }}
            className="relative"
          >
            {gradesItems.length === 0 && !loading ? (
              <p className="px-1 py-1 text-sm text-(--text-label)">{noDataText}</p>
            ) : (
              <div style={{ height: gradesVirtualizer.getTotalSize(), position: "relative" }}>
                {gradesVirtualizer.getVirtualItems().map((virtualRow) => {
                  const r = gradesItems[virtualRow.index]
                  const i = virtualRow.index
                  const gradeRecord = r as Partial<{ id?: number | string }>
                  const itemKey = pickKeyCandidate(gradeRecord.id) ?? gradeItemKey(r, i)

                  return (
                    <motion.div
                      key={itemKey}
                      ref={gradesVirtualizer.measureElement}
                      data-index={virtualRow.index}
                      variants={itemVariants}
                      initial={hasInitiallyLoaded ? false : "hidden"}
                      animate="show"
                      transition={{ delay: staggerDelay(i) }}
                      style={{ position: "absolute", top: virtualRow.start, left: 0, right: 0 }}
                      className="py-1"
                    >
                      <div className="flex items-center gap-2">
                        <div className="h-2 w-2 rounded-full bg-(--primary-main)/(--opacity-heavy) ring ring-(--primary-main)/15" />
                        <div className="flex min-w-0 flex-1 flex-wrap items-baseline gap-1.5">
                          <span className="font-bold text-text-primary">{r.course}</span>
                          <span className="text-sm text-(--text-label)">
                            {r.score}
                            {r.max ? "/" + r.max : ""}
                          </span>
                        </div>
                      </div>
                      <p className="ml-4 text-xs text-(--text-label)">{formatDate(r.date)}</p>
                    </motion.div>
                  )
                })}
              </div>
            )}
          </div>
        </div>
      </CardShell>

      {/* Participation Recent */}
      <CardShell
        onClick={() => onDetailClick("participation")}
        hasInitiallyLoaded={hasInitiallyLoaded}
        reduceMotion={reduceMotion}
      >
        <div className="flex flex-col">
          <div className="mb-2 flex items-center gap-2">
            <EmojiEventsIcon className="text-base text-(--primary-main)" />
            <h3 className="font-black text-text-primary">
              {t("activity:sections.participation.recent")}
            </h3>
          </div>
          <div
            ref={participationParentRef}
            style={{ height: LIST_HEIGHT, overflowY: "auto" }}
            className="relative"
          >
            {participationItems.length === 0 && !loading ? (
              <p className="px-1 py-1 text-sm text-(--text-label)">{noDataText}</p>
            ) : (
              <div
                style={{ height: participationVirtualizer.getTotalSize(), position: "relative" }}
              >
                {participationVirtualizer.getVirtualItems().map((virtualRow) => {
                  const r = participationItems[virtualRow.index]
                  const i = virtualRow.index
                  const participationRecord = r as Partial<{ id?: number | string }>
                  const itemKey =
                    pickKeyCandidate(participationRecord.id) ?? participationItemKey(r, i)

                  return (
                    <motion.div
                      key={itemKey}
                      ref={participationVirtualizer.measureElement}
                      data-index={virtualRow.index}
                      variants={itemVariants}
                      initial={hasInitiallyLoaded ? false : "hidden"}
                      animate="show"
                      transition={{ delay: staggerDelay(i) }}
                      style={{ position: "absolute", top: virtualRow.start, left: 0, right: 0 }}
                      className="py-1"
                    >
                      <div className="flex items-center gap-2">
                        <div className="h-2 w-2 rounded-full bg-(--warning-text)/(--opacity-heavy) ring ring-(--warning-text)/15" />
                        <div className="flex min-w-0 flex-1 flex-wrap items-baseline gap-1.5">
                          <span className="font-bold text-text-primary">{r.title}</span>
                          <span className="text-sm text-(--text-label)">
                            {[formatDate(r.date), r.role].filter(Boolean).join(separator)}
                          </span>
                        </div>
                      </div>
                    </motion.div>
                  )
                })}
              </div>
            )}
          </div>
        </div>
      </CardShell>
    </div>
  )
}
