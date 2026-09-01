import { memo, useCallback, useMemo, type CSSProperties } from "react"

import { Link, useRouter } from "@tanstack/react-router"
import { useTranslation } from "react-i18next"
import { Badge, Button, Card, ProgressBar, Skeleton } from "@/components/ui"
import { cn } from "@/utils/cn"
import { useDashboardSchedule, type DashboardLesson } from "@/hooks/useDashboardSchedule"
import { fmtTime, nowParity, parseMinutes } from "@/utils/scheduleUtils"

interface ScheduleCardProps {
  userRole?: string | null
  userGroupId?: string | number | null
  time: Date
  className?: string
  style?: CSSProperties
  "data-fade"?: string
  "data-pop"?: string
}

type LessonBounds = { start: number; end: number }
type LessonTimeFields = Pick<DashboardLesson, "start_time" | "end_time">

const ENGLISH_WEEK_DAYS = [
  "Sunday",
  "Monday",
  "Tuesday",
  "Wednesday",
  "Thursday",
  "Friday",
  "Saturday",
]

const readWeekdayArray = (value: unknown, fallback: string[]): string[] =>
  Array.isArray(value) && value.length === 7 ? (value as string[]) : fallback

/**
 * Return a lesson's validated half-open interval.
 *
 * Dashboard payloads come from a remote API, so malformed or inverted times
 * must never be treated as a current/next lesson (or used for progress math).
 * Keep this guard local to the card because the card derives its own schedule
 * view instead of using the full schedule page's time hook.
 */
const getLessonBounds = (lesson: LessonTimeFields | null): LessonBounds | null => {
  const start = parseMinutes(lesson?.start_time ?? "")
  // Keep malformed end times as NaN so the strict comparison below rejects
  // them without a redundant nullable guard (NaN is never greater than start).
  const end = parseMinutes(lesson?.end_time ?? "") ?? Number.NaN
  return start !== null && end > start ? { start, end } : null
}

const lessonStartsAfter = (lesson: LessonTimeFields, threshold: number): boolean =>
  (getLessonBounds(lesson)?.start ?? Number.NaN) > threshold

export const findNextLesson = <T extends LessonTimeFields>(
  todayLessons: readonly T[],
  currentLesson: T | null,
  minutesNow: number
): T | null =>
  todayLessons.find((lesson) =>
    lessonStartsAfter(lesson, getLessonBounds(currentLesson)?.end ?? minutesNow)
  ) ?? null

const calculateLessonProgress = (bounds: LessonBounds | null, minutesNow: number): number =>
  bounds === null
    ? 0
    : Math.round(
        (Math.min(Math.max(0, minutesNow - bounds.start), bounds.end - bounds.start) /
          (bounds.end - bounds.start)) *
          100
      )

