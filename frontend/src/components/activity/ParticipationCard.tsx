import { useTranslation } from "react-i18next"
import { useAnimatedNumber } from "@/components/activity/AnimatedRing"
import CardShell from "@/components/activity/CardShell"
import TrendChip from "@/components/activity/TrendChip"
import type { ParticipationStats } from "@/components/activity/activityTypes"

type ParticipationCardProps = {
  participation?: ParticipationStats | null
  loading?: boolean
  hasInitiallyLoaded: boolean
  reduceMotion: boolean
  onClick: () => void
  separator: string
}

export function ParticipationCard({
  participation,
  hasInitiallyLoaded,
  reduceMotion,
  onClick,
  separator,
}: ParticipationCardProps) {
  const { t } = useTranslation(["activity"])

  const partEventsAnimated = useAnimatedNumber(Math.round(participation?.events ?? 0), 0.9, 0)

  return (
    <CardShell
      tone="warning"
      onClick={onClick}
      hasInitiallyLoaded={hasInitiallyLoaded}
      reduceMotion={reduceMotion}
    >
      <div className="flex flex-col gap-1">
        <p className="text-micro font-semibold uppercase tracking-wider text-(--text-label)">
          {t("activity:sections.participation.title")}
        </p>
        <div className="flex items-center gap-2">
          <span className="text-card-stat font-black tracking-tighter tabular-nums lining-nums text-text-primary">
            {t("activity:sections.participation.eventsCount", {
              value: partEventsAnimated,
              count: participation?.events ?? 0,
            })}
          </span>
          <TrendChip value={participation?.trend} />
        </div>
        <p className="text-sm text-text-muted-subtle">
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
    </CardShell>
  )
}
