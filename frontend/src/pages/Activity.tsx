import Layout from "../components/Layout"
import PageFadeIn from "../components/PageFadeIn"
import { useEffect, useState, useCallback, type CSSProperties } from "react"
import { motion, AnimatePresence, useMotionValue, animate, useReducedMotion } from "framer-motion"
import {
  Activity as TimelineIcon,
  CalendarCheck as EventAvailableIcon,
  GraduationCap as SchoolIcon,
  Award as EmojiEventsIcon,
} from "lucide-react"
import { Button, ProgressBar } from "@/components/ui"
import Dialog from "@/components/Dialog"
import { cn } from "@/utils/cn"
import useMediaQuery from "@/hooks/useMediaQuery"
import { breakpoints } from "@/theme/tokens"
import FadeSection from "@/components/FadeSection"
import useActivityData from "@/hooks/useActivityData"
import { EASE_OUT_EXPO } from "@/components/activity/activityTypes"
import type {
  AttendanceStats,
  GradeStats,
  ParticipationStats,
} from "@/components/activity/activityTypes"
import { toNumber } from "@/components/activity/activityParsers"
import AnimatedRing, { useAnimatedNumber } from "@/components/activity/AnimatedRing"
import TrendChip from "@/components/activity/TrendChip"
import CardShell from "@/components/activity/CardShell"

const fadeDelayStyle = (value: string): CSSProperties =>
  ({ "--fade-delay": value }) as CSSProperties

