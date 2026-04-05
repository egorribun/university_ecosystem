import { useMemo } from "react"
import { useTranslation } from "react-i18next"
import {
  Calendar as CalendarIcon,
  Clock as ClockIcon,
  MapPin as RoomIcon,
  User as TeacherIcon,
  BookOpen,
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
  | "currentProgress"
  | "todayLessons"
> & {
  isExporting?: boolean
  onOpenSettings?: () => void
  /** Ref for grid element (export) */
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
        stroke="var(--color-brand)"
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
      return acc + (s != null && e != null ? e - s : 90)
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
  currentProgress,
  todayLessons,

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

  // Flip countdown: show when next lesson starts in < 30 min (FIX-67-06: extracted from IIFE)
  const nextStartMinutes = useMemo(() => {
    const lesson = currentLesson ? null : nextLesson
    if (!lesson) return null
    return parseMinutes(lesson.start_time)
  }, [currentLesson, nextLesson])

  const showCountdown = useMemo(() => {
    if (nextStartMinutes == null) return false
    const now = new Date()
    const nowMin = now.getHours() * 60 + now.getMinutes()
    const diff = nextStartMinutes - nowMin
    return diff > 0 && diff <= 30
  }, [nextStartMinutes])

  return (
    <header className="relative mb-6 mt-0">
      {/* ── Aurora mesh background ──────────────────────── */}
      <div
        className="sched-aurora-hero pointer-events-none absolute inset-0 -z-1 overflow-hidden rounded-3xl"
        aria-hidden="true"
      >
        <div className="sched-orb-1 absolute -left-20 -top-20 h-72 w-72 rounded-full opacity-70 blur-3xl" />
        <div className="sched-orb-2 absolute -right-16 top-8 h-56 w-56 rounded-full opacity-55 blur-3xl" />
        <div className="sched-orb-3 absolute -bottom-12 left-1/3 h-48 w-48 rounded-full opacity-45 blur-3xl" />
      </div>

      {/* ── Title + Group badge ─────────────────────────── */}
      <FadeSection
        delay="var(--motion-duration-instant)"
        className="mb-6 flex flex-wrap items-center gap-4 sm:gap-5"
      >
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
      </FadeSection>

      {/* ── Toolbar (week nav + view mode + actions) ────── */}
      <FadeSection delay="var(--motion-duration-rapid)" className="mb-6">
        <ScheduleToolbar isExporting={isExporting} onOpenSettings={onOpenSettings} gridRef={gridRef} />
      </FadeSection>

      {/* ── Week parity selector ────────────────────────── */}
      <FadeSection delay="var(--motion-duration-rapid)" className="mb-6">
        <WeekSelector currentParity={currentParity} setCurrentParity={setCurrentParity} />
      </FadeSection>

      {/* ── Current / Next lesson status card (Wave 66 redesign) ── */}
      <FadeSection
        delay="var(--motion-duration-fast)"
        className={cn("no-print mb-6", !isMobile && "max-w-4xl")}
      >
        {currentLesson ? (
          <div className="sched-current-glow glass-noise relative isolate overflow-hidden rounded-xl border border-glass-border bg-surface/(--opacity-medium) p-5 shadow-glass backdrop-blur-md">
            <div className="relative z-base flex items-center gap-5">
              {/* Circular progress ring */}
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
                  <Badge size="sm" tone="primary" className="sched-badge-matte font-semibold">
                    {t("schedule:chips.current")}
                  </Badge>
                  {timeLeftText && (
                    <Badge size="xs" variant="outline" aria-live="polite">
                      {timeLeftText}
                    </Badge>
                  )}
                </div>
                <h3 className="mb-1.5 text-lg font-extrabold tracking-tight">{currentLesson.subject}</h3>
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
                  <span className="flex items-center gap-1">
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
          <div className="glass-noise relative overflow-hidden rounded-xl border border-glass-border bg-surface/(--opacity-medium) p-5 shadow-glass backdrop-blur-md">
            <div className="relative z-base flex flex-wrap items-center gap-4">
              <Badge size="sm" variant="outline" tone="primary" className="sched-badge-matte font-semibold">
                {t("schedule:chips.next")}
              </Badge>
              <h3 className="text-lg font-extrabold tracking-tight">{nextLesson.subject}</h3>
              {timeLeftText && (
                <Badge size="xs" variant="outline" aria-live="polite">
                  {timeLeftText}
                </Badge>
              )}
              {/* Flip countdown when < 30 min until next lesson (FIX-67-06: removed IIFE) */}
              {showCountdown && nextStartMinutes != null && (
                <FlipCountdown targetMinutes={nextStartMinutes} className="ml-auto" />
              )}
            </div>
          </div>
        ) : (
          /* Day stats when no more lessons */
          <div className="rounded-xl border border-glass-border/(--opacity-soft) bg-surface/(--opacity-dim) p-5">
            {dayStats.totalLessons > 0 ? (
              <div className="flex items-center justify-center gap-4 text-sm text-text-secondary">
                <span className="flex items-center gap-1.5">
                  <BookOpen size={14} className="text-brand" aria-hidden="true" />
                  <span className="font-semibold text-text-primary">{dayStats.totalLessons}</span>
                  {t("schedule:stats.lessons", { defaultValue: "lessons" })}
                </span>
                <span className="text-text-muted-subtle">·</span>
                <span>
                  <span className="font-semibold text-text-primary">{dayStats.hours}</span>{t("schedule:stats.hoursShort")}
                  {dayStats.mins > 0 && <> <span className="font-semibold text-text-primary">{dayStats.mins}</span>{t("schedule:stats.minutesShort")}</>}
                </span>
                {dayStats.buildings.length > 0 && (
                  <>
                    <span className="text-text-muted-subtle">·</span>
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
      </FadeSection>

      {/* ── Group selector (teacher/admin only) ─────────── */}
      {(user?.role === "teacher" || user?.role === "admin") && (
        <FadeSection delay="var(--motion-duration-base)" className="mb-6 max-w-[24rem]">
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
