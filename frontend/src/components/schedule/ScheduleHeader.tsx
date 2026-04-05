import { useMemo } from "react"
import { useTranslation } from "react-i18next"
import {
  Calendar as CalendarIcon,
  Clock as ClockIcon,
  MapPin as RoomIcon,
  User as TeacherIcon,
  Sparkles as CompleteIcon,
} from "lucide-react"
import { Badge, Select } from "@/components/ui"
import FadeSection from "@/components/motion/FadeSection"
import { WeekSelector } from "@/components/schedule/WeekSelector"
import { ScheduleToolbar } from "@/components/schedule/ScheduleToolbar"
import { FlipCountdown } from "@/components/schedule/FlipCountdown"
import { cn } from "@/utils/cn"
import { useScheduleData } from "@/hooks/useScheduleData"
import useMediaQuery from "@/hooks/useMediaQuery"
import { breakpoints } from "@/theme/tokens"
import { getTimeStr, getEndTimeStr, parseMinutes } from "./scheduleUtils"
import { uniqueBuildings } from "@/utils/buildingIcons"
import type { Lesson } from "./scheduleUtils"

type ScheduleHeaderProps = Pick<
  ReturnType<typeof useScheduleData>,
  | "user"
  | "groups"
  | "selectedGroup"
  | "setSelectedGroup"
  | "currentParity"
  | "setCurrentParity"
  | "currentLesson"
  | "nextLesson"
  | "timeLeftText"
  | "timeLeftShort"
  | "currentProgress"
  | "todayLessons"
  | "nowTick"
> & {
  isExporting?: boolean
  onOpenSettings?: () => void
  gridRef?: React.RefObject<HTMLElement | null>
}

/** SVG Circular Progress Ring */
function ProgressRing({ progress, size = 80, stroke = 6 }: { progress: number; size?: number; stroke?: number }) {
  const radius = (size - stroke) / 2
  const circumference = 2 * Math.PI * radius
  const offset = circumference - (progress / 100) * circumference
  return (
    <svg width={size} height={size} className="sched-progress-ring" aria-hidden="true">
      <circle className="sched-progress-ring-bg" cx={size / 2} cy={size / 2} r={radius} strokeWidth={stroke} />
      <circle
        className="sched-progress-ring-fill"
        cx={size / 2} cy={size / 2} r={radius} strokeWidth={stroke}
        strokeDasharray={circumference}
        strokeDashoffset={offset}
      />
    </svg>
  )
}

/** Compute day statistics from lessons */
function useDayStats(lessons: Lesson[]) {
  return useMemo(() => {
    const totalLessons = lessons.length
    const totalMinutes = lessons.reduce((acc, l) => {
      const s = parseMinutes(l.start_time)
      const e = parseMinutes(l.end_time)
      return acc + (s != null && e != null && e > s ? e - s : 90)
    }, 0)
    const hours = Math.floor(totalMinutes / 60)
    const mins = totalMinutes % 60
    const buildings = uniqueBuildings(lessons)
    return { totalLessons, hours, mins, buildings }
  }, [lessons])
}

