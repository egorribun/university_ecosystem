import { useTranslation } from "react-i18next"
import { SkeletonMorph } from "@/components/ui/SkeletonMorph"
import AnimatedRing, { useAnimatedNumber } from "./AnimatedRing"
import CardShell from "./CardShell"
import TrendChip from "./TrendChip"
import { toNumber } from "../parsers"
import type { GradeStats } from "../types"
import { motion as motionTokens } from "@/theme/tokens"

type GradesCardProps = {
  grades?: GradeStats | null
  hasInitiallyLoaded: boolean
  ringSize: number
}

function GradesCardSkeleton() {
  return (
    <div className="flex items-center gap-4 p-4 md:p-6 xl:p-8">
      <div className="h-20 w-20 animate-pulse rounded-full bg-[var(--activity-skeleton-bg)]" />
      <div className="flex flex-1 flex-col gap-2">
        <div className="h-3 w-24 animate-pulse rounded bg-[var(--activity-skeleton-bg)]" />
        <div className="h-6 w-16 animate-pulse rounded bg-[var(--activity-skeleton-bg)]" />
        <div className="h-3 w-36 animate-pulse rounded bg-[var(--activity-skeleton-bg)]" />
      </div>
    </div>
  )
}

export function GradesCard({ grades, hasInitiallyLoaded, ringSize }: GradesCardProps) {
  const { t } = useTranslation(["activity"])

  const gradeAverage = toNumber(grades?.average)
  const gradeMax = grades?.scale === "100" ? 100 : grades?.scale === "gpa" ? 4.0 : 5
  const gradeAnimatedValue = grades?.scale === "100" ? Math.round(gradeAverage) : gradeAverage
  const gradesAnimated = useAnimatedNumber(
    gradeAnimatedValue,
    motionTokens.durationLazy,
    grades?.scale === "gpa" ? 2 : grades?.scale === "5" ? 1 : 0
  )

  return (
    <CardShell tone="info" aria-label={t("activity:a11y.gradesCard")}>
      <SkeletonMorph loaded={hasInitiallyLoaded} skeleton={<GradesCardSkeleton />}>
        <div className="flex items-center gap-4">
          <AnimatedRing
            value={gradeAverage}
            max={gradeMax}
            size={ringSize}
            mode="gauge"
            colorVar="var(--activity-grade-accent)"
            fraction={grades?.scale === "gpa" ? 2 : grades?.scale === "5" ? 1 : 0}
            ariaLabel={t("activity:a11y.ringGrades", {
              value: gradeAverage.toFixed(1),
              max: gradeMax,
            })}
          />
          <div className="flex min-w-0 flex-1 flex-col gap-1">
            <p className="text-micro font-semibold uppercase tracking-wider text-text-tertiary">
              {t("activity:sections.grades.title")}
            </p>
            <div className="flex items-center gap-2">
              <span className="text-(--fs-activity-card-title) font-black tracking-tighter tabular-nums lining-nums">
                {grades?.scale === "gpa"
                  ? `GPA ${gradesAnimated}`
                  : grades?.scale === "100"
                    ? `${gradesAnimated}/100`
                    : `${gradesAnimated}/5`}
              </span>
              <TrendChip value={grades?.trend} />
            </div>
            <p className="text-sm text-text-secondary">
              {t("activity:sections.grades.averageLabel")}
            </p>
          </div>
        </div>
      </SkeletonMorph>
    </CardShell>
  )
}
