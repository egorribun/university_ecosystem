import { useTranslation } from "react-i18next"
import { SkeletonMorph } from "@/components/ui/SkeletonMorph"
import AnimatedRing, { useAnimatedNumber } from "@/components/activity/AnimatedRing"
import CardShell from "@/components/activity/CardShell"
import TrendChip from "@/components/activity/TrendChip"
import type { ParticipationStats } from "@/components/activity/activityTypes"

type ParticipationCardProps = {
  participation?: ParticipationStats | null
  hasInitiallyLoaded: boolean
  separator: string
  ringSize: number
}

function ParticipationCardSkeleton() {
  return (
    <div className="flex items-center gap-4 p-4 md:p-6 xl:p-8">
      <div className="h-20 w-20 animate-pulse rounded-full bg-slate-200 dark:bg-slate-700" />
      <div className="flex flex-1 flex-col gap-2">
        <div className="h-3 w-24 animate-pulse rounded bg-slate-200 dark:bg-slate-700" />
        <div className="h-6 w-20 animate-pulse rounded bg-slate-200 dark:bg-slate-700" />
        <div className="h-3 w-32 animate-pulse rounded bg-slate-200 dark:bg-slate-700" />
      </div>
    </div>
  )
}

export function ParticipationCard({
  participation,
  hasInitiallyLoaded,
  separator,
  ringSize,
}: ParticipationCardProps) {
  const { t } = useTranslation(["activity"])

  const partEventsAnimated = useAnimatedNumber(Math.round(participation?.events ?? 0), 0.9, 0)

  return (
    <CardShell
      tone="warning"
      aria-label={t("activity:a11y.participationCard")}
    >
      <SkeletonMorph loaded={hasInitiallyLoaded} skeleton={<ParticipationCardSkeleton />}>
        <div className="flex items-center gap-4">
          <AnimatedRing
            value={participation?.events ?? 0}
            max={10}
            size={ringSize}
            mode="count"
            colorVar="var(--activity-participation-accent)"
          />
          <div className="flex min-w-0 flex-1 flex-col gap-1">
            <p className="text-micro font-semibold uppercase tracking-wider text-text-tertiary">
              {t("activity:sections.participation.title")}
            </p>
            <div className="flex items-center gap-2">
              <span className="text-(--fs-activity-card-title) font-black tracking-tighter tabular-nums lining-nums text-text-primary">
                {t("activity:sections.participation.eventsCount", {
                  value: partEventsAnimated,
                  count: participation?.events ?? 0,
                })}
              </span>
              <TrendChip value={participation?.trend} />
            </div>
            <p className="text-sm text-text-secondary">
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
        </div>
      </SkeletonMorph>
    </CardShell>
  )
}
