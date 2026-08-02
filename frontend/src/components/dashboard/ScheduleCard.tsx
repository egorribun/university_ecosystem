import { memo, useMemo, useCallback, type KeyboardEvent, type CSSProperties } from "react"

import { Link } from "@tanstack/react-router"
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

export const ScheduleCard = memo(function ScheduleCard({
  userRole,
  userGroupId,
  time,
  className,
  style,
  ...props
}: ScheduleCardProps) {
  const { t } = useTranslation(["dashboard", "common"])
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

  const weekDaysDisplay = useMemo(() => {
    const result = t("dashboard:weekDays.display", { returnObjects: true }) as unknown
    if (Array.isArray(result) && result.length === 7) {
      return result as string[]
    }
    return ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
  }, [t])

  const weekDaysRaw = useMemo(() => {
    const result = t("dashboard:weekDays.raw", { returnObjects: true }) as unknown
    if (Array.isArray(result) && result.length === 7) {
      return result as string[]
    }
    return weekDaysDisplay
  }, [t, weekDaysDisplay])

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
    const englishDays = [
      "sunday",
      "monday",
      "tuesday",
      "wednesday",
      "thursday",
      "friday",
      "saturday",
    ]
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
        const s = parseMinutes(l.start_time) ?? -1
        const e = parseMinutes(l.end_time) ?? -1
        return minutesNow >= s && minutesNow < e
      }) || null
    )
  }, [todayLessons, minutesNow])

  const nextLesson = useMemo(() => {
    if (currentLesson) {
      const endM = parseMinutes(currentLesson.end_time)!
      return todayLessons.find((l) => (parseMinutes(l.start_time) ?? 0) > endM) || null
    }
    return todayLessons.find((l) => (parseMinutes(l.start_time) ?? 0) > minutesNow) || null
  }, [todayLessons, currentLesson, minutesNow])

  const currentProgress = useMemo(() => {
    if (!currentLesson) return 0
    const s = parseMinutes(currentLesson.start_time)!
    const e = parseMinutes(currentLesson.end_time)!
    const span = Math.max(1, e - s)
    const passed = Math.min(Math.max(0, minutesNow - s), span)
    return Math.round((passed / span) * 100)
  }, [currentLesson, minutesNow])

  const warmSchedulePage = () => import("../../pages/Schedule").catch(() => {})

  const prepareOnKey = useCallback((event: KeyboardEvent, callback: () => void) => {
    if (event.key === "Enter" || event.key === " " || event.key === "Spacebar") {
      callback()
    }
  }, [])

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
              onPointerDown={warmSchedulePage}
              onKeyDown={(event) => prepareOnKey(event, warmSchedulePage)}
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

        {!currentLesson && nextLesson && (
          <div className="list-item-blue flex items-center gap-3 rounded-xl p-4">
            <Badge
              size="sm"
              variant="outline"
              tone="primary"
              className="shrink-0 text-[0.625rem] font-bold uppercase tracking-wide"
              label={t("dashboard:next")}
            />
            <span className="min-w-0 flex-1 text-base font-semibold leading-tight text-text-primary truncate">
              {nextLesson.subject}
            </span>
            <span className="shrink-0 font-mono text-sm font-medium text-brand">
              {fmtTime(nextLesson.start_time)}–{fmtTime(nextLesson.end_time)}
            </span>
          </div>
        )}

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

      {/* Decorative orbs — visible accents (Wave 48: dash-orb-reactive) */}
      <span
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 z-hide dash-orb-reactive bg-(--grad-schedule-flare) mix-blend-soft-light opacity-medium transition-opacity duration-slow motion-reduce:!animate-none"
        style={{ animation: "orb-breathe 5s ease-in-out infinite" }}
      />
      <span
        aria-hidden="true"
        className="pointer-events-none absolute -top-16 right-8 z-hide dash-orb-reactive h-32 w-32 rounded-full bg-(--flare-schedule-orb) blur-3xl mix-blend-soft-light opacity-medium transition-opacity duration-slower motion-reduce:!animate-none"
        style={{ animation: "orb-pulse-opacity 5s ease-in-out infinite" }}
      />
    </Card>
  )
})

export default ScheduleCard
