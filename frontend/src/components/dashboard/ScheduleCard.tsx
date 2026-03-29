import { useMemo, useCallback, type KeyboardEvent, type CSSProperties } from "react"

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

// PERF-27-02: Removed React.memo() — React Compiler "infer" mode handles memoization
export function ScheduleCard({
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

  const parity = useMemo(nowParity, [])
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
    weekDaysDisplay.forEach((name, index) => {
      map.set(name.toLowerCase(), index)
    })
    weekDaysRaw.forEach((name, index) => {
      map.set(name.toLowerCase(), index)
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
      const endM = parseMinutes(currentLesson.end_time) ?? 0
      return todayLessons.find((l) => (parseMinutes(l.start_time) ?? 0) > endM) || null
    }
    return todayLessons.find((l) => (parseMinutes(l.start_time) ?? 0) > minutesNow) || null
  }, [todayLessons, currentLesson, minutesNow])

  const currentProgress = useMemo(() => {
    if (!currentLesson) return 0
    const s = parseMinutes(currentLesson.start_time) ?? 0
    const e = parseMinutes(currentLesson.end_time) ?? 0
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
      className={cn("glass-noise dash-panel-schedule p-6 md:p-7", className)}
      padding="none"
      aria-busy={loadingSched}
      style={style}
      {...props}
    >
      <div className="relative z-base space-y-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="font-extrabold" style={{ fontSize: "clamp(1.35rem, 2.5vw, 1.75rem)" }}>{t("dashboard:todaySchedule")}</h2>
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

        {/* Current lesson with left accent border (Wave 45) */}
        {currentLesson && (
          <div className="rounded-xl border-l-2 border-brand bg-(--bg-matte-list) p-4">
            <div className="mb-3 flex flex-col gap-1 sm:flex-row sm:items-center sm:gap-2">
              <div className="flex flex-wrap items-center gap-2">
                <Badge size="sm" tone="primary" label={t("dashboard:now")} />
                <Badge
                  size="sm"
                  className="border-(--brand-main)/(--opacity-dim) bg-(--brand-main)/(--opacity-faint) font-mono text-xs font-medium text-(--brand-main) dark:bg-(--brand-main)/(--opacity-subtle)"
                  label={`${fmtTime(currentLesson.start_time)}–${fmtTime(currentLesson.end_time)}`}
                />
              </div>
              <span className="text-base font-semibold leading-tight text-text-primary line-clamp-1">
                {currentLesson.subject}
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
          <div className="flex flex-col gap-2 rounded-xl border-l-2 border-brand/(--opacity-soft) bg-(--bg-matte-list) p-4 sm:flex-row sm:items-center">
            <Badge
              size="sm"
              variant="outline"
              tone="primary"
              className="self-start font-bold uppercase tracking-wide"
              label={t("dashboard:next")}
            />
            <div className="flex min-w-0 flex-1 flex-col gap-1 sm:flex-row sm:items-center sm:justify-between sm:gap-3">
              <span className="text-base font-semibold leading-tight text-text-primary truncate">
                {nextLesson.subject}
              </span>
              <Badge
                size="sm"
                className="self-start border-brand/(--opacity-dim) bg-brand/(--opacity-faint) font-mono text-xs font-medium text-brand dark:bg-brand/(--opacity-subtle)"
                label={`${fmtTime(nextLesson.start_time)}–${fmtTime(nextLesson.end_time)}`}
              />
            </div>
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

        {!loadingSched && todayLessons.length > 0 && (
          <ul className="space-y-2.5">
            {todayLessons.map((l, idx) => (
              <li key={l.id} className="dash-list-item px-0 py-0">
                <div
                  className={cn(
                    "list-item-matte list-item-matte-hover",
                    "flex flex-col gap-2 pb-4 sm:gap-2.5",
                    "cursor-default"
                  )}
                  style={{ "--stagger-i": idx } as React.CSSProperties}
                >
                  <div className="flex w-full items-start justify-between gap-3">
                    <span className="text-base font-semibold leading-tight text-text-primary line-clamp-2">
                      {l.subject}
                    </span>
                    <Badge
                      size="sm"
                      className="shrink-0 border-(--brand-main)/(--opacity-dim) bg-(--brand-main)/(--opacity-faint) font-mono text-xs font-medium text-(--brand-main) dark:bg-(--brand-main)/(--opacity-subtle)"
                      label={`${fmtTime(l.start_time)}–${fmtTime(l.end_time)}`}
                    />
                  </div>
                  <div className="flex flex-wrap items-center gap-2 text-sm text-(--text-secondary)">
                    <Badge size="sm" tone="default" variant="outline" label={l.lesson_type} />
                    <span className="truncate max-w-40 opacity-heavy">
                      {t("dashboard:lessonMeta", { teacher: l.teacher, room: l.room })}
                    </span>
                  </div>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* Decorative orbs — visible accents */}
      <span
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 z-hide bg-(--grad-schedule-flare) mix-blend-soft-light opacity-medium transition-opacity duration-slow motion-reduce:!animate-none"
        style={{ animation: "orb-breathe 5s ease-in-out infinite" }}
      />
      <span
        aria-hidden="true"
        className="pointer-events-none absolute -top-16 right-8 z-hide h-32 w-32 rounded-full bg-(--flare-schedule-orb) blur-3xl mix-blend-soft-light opacity-medium transition-opacity duration-slower motion-reduce:!animate-none"
        style={{ animation: "orb-pulse-opacity 5s ease-in-out infinite" }}
      />
    </Card>
  )
}
