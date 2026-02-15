import { useMemo } from "react"
import { useTranslation } from "react-i18next"
import { Calendar as CalendarMonthIcon } from "lucide-react"
import { Badge, Select, ProgressBar } from "@/components/ui"
import FadeSection from "@/components/FadeSection"
import { WeekSelector } from "@/components/schedule/WeekSelector"
import { cn } from "@/utils/cn"
import { useScheduleData } from "@/hooks/useScheduleData"
import useMediaQuery from "@/hooks/useMediaQuery"
import { breakpoints } from "@/theme/tokens"

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
>

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
}: ScheduleHeaderProps) {
  const { t } = useTranslation(["schedule", "common"])
  const isMobile = useMediaQuery(`(max-width: ${breakpoints.ultrawide})`)
  const activeGroupName = useMemo(
    () => groups.find((g) => g.id === selectedGroup)?.name || "",
    [groups, selectedGroup]
  )

  return (
    <header className="mb-6 mt-0">
      <FadeSection
        delay="var(--motion-duration-instant)"
        className="mb-8 flex flex-wrap items-center gap-4 sm:gap-5"
      >
        <div className="flex h-12 w-12 items-center justify-center rounded-full bg-surface/(--opacity-medium) border border-glass-border text-brand shadow-glass">
          <CalendarMonthIcon className="h-7 w-7" />
        </div>
        <h1 className="text-page-title font-bold tracking-tight text-text-primary">
          {user?.role === "student" ? t("schedule:title.student") : t("schedule:title.default")}
        </h1>
        {activeGroupName && (
          <Badge variant="outline" tone="primary" className="translate-y-0.5">
            {t("schedule:header.groupName", { name: activeGroupName })}
          </Badge>
        )}
      </FadeSection>

      <FadeSection delay="var(--motion-duration-rapid)" className="mb-6">
        <WeekSelector currentParity={currentParity} setCurrentParity={setCurrentParity} />
      </FadeSection>

      <FadeSection
        delay="var(--motion-duration-fast)"
        className={cn(
          "no-print group relative isolate mb-6 overflow-hidden rounded-lg border border-glass-border bg-surface/(--opacity-medium) p-6 shadow-glass backdrop-blur-md transition-all hover:shadow-xl",
          !isMobile && "max-w-4xl"
        )}
      >
        {currentLesson ? (
          <div className="relative z-base">
            <div className="mb-4 flex flex-wrap items-center gap-3">
              <Badge size="sm" tone="primary" className="font-semibold">
                {t("schedule:chips.current")}
              </Badge>
              <h3 className="text-lg font-extrabold">{currentLesson.subject}</h3>
              {timeLeftText && <Badge size="sm">{timeLeftText}</Badge>}
            </div>
            <ProgressBar
              value={currentProgress}
              className="mt-5 h-2.5 rounded-full"
              title={`${currentProgress}% ${t("schedule:summary.progress")}`}
              ariaLabel={`${currentProgress}% ${t("schedule:summary.progress")}`}
            />
          </div>
        ) : nextLesson ? (
          <div className="relative z-base flex flex-wrap items-center gap-3">
            <Badge size="sm" variant="outline" tone="primary" className="font-semibold">
              {t("schedule:chips.next")}
            </Badge>
            <h3 className="text-lg font-extrabold">{nextLesson.subject}</h3>
            {timeLeftText && <Badge size="sm">{timeLeftText}</Badge>}
          </div>
        ) : (
          <p>{t("schedule:summary.noMoreToday")}</p>
        )}
      </FadeSection>

      {(user?.role === "teacher" || user?.role === "admin") && (
        <FadeSection delay="var(--motion-duration-base)" className="mb-6 max-w-sm">
          <label className="mb-2 block text-sm font-semibold">
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
