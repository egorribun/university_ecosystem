import { useTranslation } from "react-i18next"
import { useAnimatedNumber } from "@/components/activity/AnimatedRing"
import CardShell from "@/components/activity/CardShell"
import TrendChip from "@/components/activity/TrendChip"
import { toNumber } from "@/components/activity/activityParsers"
import type { GradeStats } from "@/components/activity/activityTypes"

type GradesCardProps = {
  grades?: GradeStats | null
  loading?: boolean
  hasInitiallyLoaded: boolean
  reduceMotion: boolean
  onClick: () => void
}

export function GradesCard({
  grades,
  hasInitiallyLoaded,
  reduceMotion,
  onClick,
}: GradesCardProps) {
  const { t } = useTranslation(["activity"])

  const gradeAverage = toNumber(grades?.average)
  const gradeAnimatedValue =
    grades?.scale === "100" ? Math.round(gradeAverage) : gradeAverage
  const gradesAnimated = useAnimatedNumber(
    gradeAnimatedValue,
    0.9,
    grades?.scale === "gpa" ? 2 : grades?.scale === "5" ? 1 : 0
  )

  return (
    <CardShell
      tone="info"
      onClick={onClick}
      hasInitiallyLoaded={hasInitiallyLoaded}
      reduceMotion={reduceMotion}
    >
      <div className="flex flex-col gap-1">
        <p className="text-micro font-semibold uppercase tracking-wider text-(--text-label)">
          {t("activity:sections.grades.title")}
        </p>
        <div className="flex items-center gap-2">
          <span className="text-(--fs-card-stat) font-black tracking-tighter tabular-nums lining-nums">
            {grades?.scale === "gpa"
              ? `GPA ${gradesAnimated}`
              : grades?.scale === "100"
                ? `${gradesAnimated}/100`
                : `${gradesAnimated}/5`}
          </span>
          <TrendChip value={grades?.trend} />
        </div>
        <p className="text-sm text-text-muted-subtle">
          {t("activity:sections.grades.averageLabel")}
        </p>
      </div>
    </CardShell>
  )
}
