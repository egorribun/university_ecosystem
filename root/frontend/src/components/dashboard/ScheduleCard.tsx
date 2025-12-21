import { useMemo, type KeyboardEvent, type CSSProperties } from "react"
import { motion } from "framer-motion"
import { Link } from "react-router-dom"
import { useTranslation } from "react-i18next"
import { Badge, Button, Card, ProgressBar, Skeleton } from "@/components/ui"
import { cn } from "@/utils/cn"
import { useDashboardSchedule, type DashboardLesson } from "@/hooks/useDashboardSchedule"
import { fmtTime, nowParity, parseMinutes } from "@/utils/scheduleUtils"

interface ScheduleCardProps {
  userRole?: string | null
  userGroupId?: number | null
  time: Date
  className?: string
  style?: CSSProperties
  "data-fade"?: string
  "data-pop"?: string
}

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
  const schedule: DashboardLesson[] = dashboardScheduleQuery.data ?? []
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

  const warmSchedulePage = () => import("../../pages/Schedule").catch(() => { })

  const prepareOnKey = (event: KeyboardEvent, callback: () => void) => {
    if (event.key === "Enter" || event.key === " " || event.key === "Spacebar") {
      callback()
    }
  }

  // Styles
  const panelBase =
    "group relative isolate overflow-hidden rounded-[2.4rem] border !border-[color:var(--dash-panel-border)] !bg-[color:var(--dash-panel-bg-muted)] text-page-foreground !shadow-[var(--dash-panel-shadow-soft)] transition-[transform,box-shadow] duration-[var(--dash-hover-duration)] ease-[var(--dash-hover-ease)]"
  const panelHover =
    "hover:-translate-y-[var(--dash-hover-lift)] hover:scale-[var(--dash-hover-scale)] hover:shadow-[var(--dash-panel-hover-shadow)] motion-reduce:hover:transform-none motion-reduce:hover:shadow-[var(--dash-panel-shadow)]"
  const listActionBase =
    "group relative isolate w-full overflow-hidden rounded-ue-lg border border-[color:var(--dash-panel-item-divider)] bg-[color:var(--dash-panel-item-bg)] px-4 py-3 text-left transition-[background-color,transform,box-shadow,border-color] duration-[var(--dash-hover-duration)] ease-[var(--dash-hover-ease)] sm:px-5 sm:py-4 group-even/list:bg-[color:var(--dash-panel-item-bg-alt)] hover:border-[color:var(--dash-panel-item-ring)] hover:bg-[color:var(--dash-panel-item-hover)] hover:-translate-y-[var(--dash-hover-lift)] hover:scale-[var(--dash-hover-scale)] focus-visible:border-[color:var(--dash-panel-item-ring)] focus-visible:outline-none focus-visible:shadow-focus motion-reduce:hover:transform-none motion-reduce:hover:translate-y-0 motion-reduce:hover:scale-100 before:pointer-events-none before:absolute before:inset-0 before:rounded-[inherit] before:border before:border-[color:var(--dash-panel-item-ring)] before:opacity-0 before:scale-[0.96] before:transition-[transform,opacity,border-color] before:duration-[var(--dash-hover-duration)] before:ease-[var(--dash-hover-ease)] before:content-[''] hover:before:opacity-100 hover:before:scale-100"

  return (
    <Card
      className={cn(panelBase, panelHover, "dash-panel-schedule", className)}
      padding="lg"
      aria-busy={loadingSched}
      style={style}
      {...props}
    >
      <div className="relative z-[1] space-y-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-[clamp(1.05rem,2vw,1.4rem)] font-extrabold text-page-foreground">
            {t("dashboard:todaySchedule")}
          </h2>
          <div className="flex items-center gap-2">
            <Button
              as={Link}
              to="/schedule"
              size="sm"
              variant="outline"
              className="whitespace-nowrap px-5 transition-transform duration-300 hover:-translate-y-[2px]"
              aria-label={t("dashboard:aria.openFullSchedule")}
              onPointerDown={warmSchedulePage}
              onKeyDown={(event) => prepareOnKey(event, warmSchedulePage)}
            >
              {t("dashboard:fullSchedule")}
            </Button>
          </div>
        </div>
        {currentLesson && (
          <div>
            <div className="mb-3 flex flex-wrap items-center gap-2">
              <Badge size="sm" tone="primary" label={t("dashboard:now")} />
              <span className="text-base font-semibold text-page-foreground">
                {currentLesson.subject}
              </span>
              <Badge
                size="sm"
                className="chip-time"
                label={`${fmtTime(currentLesson.start_time)}–${fmtTime(currentLesson.end_time)}`}
              />
            </div>
            <ProgressBar
              value={currentProgress}
              className="h-2.5"
              ariaLabel={t("common:ariaCurrentLessonProgress")}
            />
          </div>
        )}
        {!currentLesson && nextLesson && (
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <Badge
                size="sm"
                variant="outline"
                tone="primary"
                className="font-bold uppercase tracking-wide"
                label={t("dashboard:next")}
              />
              <span className="text-base font-semibold text-page-foreground">
                {nextLesson.subject}
              </span>
              <Badge
                size="sm"
                className="chip-time"
                label={`${fmtTime(nextLesson.start_time)}–${fmtTime(nextLesson.end_time)}`}
              />
            </div>
          </div>
        )}
        {loadingSched && (
          <div className="space-y-4" role="presentation">
            {[1, 2, 3].map((i) => (
              <div key={i} className="flex flex-col gap-2 rounded-ue-lg border border-[color:var(--dash-panel-item-divider)] bg-[color:var(--dash-panel-item-bg)] px-4 py-3 opacity-60">
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
          <p className="text-sm text-secondary">{t("dashboard:noClasses")}</p>
        )}
        {!loadingSched && todayLessons.length > 0 && (
          <ul className="space-y-3">
            {todayLessons.map((l) => (
              <li key={l.id} className="dash-list-item">
                <div
                  className={cn(
                    listActionBase,
                    "flex flex-col gap-2 text-left sm:gap-2.5",
                    "cursor-default"
                  )}
                >
                  <div className="flex flex-wrap items-center gap-2 text-sm">
                    <Badge
                      size="sm"
                      className="chip-time"
                      label={`${fmtTime(l.start_time)}–${fmtTime(l.end_time)}`}
                    />
                    <span className="text-base font-semibold text-page-foreground">
                      {l.subject}
                    </span>
                    <Badge
                      size="sm"
                      className="chip-type"
                      variant="outline"
                      label={l.lesson_type}
                    />
                  </div>
                  <p className="text-sm leading-relaxed text-secondary">
                    {t("dashboard:lessonMeta", { teacher: l.teacher, room: l.room })}
                  </p>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
      <motion.span
        aria-hidden="true"
        initial={{ opacity: 0 }}
        whileHover={{ opacity: 0.8 }}
        animate={{
          scale: [1, 1.1, 1],
        }}
        transition={{
          duration: 4,
          repeat: Infinity,
          ease: "easeInOut"
        }}
        className="pointer-events-none absolute inset-0 z-0 bg-[radial-gradient(circle_at_top,var(--dash-card-schedule-radial),transparent_72%)] mix-blend-soft-light transition-opacity duration-500"
      />
      <motion.span
        aria-hidden="true"
        initial={{ opacity: 0.3 }}
        whileHover={{ opacity: 0.7 }}
        animate={{
          scale: [1, 1.15, 1],
          x: [0, 8, 0],
          y: [0, -8, 0],
        }}
        transition={{
          duration: 6,
          repeat: Infinity,
          ease: "easeInOut"
        }}
        className="pointer-events-none absolute -top-24 right-10 z-0 h-36 w-36 rounded-full bg-[radial-gradient(circle,var(--dash-card-schedule-orb),transparent)] blur-3xl mix-blend-soft-light transition-opacity duration-700"
      />
    </Card>
  )
}