export function ScheduleHeader({
  user,
  groups,
  selectedGroup,
  setSelectedGroup,
  currentParity,
  setCurrentParity,
  currentLesson,
  nextLesson,
  timeLeftText,
  timeLeftShort,
  currentProgress,
  todayLessons,
  nowTick,
  isExporting,
  onOpenSettings,
  gridRef,
}: ScheduleHeaderProps) {
  const { t } = useTranslation(["schedule", "common"])
  const isMobile = useMediaQuery(`(max-width: ${breakpoints.desktop})`)
  const activeGroupName = useMemo(
    () => groups.find((g) => g.id === selectedGroup)?.name || "",
    [groups, selectedGroup],
  )
  const dayStats = useDayStats(todayLessons ?? [])

  // Flip countdown: show when next lesson starts in < 30 min
  const nextStartMinutes = useMemo(() => {
    const lesson = currentLesson ? null : nextLesson
    if (!lesson) return null
    return parseMinutes(lesson.start_time)
  }, [currentLesson, nextLesson])

  const minutesNow = nowTick.getHours() * 60 + nowTick.getMinutes()
  const showCountdown = useMemo(() => {
    if (nextStartMinutes == null) return false
    const diff = nextStartMinutes - minutesNow
    return diff > 0 && diff <= 30
  }, [nextStartMinutes, minutesNow])

  return (
    <header className="relative mb-6 mt-0">
      {/* ═══ Premium hero card (Wave 71b) ═══════════════════ */}
      <FadeSection delay="var(--motion-duration-instant)">
        <div className="sched-hero-card glass-noise p-6 sm:p-8">
          {/* ── Decorative layer (clipped to card) ────────── */}
          <div className="pointer-events-none absolute inset-0 overflow-hidden rounded-[inherit]" aria-hidden="true">
            <div className="sched-hero-flare" />
            {/* Aurora orbs inside hero */}
            <div className="sched-orb-1 absolute -left-20 -top-20 h-48 w-48 rounded-full opacity-60 blur-3xl sm:h-64 sm:w-64" />
            <div className="sched-orb-2 absolute -right-16 top-4 h-40 w-40 rounded-full opacity-45 blur-3xl sm:h-52 sm:w-52" />
          </div>

          {/* ── Title + Group badge ─────────────────────────── */}
          <div className="relative z-base mb-5 flex flex-wrap items-center gap-4 sm:gap-5">
            <div className="sched-badge-matte flex h-12 w-12 items-center justify-center rounded-full text-brand">
              <CalendarIcon className="h-7 w-7" aria-hidden="true" />
            </div>
            <h1
              className="font-bold tracking-tight text-text-primary"
              style={{ fontSize: "var(--fs-sched-hero)" }}
            >
              {user?.role === "student" ? t("schedule:title.student") : t("schedule:title.default")}
            </h1>
            {activeGroupName && (
              <Badge variant="outline" tone="primary" className="sched-badge-matte translate-y-0.5">
                {t("schedule:header.groupName", { name: activeGroupName })}
              </Badge>
            )}
          </div>

          {/* ── Controls bar ──────────────────────────────── */}
          <div className="relative z-base mb-5">
            <ScheduleToolbar isExporting={isExporting} onOpenSettings={onOpenSettings} gridRef={gridRef}>
              <WeekSelector currentParity={currentParity} setCurrentParity={setCurrentParity} />
            </ScheduleToolbar>
          </div>

          {/* ── Status card: Current / Next / Stats ─────── */}
          <div className={cn("relative z-base no-print", !isMobile && "max-w-4xl")}>
            {currentLesson ? (
              /* ── CURRENT LESSON — premium card with progress ring ── */
              <div className="sched-status-card sched-current-glow p-5 sm:p-6">
                <div className="relative z-base flex items-center gap-5">
                  <div className="relative shrink-0">
                    <ProgressRing progress={currentProgress} size={isMobile ? 64 : 80} />
                    <div className="absolute inset-0 flex items-center justify-center">
                      <span className="text-lg font-extrabold text-brand tabular-nums">
                        {Math.max(0, 100 - currentProgress)}%
                      </span>
                    </div>
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="mb-2 flex flex-wrap items-center gap-2">
                      <Badge size="sm" tone="primary" className="sched-badge-matte font-semibold shadow-glow-primary">
                        {t("schedule:chips.current")}
                      </Badge>
                      {timeLeftShort && (
                        <span className="inline-flex items-center gap-1 rounded-lg border border-glass-border bg-surface/(--opacity-dim) px-2 py-0.5 text-xs font-semibold font-mono tabular-nums text-text-secondary" aria-live="polite" aria-label={timeLeftText}>
                          <ClockIcon size={11} className="text-brand opacity-70" aria-hidden="true" />
                          {timeLeftShort}
                        </span>
                      )}
                    </div>
                    <h3 className="mb-1.5 text-xl font-extrabold tracking-tight text-text-primary">{currentLesson.subject}</h3>
                    <div className="flex flex-wrap items-center gap-3 text-sm text-text-secondary">
                      {currentLesson.teacher && (
                        <span className="flex items-center gap-1">
                          <TeacherIcon size={14} className="text-brand" aria-hidden="true" />
                          {currentLesson.teacher}
                        </span>
                      )}
                      {currentLesson.room && (
                        <span className="flex items-center gap-1">
                          <RoomIcon size={14} className="text-brand" aria-hidden="true" />
                          {currentLesson.room}
                        </span>
                      )}
                      <span className="flex items-center gap-1 font-mono tabular-nums">
                        <ClockIcon size={14} className="text-brand" aria-hidden="true" />
                        {`${getTimeStr(currentLesson)}–${getEndTimeStr(currentLesson)}`}
                      </span>
                    </div>
                  </div>
                </div>
                {/* Progress bar */}
                <div className="mt-4 sched-progress-bar h-2 w-full rounded-full">
                  <div
                    className="sched-progress-fill"
                    style={{ width: `${currentProgress}%` }}
                    role="progressbar"
                    aria-valuenow={currentProgress}
                    aria-valuemin={0}
                    aria-valuemax={100}
                  />
                </div>
              </div>
            ) : nextLesson ? (
              /* ── NEXT LESSON — compact status card ─────────── */
              <div className="sched-status-card px-4 py-3">
                <div className="relative z-base flex flex-wrap items-center gap-2">
                  <Badge size="xs" tone="primary" className="sched-badge-matte font-semibold">
                    {t("schedule:chips.next")}
                  </Badge>
                  <h3 className="text-base font-extrabold tracking-tight text-text-primary">{nextLesson.subject}</h3>
                  {/* Inline metadata — same row */}
                  {nextLesson.teacher && (
                    <span className="flex items-center gap-1 text-xs text-text-secondary">
                      <TeacherIcon size={12} className="text-brand opacity-60" aria-hidden="true" />
                      {nextLesson.teacher}
                    </span>
                  )}
                  {nextLesson.room && (
                    <span className="flex items-center gap-1 text-xs text-text-secondary">
                      <RoomIcon size={12} className="text-brand opacity-60" aria-hidden="true" />
                      {nextLesson.room}
                    </span>
                  )}
                  <span className="flex items-center gap-1 text-xs font-mono tabular-nums text-text-secondary">
                    <ClockIcon size={12} className="text-brand opacity-60" aria-hidden="true" />
                    {`${getTimeStr(nextLesson)}–${getEndTimeStr(nextLesson)}`}
                  </span>
                  {timeLeftShort && (
                    <span className="inline-flex items-center gap-1 rounded-md border border-glass-border bg-surface/(--opacity-dim) px-1.5 py-0.5 text-[0.625rem] font-semibold font-mono tabular-nums text-text-secondary" aria-live="polite" aria-label={timeLeftText}>
                      <ClockIcon size={10} className="text-brand opacity-70" aria-hidden="true" />
                      {timeLeftShort}
                    </span>
                  )}
                  {showCountdown && nextStartMinutes != null && (
                    <FlipCountdown targetMinutes={nextStartMinutes} />
                  )}
                </div>
              </div>
            ) : (
              /* ── DAY STATS — when no more lessons ────────── */
              <div className="sched-stats-card p-5">
                {dayStats.totalLessons > 0 ? (
                  <div className="flex items-center justify-center gap-5 text-sm text-text-secondary">
                    <span className="flex items-center gap-1.5">
                      <CompleteIcon size={16} className="text-brand" aria-hidden="true" />
                      <span className="font-semibold text-text-primary">{dayStats.totalLessons}</span>
                      {t("schedule:stats.lessons", { defaultValue: "lessons" })}
                    </span>
                    <span className="h-4 w-px bg-glass-border" aria-hidden="true" />
                    <span>
                      <span className="font-semibold text-text-primary font-mono tabular-nums">{dayStats.hours}</span>{t("schedule:stats.hoursShort")}
                      {dayStats.mins > 0 && <> <span className="font-semibold text-text-primary font-mono tabular-nums">{dayStats.mins}</span>{t("schedule:stats.minutesShort")}</>}
                    </span>
                    {dayStats.buildings.length > 0 && (
                      <>
                        <span className="h-4 w-px bg-glass-border" aria-hidden="true" />
                        <span>
                          {t("schedule:stats.buildings", { defaultValue: "buildings" })}{" "}
                          <span className="font-semibold text-text-primary">{dayStats.buildings.join(", ")}</span>
                        </span>
                      </>
                    )}
                  </div>
                ) : (
                  <p className="text-center text-sm text-text-secondary">
                    {t("schedule:summary.noMoreToday")}
                  </p>
                )}
              </div>
            )}
          </div>
        </div>
      </FadeSection>

      {/* ── Group selector (teacher/admin only) ─────────── */}
      {(user?.role === "teacher" || user?.role === "admin") && (
        <FadeSection delay="var(--motion-duration-base)" className="mt-6 max-w-[24rem]">
          <label className="mb-2 block text-sm font-semibold" htmlFor="schedule-group-selector">
            {t("schedule:form.groupLabel")}
          </label>
          <Select
            id="schedule-group-selector"
            value={selectedGroup ?? ""}
            onValueChange={(val) => setSelectedGroup(val || null)}
            options={groups.map((g) => ({ value: g.id, label: g.name }))}
            placeholder={t("schedule:form.groupLabel")}
          />
        </FadeSection>
      )}
    </header>
  )
}