export default function Activity() {
  const {
    t,
    period,
    setPeriod,
    attendance,
    grades,
    participation,
    loading,
    hasInitiallyLoaded,
    detail,
    setDetail,
    detailSection,
    periodOptions,
    separator,
    noDataText,
    attendanceLessonFallback,
    formatDate,
    attendanceStatusLabel,
    labelByPeriod,
  } = useActivityData()

  const reduce = useReducedMotion()
  const isSm = useMediaQuery(`(max-width: ${breakpoints.small})`)
  const isMd = useMediaQuery(`(max-width: ${breakpoints.mobile})`)
  const isXl = useMediaQuery(`(min-width: ${breakpoints.desktop})`)
  const ringSize = isSm ? 68 : isMd ? 84 : isXl ? 104 : 96

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
  const pickKeyCandidate = useCallback((value: unknown): string | number | undefined => {
    return typeof value === "number" || typeof value === "string" ? value : undefined
  }, [])

  const headerVariants = {
    hidden: { opacity: 0, y: reduce ? 0 : 10 },
    show: { opacity: 1, y: 0, transition: { duration: 0.35, ease: EASE_OUT_EXPO } },
  }
  const gridVariants = {
    show: { transition: { staggerChildren: reduce ? 0 : 0.06, delayChildren: 0.05 } },
  }
  const listItemVariants = {
    hidden: { opacity: 0, y: reduce ? 0 : 8 },
    show: { opacity: 1, y: 0, transition: { duration: 0.28 } },
  }

  const attendancePctAnimated = useAnimatedNumber(
    Math.max(0, Math.min(100, attendance?.percent ?? 0)),
    0.9,
    0
  )
  const gradeAverage = toNumber(grades?.average)
  const gradeAnimatedValue = grades?.scale === "100" ? Math.round(gradeAverage) : gradeAverage
  const gradesAnimated = useAnimatedNumber(
    gradeAnimatedValue,
    0.9,
    grades?.scale === "gpa" ? 2 : grades?.scale === "5" ? 1 : 0
  )
  const partEventsAnimated = useAnimatedNumber(Math.round(participation?.events ?? 0), 0.9, 0)

  const progressAttendanceMv = useMotionValue(0)
  const [progressAttendance, setProgressAttendance] = useState(0)
  useEffect(() => {
    const target = Math.max(0, Math.min(100, attendance?.percent ?? 0))
    const controls = animate(progressAttendanceMv, target, {
      duration: reduce ? 0 : 0.9,
      ease: EASE_OUT_EXPO,
    })
    const unsubscribe = progressAttendanceMv.on("change", (value: number) =>
      setProgressAttendance(value)
    )
    return () => {
      controls.stop()
      unsubscribe()
    }
  }, [attendance?.percent, reduce, progressAttendanceMv])

  return (
    <Layout>
      <PageFadeIn>
        <div className="w-screen min-h-screen bg-(--bg-page) text-(--text-primary) py-8 sm:py-10">
          <motion.div
            initial="hidden"
            animate="show"
            variants={headerVariants}
            className="px-2 pb-16 sm:px-4"
            style={
              reduce ? undefined : { willChange: "transform, opacity", transform: "translateZ(0)" }
            }
          >
            <header>
              <FadeSection delay="80ms" className="mb-8 flex flex-wrap items-center gap-4 sm:gap-5">
                <div className="flex h-12 w-12 items-center justify-center rounded-full bg-brand-subtle-bg text-brand shadow-glass transition-transform duration-fast hover:scale-105 backdrop-blur-sm">
                  <TimelineIcon className="text-3xl" />
                </div>
                <h1 className="text-page-title font-bold tracking-tight text-(--text-primary)">
                  {t("activity:title")}
                </h1>
              </FadeSection>
            </header>
            <section aria-label={t("activity:title")}>
              <motion.div
                data-fade
                initial={{ opacity: 0, y: reduce ? 0 : 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: reduce ? 0 : 0.35 }}
                style={{
                  ...(reduce
                    ? {}
                    : { willChange: "transform, opacity", transform: "translateZ(0)" }),
                  ...fadeDelayStyle("140ms"),
                }}
                className="mb-6 inline-flex items-center gap-1 rounded-full border border-glass-border bg-(--bg-surface)/(--opacity-medium) p-1 shadow-premium backdrop-blur-xl [-webkit-backdrop-filter:blur(var(--blur-md))] dark:border-glass-border dark:bg-(--bg-page)/(--opacity-medium) dark:shadow-premium"
              >
                {periodOptions.map((option) => (
                  <button
                    key={option.value}
                    onClick={() => setPeriod(option.value)}
                    className={cn(
                      "relative rounded-full border-0 px-4 py-1.5 text-sm font-bold transition-colors duration-rapid",
                      period === option.value
                        ? "text-white"
                        : "bg-transparent text-(--text-primary) hover:bg-brand-subtle-bg hover:text-brand"
                    )}
                  >
                    {period === option.value && (
                      <motion.span
                        layoutId="activity-period-indicator"
                        className="absolute inset-0 rounded-full bg-brand shadow-glass"
                        transition={{ type: "spring", stiffness: 400, damping: 30 }}
                      />
                    )}
                    <span className="relative z-base">{option.label}</span>
                  </button>
                ))}
              </motion.div>

              <motion.div
                variants={gridVariants}
                initial="hidden"
                animate="show"
                className="mb-4 grid grid-cols-1 gap-4 sm:grid-cols-2 md:mb-6 md:grid-cols-3 md:gap-6"
                style={
                  reduce
                    ? undefined
                    : { willChange: "transform, opacity", transform: "translateZ(0)" }
                }
              >
                <CardShell
                  tone="success"
                  onClick={() => setDetail("attendance")}
                  hasInitiallyLoaded={hasInitiallyLoaded}
                  reduceMotion={reduce ?? false}
                >
                  <div className="flex items-center gap-4">
                    <AnimatedRing value={attendance?.percent ?? 0} size={ringSize} tone="success" />
                    <div className="flex min-w-0 flex-1 flex-col gap-1">
                      <p className="text-micro font-semibold uppercase tracking-wider text-(--text-tertiary)">
                        {t("activity:sections.attendance.title")}
                      </p>
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-(--fs-card-stat) font-black tracking-tighter tabular-nums lining-nums">
                          {attendancePctAnimated}%
                        </span>
                        <TrendChip value={attendance?.trend} />
                      </div>
                      <ProgressBar
                        value={progressAttendance}
                        className="h-2 rounded-full"
                        barClassName="bg-(--success-text) rounded-full duration-slow"
                        style={{ transitionProperty: "width" }}
                      />
                      <p className="truncate text-sm text-(--text-muted-subtle)">
                        {t("activity:sections.attendance.summary", {
                          present: attendance?.present ?? 0,
                          total: attendance?.total ?? 0,
                          period: attendance?.periodLabel || labelByPeriod(period),
                        })}
                      </p>
                    </div>
                  </div>
                </CardShell>

                <CardShell
                  tone="info"
                  onClick={() => setDetail("grades")}
                  hasInitiallyLoaded={hasInitiallyLoaded}
                  reduceMotion={reduce ?? false}
                >
                  <div className="flex flex-col gap-1">
                    <p className="text-micro font-semibold uppercase tracking-wider text-(--text-label)">
                      {t("activity:sections.grades.title")}
                    </p>
                    <div className="flex items-center gap-2">
                      <span className="text-(--fs-card-stat) font-black tracking-tighter tabular-nums lining-nums">
                        {grades?.scale === "gpa"
                          ? `GPA ${gradesAnimated}`
                          : grades?.scale === "100"
                            ? `${gradesAnimated}/100`
                            : `${gradesAnimated}/5`}
                      </span>
                      <TrendChip value={grades?.trend} />
                    </div>
                    <p className="text-sm text-text-muted-subtle">
                      {t("activity:sections.grades.averageLabel")}
                    </p>
                  </div>
                </CardShell>

                <CardShell
                  tone="warning"
                  onClick={() => setDetail("participation")}
                  hasInitiallyLoaded={hasInitiallyLoaded}
                  reduceMotion={reduce ?? false}
                >
                  <div className="flex flex-col gap-1">
                    <p className="text-micro font-semibold uppercase tracking-wider text-(--text-label)">
                      {t("activity:sections.participation.title")}
                    </p>
                    <div className="flex items-center gap-2">
                      <span className="text-card-stat font-black tracking-tighter tabular-nums lining-nums text-(--text-primary)">
                        {t("activity:sections.participation.eventsCount", {
                          value: partEventsAnimated,
                          count: participation?.events ?? 0,
                        })}
                      </span>
                      <TrendChip value={participation?.trend} />
                    </div>
                    <p className="text-sm text-text-muted-subtle">
                      {[
                        participation?.hours != null
                          ? t("activity:sections.participation.summaryHours", {
                              count: participation.hours ?? 0,
                            })
                          : null,
                        participation?.groups != null
                          ? t("activity:sections.participation.summaryGroups", {
                              count: participation.groups ?? 0,
                            })
                          : null,
                      ]
                        .filter(Boolean)
                        .join(separator)}
                    </p>
                  </div>
                </CardShell>
              </motion.div>

              <div className="my-4 border-t border-glass-border-subtle md:my-6" />

              <motion.div
                variants={gridVariants}
                initial="hidden"
                animate="show"
                className="grid grid-cols-1 gap-4 sm:grid-cols-2 md:grid-cols-3 md:gap-6"
              >
                <CardShell
                  onClick={() => setDetail("attendance_recent")}
                  hasInitiallyLoaded={hasInitiallyLoaded}
                  reduceMotion={reduce ?? false}
                >
                  <div className="flex flex-col">
                    <div className="mb-2 flex items-center gap-2">
                      <EventAvailableIcon className="text-base text-brand" />
                      <h3 className="font-black text-(--text-primary)">
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
                              transition={{ delay: reduce || hasInitiallyLoaded ? 0 : i * 0.04 }}
                              className="py-1"
                              style={
                                reduce
                                  ? undefined
                                  : { willChange: "transform, opacity", transform: "translateZ(0)" }
                              }
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
                                  <span className="font-bold text-(--text-primary)">
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
                      {!loading && (!attendance?.recent || attendance.recent.length === 0) && (
                        <p className="px-1 py-1 text-sm text-(--text-label)">{noDataText}</p>
                      )}
                    </div>
                  </div>
                </CardShell>

                <CardShell
                  onClick={() => setDetail("grades_recent")}
                  hasInitiallyLoaded={hasInitiallyLoaded}
                  reduceMotion={reduce ?? false}
                >
                  <div className="flex flex-col">
                    <div className="mb-2 flex items-center gap-2">
                      <SchoolIcon className="text-base text-(--primary-main)" />
                      <h3 className="font-black text-(--text-primary)">
                        {t("activity:sections.grades.recent")}
                      </h3>
                    </div>
                    <div className="space-y-1">
                      <AnimatePresence initial={false}>
                        {(grades?.recent ?? []).slice(0, 6).map((r, i) => {
                          const gradeRecord = r as Partial<{ id?: number | string }>
                          const itemKey = pickKeyCandidate(gradeRecord.id) ?? gradeItemKey(r, i)
                          return (
                            <motion.div
                              key={itemKey}
                              variants={listItemVariants}
                              initial={hasInitiallyLoaded ? false : "hidden"}
                              animate="show"
                              exit={{ opacity: 0 }}
                              transition={{ delay: reduce || hasInitiallyLoaded ? 0 : i * 0.04 }}
                              className="py-1"
                              style={
                                reduce
                                  ? undefined
                                  : { willChange: "transform, opacity", transform: "translateZ(0)" }
                              }
                            >
                              <div className="flex items-center gap-2">
                                <div className="h-2 w-2 rounded-full bg-(--primary-main)/(--opacity-heavy) shadow-pulse-primary" />
                                <div className="flex min-w-0 flex-1 flex-wrap items-baseline gap-1.5">
                                  <span className="font-bold text-(--text-primary)">
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
                        <p className="px-1 py-1 text-sm text-(--text-label)">{noDataText}</p>
                      )}
                    </div>
                  </div>
                </CardShell>

                <CardShell
                  onClick={() => setDetail("participation_recent")}
                  hasInitiallyLoaded={hasInitiallyLoaded}
                  reduceMotion={reduce ?? false}
                >
                  <div className="flex flex-col">
                    <div className="mb-2 flex items-center gap-2">
                      <EmojiEventsIcon className="text-base text-(--primary-main)" />
                      <h3 className="font-black text-(--text-primary)">
                        {t("activity:sections.participation.recent")}
                      </h3>
                    </div>
                    <div className="space-y-1">
                      <AnimatePresence initial={false}>
                        {(participation?.recent ?? []).slice(0, 6).map((r, i) => {
                          const participationRecord = r as Partial<{ id?: number | string }>
                          const itemKey =
                            pickKeyCandidate(participationRecord.id) ?? participationItemKey(r, i)
                          return (
                            <motion.div
                              key={itemKey}
                              variants={listItemVariants}
                              initial={hasInitiallyLoaded ? false : "hidden"}
                              animate="show"
                              exit={{ opacity: 0 }}
                              transition={{ delay: reduce || hasInitiallyLoaded ? 0 : i * 0.04 }}
                              className="py-1"
                              style={
                                reduce
                                  ? undefined
                                  : { willChange: "transform, opacity", transform: "translateZ(0)" }
                              }
                            >
                              <div className="flex items-center gap-2">
                                <div className="h-2 w-2 rounded-full bg-(--warning-text)/(--opacity-heavy) shadow-pulse-warning" />
                                <div className="flex min-w-0 flex-1 flex-wrap items-baseline gap-1.5">
                                  <span className="font-bold text-(--text-primary)">{r.title}</span>
                                  <span className="text-sm text-(--text-label)">
                                    {[formatDate(r.date), r.role].filter(Boolean).join(separator)}
                                  </span>
                                </div>
                              </div>
                            </motion.div>
                          )
                        })}
                      </AnimatePresence>
                      {!loading &&
                        (!participation?.recent || participation.recent.length === 0) && (
                          <p className="px-1 py-1 text-sm text-(--text-label)">{noDataText}</p>
                        )}
                    </div>
                  </div>
                </CardShell>
              </motion.div>
            </section>
          </motion.div>
          <Dialog
            open={detail !== ""}
            onClose={() => setDetail("")}
            title={detailSection ? t(`activity:sections.${detailSection}.dialogTitle`) : ""}
            size="md"
          >
            {detail === "attendance" && (
              <div className="space-y-4">
                <p className="text-base text-(--text-primary)">
                  {t("activity:sections.attendance.dialogTotal", {
                    present: attendance?.present ?? 0,
                    total: attendance?.total ?? 0,
                    period: attendance?.periodLabel || labelByPeriod(period),
                  })}
                </p>
                <ProgressBar
                  value={Math.max(0, Math.min(100, attendance?.percent ?? 0))}
                  className="h-2.5 rounded-lg"
                  barClassName="bg-(--success-text) rounded-lg"
                />
                <div className="space-y-2">
                  {(attendance?.recent ?? []).map((r, i) => (
                    <div key={attendanceItemKey(r, i)} className="space-y-0.5">
                      <p className="text-sm font-semibold text-(--text-primary)">
                        {`${r.course || attendanceLessonFallback} — ${attendanceStatusLabel(r.status)}`}
                      </p>
                      <p className="text-xs text-(--text-caption)">{formatDate(r.date)}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}
            {detail === "grades" && (
              <div className="space-y-4">
                <p className="text-base font-semibold text-(--text-primary)">
                  {grades?.scale === "gpa"
                    ? `GPA ${(grades?.average ?? 0).toFixed(2)}`
                    : grades?.scale === "100"
                      ? `${Math.round(grades?.average ?? 0)}/100`
                      : `${(grades?.average ?? 0).toFixed(1)}/5`}
                </p>
                <div className="space-y-2">
                  {(grades?.recent ?? []).map((r, i) => (
                    <div key={gradeItemKey(r, i)} className="space-y-0.5">
                      <p className="text-sm font-semibold text-(--text-primary)">
                        {`${r.course} — ${r.score}${r.max ? "/" + r.max : ""}`}
                      </p>
                      <p className="text-xs text-(--text-caption)">{formatDate(r.date)}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}
            {detail === "participation" && (
              <div className="space-y-4">
                <p className="text-base text-(--text-primary)">
                  {[
                    t("activity:sections.participation.eventsCount", {
                      value: String(participation?.events ?? 0),
                      count: participation?.events ?? 0,
                    }),
                    participation?.hours != null
                      ? t("activity:sections.participation.summaryHours", {
                          count: participation.hours ?? 0,
                        })
                      : null,
                    participation?.groups != null
                      ? t("activity:sections.participation.summaryGroups", {
                          count: participation.groups ?? 0,
                        })
                      : null,
                  ]
                    .filter(Boolean)
                    .join(separator)}
                </p>
                <div className="space-y-2">
                  {(participation?.recent ?? []).map((r, i) => (
                    <div key={participationItemKey(r, i)} className="space-y-0.5">
                      <p className="text-sm font-semibold text-(--text-primary)">{r.title}</p>
                      <p className="text-xs text-(--text-caption)">
                        {[formatDate(r.date), r.role].filter(Boolean).join(separator)}
                      </p>
                    </div>
                  ))}
                </div>
              </div>
            )}
            {detail === "attendance_recent" && (
              <div className="space-y-2">
                {(attendance?.recent ?? []).map((r, i) => (
                  <div key={attendanceItemKey(r, i)} className="space-y-0.5">
                    <p className="text-sm font-semibold text-(--text-primary)">
                      {`${r.course || attendanceLessonFallback} — ${attendanceStatusLabel(r.status)}`}
                    </p>
                    <p className="text-xs text-(--text-caption)">{formatDate(r.date)}</p>
                  </div>
                ))}
              </div>
            )}
            {detail === "grades_recent" && (
              <div className="space-y-2">
                {(grades?.recent ?? []).map((r, i) => (
                  <div key={gradeItemKey(r, i)} className="space-y-0.5">
                    <p className="text-sm font-semibold text-(--text-primary)">
                      {`${r.course} — ${r.score}${r.max ? "/" + r.max : ""}`}
                    </p>
                    <p className="text-xs text-(--text-caption)">{formatDate(r.date)}</p>
                  </div>
                ))}
              </div>
            )}
            {detail === "participation_recent" && (
              <div className="space-y-2">
                {(participation?.recent ?? []).map((r, i) => (
                  <div key={participationItemKey(r, i)} className="space-y-0.5">
                    <p className="text-sm font-semibold text-(--text-primary)">{r.title}</p>
                    <p className="text-xs text-(--text-caption)">
                      {[formatDate(r.date), r.role].filter(Boolean).join(separator)}
                    </p>
                  </div>
                ))}
              </div>
            )}
            <div className="mt-6 flex justify-end">
              <Button variant="outline" onClick={() => setDetail("")}>
                {t("activity:dialog.close")}
              </Button>
            </div>
          </Dialog>
        </div>
      </PageFadeIn>
    </Layout>
  )
}
