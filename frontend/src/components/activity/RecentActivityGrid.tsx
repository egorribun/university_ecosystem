import { useCallback } from "react"
import { useTranslation } from "react-i18next"
import { motion, AnimatePresence } from "framer-motion"
import {
  CalendarCheck as EventAvailableIcon,
  GraduationCap as SchoolIcon,
  Award as EmojiEventsIcon,
} from "lucide-react"

import CardShell from "@/components/activity/CardShell"
import type {
  AttendanceStats,
  GradeStats,
  ParticipationStats,
} from "@/components/activity/activityTypes"
import type { DetailSection } from "@/components/activity/activityTypes"

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

  const pickKeyCandidate = useCallback(
    (value: unknown): string | number | undefined => {
      return typeof value === "number" || typeof value === "string"
        ? value
        : undefined
    },
    []
  )

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

  const listItemVariants = {
    hidden: { opacity: 0, y: reduceMotion ? 0 : 8 },
    show: { opacity: 1, y: 0, transition: { duration: 0.28 } },
  }

  const noDataText = t("activity:states.noData")

  const styleProps = reduceMotion
    ? undefined
    : { willChange: "transform, opacity", transform: "translateZ(0)" }

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
          <div className="space-y-1">
            <AnimatePresence initial={false}>
              {(attendance?.recent ?? []).slice(0, 6).map((r, i) => {
                const color =
                  r.status === "present"
                    ? "var(--success-text)"
                    : r.status === "late"
                      ? "var(--warning-text)"
                      : "var(--error-text)"
                const darkColor =
                  r.status === "present"
                    ? "var(--success-text)"
                    : r.status === "late"
                      ? "var(--warning-text)"
                      : "var(--error-text)"
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
                    variants={listItemVariants}
                    initial={hasInitiallyLoaded ? false : "hidden"}
                    animate="show"
                    exit={{ opacity: 0 }}
                    transition={{
                      delay: reduceMotion || hasInitiallyLoaded ? 0 : i * 0.04,
                    }}
                    className="py-1"
                    style={styleProps}
                  >
                    <div className="flex items-center gap-2">
                      <div
                        className="h-2 w-2 rounded-full dark:hidden"
                        style={{
                          background: color,
                          boxShadow: `0 0 0 3px ${color}18`,
                        }}
                      />
                      <div
                        className="hidden h-2 w-2 rounded-full dark:block"
                        style={{
                          background: darkColor,
                          boxShadow: `0 0 0 3px ${darkColor}18`,
                        }}
                      />
                      <div className="flex min-w-0 flex-1 flex-wrap items-baseline gap-1.5">
                        <span className="font-bold text-text-primary">
                          {r.course || attendanceLessonFallback}
                        </span>
                        <span className="text-sm text-(--text-label)">
                          {attendanceStatusLabel(r.status)}
                        </span>
                      </div>
                    </div>
                    <p className="ml-4 text-xs text-(--text-label)">
                      {formatDate(r.date)}
                    </p>
                  </motion.div>
                )
              })}
            </AnimatePresence>
            {!loading &&
              (!attendance?.recent || attendance.recent.length === 0) && (
                <p className="px-1 py-1 text-sm text-(--text-label)">
                  {noDataText}
                </p>
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
            <h3 className="font-black text-text-primary">
              {t("activity:sections.grades.recent")}
            </h3>
          </div>
          <div className="space-y-1">
            <AnimatePresence initial={false}>
              {(grades?.recent ?? []).slice(0, 6).map((r, i) => {
                const gradeRecord = r as Partial<{ id?: number | string }>
                const itemKey =
                  pickKeyCandidate(gradeRecord.id) ?? gradeItemKey(r, i)
                return (
                  <motion.div
                    key={itemKey}
                    variants={listItemVariants}
                    initial={hasInitiallyLoaded ? false : "hidden"}
                    animate="show"
                    exit={{ opacity: 0 }}
                    transition={{
                      delay: reduceMotion || hasInitiallyLoaded ? 0 : i * 0.04,
                    }}
                    className="py-1"
                    style={styleProps}
                  >
                    <div className="flex items-center gap-2">
                      <div className="h-2 w-2 rounded-full bg-(--primary-main)/(--opacity-heavy) shadow-pulse-primary" />
                      <div className="flex min-w-0 flex-1 flex-wrap items-baseline gap-1.5">
                        <span className="font-bold text-text-primary">
                          {r.course}
                        </span>
                        <span className="text-sm text-(--text-label)">
                          {r.score}
                          {r.max ? "/" + r.max : ""}
                        </span>
                      </div>
                    </div>
                    <p className="ml-4 text-xs text-(--text-label)">
                      {formatDate(r.date)}
                    </p>
                  </motion.div>
                )
              })}
            </AnimatePresence>
            {!loading && (!grades?.recent || grades.recent.length === 0) && (
              <p className="px-1 py-1 text-sm text-(--text-label)">
                {noDataText}
              </p>
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
          <div className="space-y-1">
            <AnimatePresence initial={false}>
              {(participation?.recent ?? []).slice(0, 6).map((r, i) => {
                const participationRecord = r as Partial<{
                  id?: number | string
                }>
                const itemKey =
                  pickKeyCandidate(participationRecord.id) ??
                  participationItemKey(r, i)
                return (
                  <motion.div
                    key={itemKey}
                    variants={listItemVariants}
                    initial={hasInitiallyLoaded ? false : "hidden"}
                    animate="show"
                    exit={{ opacity: 0 }}
                    transition={{
                      delay: reduceMotion || hasInitiallyLoaded ? 0 : i * 0.04,
                    }}
                    className="py-1"
                    style={styleProps}
                  >
                    <div className="flex items-center gap-2">
                      <div className="h-2 w-2 rounded-full bg-(--warning-text)/(--opacity-heavy) shadow-pulse-warning" />
                      <div className="flex min-w-0 flex-1 flex-wrap items-baseline gap-1.5">
                        <span className="font-bold text-text-primary">
                          {r.title}
                        </span>
                        <span className="text-sm text-(--text-label)">
                          {[formatDate(r.date), r.role]
                            .filter(Boolean)
                            .join(separator)}
                        </span>
                      </div>
                    </div>
                  </motion.div>
                )
              })}
            </AnimatePresence>
            {!loading &&
              (!participation?.recent || participation.recent.length === 0) && (
                <p className="px-1 py-1 text-sm text-(--text-label)">
                  {noDataText}
                </p>
              )}
          </div>
        </div>
      </CardShell>
    </div>
  )
}
