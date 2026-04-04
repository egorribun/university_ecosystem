import { useMemo } from "react"
import { useTranslation } from "react-i18next"
import {
  Calendar as CalendarIcon,
  Clock as ClockIcon,
  MapPin as RoomIcon,
  User as TeacherIcon,
} from "lucide-react"
import { Badge, Select } from "@/components/ui"
import FadeSection from "@/components/motion/FadeSection"
import { WeekSelector } from "@/components/schedule/WeekSelector"
import { ScheduleToolbar } from "@/components/schedule/ScheduleToolbar"
import { cn } from "@/utils/cn"
import { useScheduleData } from "@/hooks/useScheduleData"
import useMediaQuery from "@/hooks/useMediaQuery"
import { breakpoints } from "@/theme/tokens"
import { getTimeStr, getEndTimeStr } from "./scheduleUtils"

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
> & {
  onExportIcs?: () => void
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
  onExportIcs,
}: ScheduleHeaderProps) {
  const { t } = useTranslation(["schedule", "common"])
  const isMobile = useMediaQuery(`(max-width: ${breakpoints.ultrawide})`)
  const activeGroupName = useMemo(
    () => groups.find((g) => g.id === selectedGroup)?.name || "",
    [groups, selectedGroup],
  )

  return (
    <header className="relative mb-6 mt-0">
      {/* ── Aurora mesh background ──────────────────────── */}
      <div
        className="sched-aurora-hero pointer-events-none absolute inset-0 -z-1 overflow-hidden rounded-3xl"
        aria-hidden="true"
      >
        <div
          className="absolute -left-20 -top-20 h-72 w-72 rounded-full opacity-70 blur-3xl"
          style={{ background: "var(--sched-orb-1)" }}
        />
        <div
          className="absolute -right-16 top-8 h-56 w-56 rounded-full opacity-55 blur-3xl"
          style={{ background: "var(--sched-orb-2)" }}
        />
        <div
          className="absolute -bottom-12 left-1/3 h-48 w-48 rounded-full opacity-45 blur-3xl"
          style={{ background: "var(--sched-orb-3)" }}
        />
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
        <ScheduleToolbar onExportIcs={onExportIcs} />
      </FadeSection>

      {/* ── Week parity selector ────────────────────────── */}
      <FadeSection delay="var(--motion-duration-rapid)" className="mb-6">
        <WeekSelector currentParity={currentParity} setCurrentParity={setCurrentParity} />
      </FadeSection>

      {/* ── Current / Next lesson status card ───────────── */}
      <FadeSection
        delay="var(--motion-duration-fast)"
        className={cn("no-print mb-6", !isMobile && "max-w-4xl")}
      >
        {currentLesson ? (
          <div className="sched-current-glow glass-noise relative isolate overflow-hidden rounded-xl border border-glass-border bg-surface/(--opacity-medium) p-5 shadow-glass backdrop-blur-md">
            <div className="relative z-base">
              <div className="mb-3 flex flex-wrap items-center gap-3">
                <Badge size="sm" tone="primary" className="sched-badge-matte font-semibold">
                  {t("schedule:chips.current")}
                </Badge>
                <h3 className="text-lg font-extrabold tracking-tight">{currentLesson.subject}</h3>
              </div>
              <div className="mb-4 flex flex-wrap items-center gap-3 text-sm text-text-secondary">
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
                {timeLeftText && (
                  <Badge size="xs" variant="outline" aria-live="polite">
                    {timeLeftText}
                  </Badge>
                )}
              </div>
              {/* ── Progress bar with glowing head ──────── */}
              <div className="sched-progress-bar h-2.5 w-full rounded-full">
                <div
                  className="sched-progress-fill"
                  style={{ width: `${currentProgress}%` }}
                  role="progressbar"
                  aria-valuenow={currentProgress}
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-label={`${currentProgress}% ${t("schedule:summary.progress", { defaultValue: "" })}`}
                />
              </div>
            </div>
          </div>
        ) : nextLesson ? (
          <div className="glass-noise relative overflow-hidden rounded-xl border border-glass-border bg-surface/(--opacity-medium) p-5 shadow-glass backdrop-blur-md">
            <div className="relative z-base flex flex-wrap items-center gap-3">
              <Badge size="sm" variant="outline" tone="primary" className="sched-badge-matte font-semibold">
                {t("schedule:chips.next")}
              </Badge>
              <h3 className="text-lg font-extrabold tracking-tight">{nextLesson.subject}</h3>
              {timeLeftText && (
                <Badge size="xs" variant="outline" aria-live="polite">
                  {timeLeftText}
                </Badge>
              )}
            </div>
          </div>
        ) : (
          <div className="rounded-xl border border-glass-border/(--opacity-soft) bg-surface/(--opacity-dim) p-5 text-center text-sm text-text-secondary">
            {t("schedule:summary.noMoreToday")}
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
