import { useMemo } from "react"
import { useTranslation } from "react-i18next"
import {
  Calendar as CalendarIcon,
  Clock as ClockIcon,
  MapPin as RoomIcon,
  User as TeacherIcon,
  CircleCheckBig as CompleteIcon,
  SlidersHorizontal as ControlsIcon,
} from "lucide-react"
import { Badge, Select } from "@/components/ui"
import FadeSection from "@/components/motion/FadeSection"
import { FlipCountdown } from "@/components/schedule/FlipCountdown"
import { cn } from "@/utils/cn"
import { useScheduleData } from "@/hooks/useScheduleData"
import useMediaQuery from "@/hooks/useMediaQuery"
import { breakpoints } from "@/theme/tokens"
import { getTimeStr, getEndTimeStr, parseMinutes } from "./scheduleUtils"
import { uniqueBuildings } from "@/utils/buildingIcons"
import type { Lesson } from "./scheduleUtils"

type ScheduleHeaderProps = Omit<
  Pick<
    ReturnType<typeof useScheduleData>,
    | "user"
    | "groups"
    | "selectedGroup"
    | "setSelectedGroup"
    | "currentLesson"
    | "nextLesson"
    | "timeLeftText"
    | "timeLeftShort"
    | "currentProgress"
    | "todayLessons"
    | "nowTick"
  >,
  "todayLessons"
> & {
  todayLessons?: Lesson[]
  onOpenSettings?: () => void
}

/** SVG Circular Progress Ring */
function ProgressRing({
  progress,
  size = 80,
  stroke = 6,
}: {
  progress: number
  size?: number
  stroke?: number
}) {
  const radius = (size - stroke) / 2
  const circumference = 2 * Math.PI * radius
  const offset = (progress / 100) * circumference
  return (
    <svg width={size} height={size} className="sched-progress-ring" aria-hidden="true">
      <circle
        className="sched-progress-ring-bg"
        cx={size / 2}
        cy={size / 2}
        r={radius}
        strokeWidth={stroke}
      />
      <circle
        className="sched-progress-ring-fill"
        cx={size / 2}
        cy={size / 2}
        r={radius}
        strokeWidth={stroke}
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
  currentLesson,
  nextLesson,
  timeLeftText,
  timeLeftShort,
  currentProgress,
  todayLessons,
  nowTick,
  onOpenSettings,
}: ScheduleHeaderProps) {
  const { t } = useTranslation(["schedule", "common"])
  const isMobile = useMediaQuery(`(max-width: ${breakpoints.desktop})`)
  const activeGroupName = useMemo(
    () => groups.find((g) => g.id === selectedGroup)?.name || "",
    [groups, selectedGroup]
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
    <header className="relative mb-6 sm:mb-8 space-y-4">
      {/* ── Title row (matches News page style) ──────────── */}
      <FadeSection delay="60ms" className="flex items-center gap-3 flex-wrap">
        <div className="flex items-center gap-2 sm:gap-3 min-w-0">
          <div className="sched-badge-matte hidden sm:flex h-11 w-11 items-center justify-center rounded-xl text-text-primary shrink-0">
            <CalendarIcon size={20} strokeWidth={2.2} aria-hidden="true" />
          </div>
          <h1 className="text-fluid-h1 font-extrabold tracking-tight text-text-primary whitespace-nowrap">
            {user?.role === "student" ? t("schedule:title.student") : t("schedule:title.default")}
            {activeGroupName && (
              <span
                className="sched-badge-matte ml-2 inline-flex items-center justify-center rounded-full px-2 py-0.5 align-middle font-bold leading-none"
                style={{ fontSize: "0.45em" }}
              >
                {t("schedule:header.groupName", { name: activeGroupName })}
              </span>
            )}
          </h1>
        </div>
        {/* ── Controls button — opens settings panel ── */}
        {onOpenSettings && (
          <button
            type="button"
            onClick={onOpenSettings}
            aria-label={t("schedule:toolbar.settings")}
            className="sched-settings-btn ml-auto flex h-10 w-10 min-h-[44px] min-w-[44px] items-center justify-center rounded-xl text-text-secondary hover:text-text-primary focus-visible:ring-2 focus-visible:ring-brand"
          >
            <ControlsIcon size={18} aria-hidden="true" />
          </button>
        )}
      </FadeSection>

      {/* ── Status card: Current / Next / Stats ─────── */}
      <FadeSection delay="120ms">
        <div className={cn("no-print", !isMobile && "max-w-4xl")}>
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
                    <Badge
                      size="sm"
                      tone="primary"
                      className="sched-badge-matte font-semibold shadow-glow-primary"
                    >
                      {t("schedule:chips.current")}
                    </Badge>
                    {timeLeftShort && (
                      <span
                        className="inline-flex items-center gap-1 rounded-lg matte-chip px-2 py-0.5 text-xs font-semibold font-mono tabular-nums text-text-secondary"
                        aria-live="polite"
                        aria-label={timeLeftText}
                      >
                        <ClockIcon size={11} className="text-brand opacity-70" aria-hidden="true" />
                        {timeLeftShort}
                      </span>
                    )}
                  </div>
                  <h3 className="mb-1.5 text-xl font-extrabold tracking-tight text-text-primary">
                    {currentLesson.subject}
                  </h3>
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
            </div>
          ) : nextLesson ? (
            /* ── NEXT LESSON — compact status card ─────────── */
            <div className="sched-status-card px-4 py-3">
              <div className="relative z-base flex flex-wrap items-center gap-2">
                <Badge size="xs" tone="primary" className="sched-badge-matte font-semibold">
                  {t("schedule:chips.next")}
                </Badge>
                <h3 className="text-base font-extrabold tracking-tight text-text-primary">
                  {nextLesson.subject}
                </h3>
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
                  <span
                    className="inline-flex items-center gap-1 rounded-md matte-chip px-1.5 py-0.5 text-[0.625rem] font-semibold font-mono tabular-nums text-text-secondary"
                    aria-live="polite"
                    aria-label={timeLeftText}
                  >
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
            /* ── DAY COMPLETE — warm motivational message ── */
            <div className="sched-stats-card p-5">
              <p className="text-center text-sm font-medium text-text-secondary">
                <CompleteIcon
                  size={16}
                  className="mr-1.5 inline-block align-[-0.15em] text-brand"
                  aria-hidden="true"
                />
                {dayStats.totalLessons > 0
                  ? t("schedule:dayComplete")
                  : t("schedule:summary.noMoreToday")}
              </p>
            </div>
          )}
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