export const ScheduleCard = memo(function ScheduleCard({
  userRole,
  userGroupId,
  time,
  className,
  style,
  ...props
}: ScheduleCardProps) {
  const { t } = useTranslation(["dashboard", "common"])
  const router = useRouter()
  const shouldLoadSchedule = userRole === "student" && Boolean(userGroupId)
  const dashboardScheduleQuery = useDashboardSchedule(
    (userRole as "student" | "teacher" | "admin" | null) ?? null,
    userGroupId ?? null
  )
  const schedule: DashboardLesson[] = useMemo(
    () => dashboardScheduleQuery.data ?? [],
    [dashboardScheduleQuery.data]
  )
  const loadingSched = shouldLoadSchedule
    ? dashboardScheduleQuery.isLoading && schedule.length === 0
    : false

  // CQ-72-02: removed useMemo — nowParity() is microsecond-cheap (Date + arithmetic),
  // and empty deps [] made it stale in long-lived tabs (wouldn't update after midnight)
  const parity = nowParity()
  const todayIndex = time.getDay()

  const weekDaysDisplay = useMemo(
    () =>
      readWeekdayArray(t("dashboard:weekDays.display", { returnObjects: true }) as unknown, [
        ...ENGLISH_WEEK_DAYS,
      ]),
    [t]
  )

  const weekDaysRaw = useMemo(
    () =>
      readWeekdayArray(
        t("dashboard:weekDays.raw", { returnObjects: true }) as unknown,
        weekDaysDisplay
      ),
    [t, weekDaysDisplay]
  )

  const weekdayIndex = useMemo(() => {
    const map = new Map<string, number>()
    // i18n display/raw names (e.g. Russian: "воскресенье" → 0)
    weekDaysDisplay.forEach((name, index) => {
      map.set(name.toLowerCase(), index)
    })
    weekDaysRaw.forEach((name, index) => {
      map.set(name.toLowerCase(), index)
    })
    // English backend names — API returns weekday as "sunday", "monday", etc.
    const englishDays = ENGLISH_WEEK_DAYS.map((name) => name.toLowerCase())
    englishDays.forEach((name, index) => {
      map.set(name, index)
    })
    return map
  }, [weekDaysDisplay, weekDaysRaw])

  const todayLessons = useMemo(() => {
    return schedule
      .filter((l) => {
        const normalized = (l.weekday ?? "").toLowerCase()
        const lessonIndex = weekdayIndex.get(normalized)
        return (l.parity === "both" || l.parity === parity) && lessonIndex === todayIndex
      })
      .sort((a, b) => fmtTime(a.start_time).localeCompare(fmtTime(b.start_time)))
  }, [schedule, parity, todayIndex, weekdayIndex])

  const minutesNow = useMemo(() => time.getHours() * 60 + time.getMinutes(), [time])
  const currentLesson = useMemo(() => {
    return (
      todayLessons.find((l) => {
        const bounds = getLessonBounds(l)
        return bounds !== null && minutesNow >= bounds.start && minutesNow < bounds.end
      }) || null
    )
  }, [todayLessons, minutesNow])

  const nextLesson = useMemo(
    () => findNextLesson(todayLessons, currentLesson, minutesNow),
    [todayLessons, currentLesson, minutesNow]
  )

  const currentProgress = useMemo(
    () => calculateLessonProgress(getLessonBounds(currentLesson), minutesNow),
    [currentLesson, minutesNow]
  )

  const shouldShowNextLesson = nextLesson !== null ? currentLesson === null : false
  const nextLessonToDisplay = shouldShowNextLesson ? nextLesson : null

  const warmScheduleRoute = useCallback(() => {
    void router.preloadRoute({ to: "/schedule" }).catch(() => undefined)
  }, [router])

  return (
    <Card
      className={cn(
        "glass-noise refetch-shimmer dash-border-shimmer dash-panel-schedule p-6 md:p-7",
        className
      )}
      padding="none"
      aria-busy={loadingSched}
      data-refetching={dashboardScheduleQuery.isFetching && !dashboardScheduleQuery.isLoading}
      style={style}
      {...props}
    >
      <div className="relative z-base space-y-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="font-extrabold" style={{ fontSize: "clamp(1.35rem, 2.5vw, 1.75rem)" }}>
            {t("dashboard:todaySchedule")}
          </h2>
          <div className="flex items-center gap-2">
            <Button
              as={Link}
              to="/schedule"
              size="sm"
              variant="outline"
              className="btn-dash whitespace-nowrap px-5 transition-transform duration-base hover:-translate-y-0.5"
              aria-label={t("dashboard:aria.openFullSchedule")}
              onPointerDown={warmScheduleRoute}
            >
              {t("dashboard:fullSchedule")}
            </Button>
          </div>
        </div>

        {/* Current lesson — premium blue panel */}
        {currentLesson && (
          <div className="list-item-blue rounded-xl p-4">
            <div className="mb-3 flex items-center justify-between gap-3">
              <div className="flex items-center gap-2.5">
                <Badge size="sm" tone="primary" label={t("dashboard:now")} />
                <span className="text-base font-semibold leading-tight text-text-primary line-clamp-1">
                  {currentLesson.subject}
                </span>
              </div>
              <span className="shrink-0 font-mono text-sm font-medium text-brand">
                {fmtTime(currentLesson.start_time)}–{fmtTime(currentLesson.end_time)}
              </span>
            </div>
            <ProgressBar
              value={currentProgress}
              className="h-2"
              ariaLabel={t("common:ariaCurrentLessonProgress")}
            />
          </div>
        )}

        {nextLessonToDisplay ? (
          <div className="list-item-blue flex items-center gap-3 rounded-xl p-4">
            <Badge
              size="sm"
              variant="outline"
              tone="primary"
              className="shrink-0 text-[0.625rem] font-bold uppercase tracking-wide"
              label={t("dashboard:next")}
            />
            <span className="min-w-0 flex-1 text-base font-semibold leading-tight text-text-primary truncate">
              {nextLessonToDisplay.subject}
            </span>
            <span className="shrink-0 font-mono text-sm font-medium text-brand">
              {fmtTime(nextLessonToDisplay.start_time)}–{fmtTime(nextLessonToDisplay.end_time)}
            </span>
          </div>
        ) : null}

        {loadingSched && (
          <div className="space-y-3" role="presentation">
            {[1, 2, 3].map((i) => (
              <div
                key={i}
                className="flex flex-col gap-2 rounded-xl bg-(--bg-matte-list) px-4 py-3 opacity-medium"
              >
                <div className="flex items-center gap-2">
                  <Skeleton width={80} height={18} />
                  <Skeleton width={120} height={20} />
                </div>
                <Skeleton width="60%" height={14} />
              </div>
            ))}
          </div>
        )}

        {!loadingSched && todayLessons.length === 0 && (
          <p className="text-sm text-(--text-secondary)">{t("dashboard:noClasses")}</p>
        )}

        {/* Wave 49: always list view on dashboard — timeline removed (too cramped for card width) */}
        {!loadingSched && todayLessons.length > 0 && (
          <ul className="space-y-2.5">
            {todayLessons.map((l, idx) => (
              <li key={l.id} className="dash-list-item px-0 py-0">
                <div
                  className={cn(
                    "list-item-blue list-item-blue-hover",
                    "flex flex-col gap-2 sm:gap-2.5",
                    "cursor-default"
                  )}
                  style={{ "--stagger-i": idx } as React.CSSProperties}
                >
                  <div className="flex w-full items-center justify-between gap-3">
                    <span className="text-base font-semibold leading-tight text-text-primary line-clamp-2">
                      {l.subject}
                    </span>
                    <span className="shrink-0 font-mono text-sm font-medium text-brand">
                      {fmtTime(l.start_time)}–{fmtTime(l.end_time)}
                    </span>
                  </div>
                  <div className="flex flex-wrap items-center gap-2 text-sm text-(--text-secondary)">
                    <Badge size="sm" tone="default" variant="outline" label={l.lesson_type} />
                    <span className="opacity-heavy">
                      {t("dashboard:lessonMeta", { teacher: l.teacher, room: l.room })}
                    </span>
                  </div>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </Card>
  )
})

export default ScheduleCard
