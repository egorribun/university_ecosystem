import { useTranslation } from "react-i18next"
import { ProgressBar } from "@/components/ui"
import { SkeletonMorph } from "@/components/ui/SkeletonMorph"
import AnimatedRing, { useAnimatedNumber } from "./AnimatedRing"
import CardShell from "./CardShell"
import TrendChip from "./TrendChip"
import { type AttendanceStats } from "../types"
import { motion as motionTokens } from "@/theme/tokens"
import { useAnimatedFloat } from "@/hooks/useAnimatedFloat"

type AttendanceCardProps = {
  attendance?: AttendanceStats | null
  hasInitiallyLoaded: boolean
  reduceMotion: boolean
  ringSize: number
}

function AttendanceCardSkeleton() {
  return (
    <div className="flex items-center gap-4 p-4 md:p-6 xl:p-8">
      <div className="h-20 w-20 animate-pulse rounded-full bg-[var(--activity-skeleton-bg)]" />
      <div className="flex flex-1 flex-col gap-2">
        <div className="h-3 w-24 animate-pulse rounded bg-[var(--activity-skeleton-bg)]" />
        <div className="h-6 w-16 animate-pulse rounded bg-[var(--activity-skeleton-bg)]" />
        <div className="h-2 w-full animate-pulse rounded-full bg-[var(--activity-skeleton-bg)]" />
        <div className="h-3 w-32 animate-pulse rounded bg-[var(--activity-skeleton-bg)]" />
      </div>
    </div>
  )
}

// Wave 124 SW1 — `reduceMotion` prop no longer destructured; useAnimatedFloat
// reads `useReducedMotion` internally. Prop kept in interface for caller
// compat (ActivityFeature still passes it; harmless to ignore here).
export function AttendanceCard({
  attendance,
  hasInitiallyLoaded,
  ringSize,
}: AttendanceCardProps) {
  const { t } = useTranslation(["activity"])

  const attendancePct = Math.max(0, Math.min(100, attendance?.percent ?? 0))
  const attendancePctAnimated = useAnimatedNumber(
    attendancePct,
    motionTokens.durationLazy,
    0
  )
  // Wave 124 SW1 — refactored from framer-motion useMotionValue + animate
  // (require domMax) to shared rAF helper. The reduceMotion prop is honored
  // by useAnimatedFloat via useReducedMotion internally — but the original
  // code passed prop reduceMotion + ignored useReducedMotion hook. Both
  // sources should agree (reduceMotion prop is computed from same hook
  // upstream in ActivityFeature).
  const progressAttendance = useAnimatedFloat(attendancePct, motionTokens.durationLazy)

  return (
    <CardShell tone="success" aria-label={t("activity:a11y.attendanceCard")}>
      <SkeletonMorph loaded={hasInitiallyLoaded} skeleton={<AttendanceCardSkeleton />}>
        <div className="flex items-center gap-4">
          <AnimatedRing
            value={attendance?.percent ?? 0}
            size={ringSize}
            mode="percent"
            colorVar="var(--activity-present-accent)"
            ariaLabel={t("activity:a11y.ringAttendance", {
              value: Math.round(attendance?.percent ?? 0),
            })}
          />
          <div className="flex min-w-0 flex-1 flex-col gap-1">
            <p className="text-micro font-semibold uppercase tracking-wider text-text-tertiary">
              {t("activity:sections.attendance.title")}
            </p>
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-(--fs-activity-card-title) font-black tracking-tighter tabular-nums lining-nums">
                {attendancePctAnimated}%
              </span>
              <TrendChip value={attendance?.trend} />
            </div>
            <ProgressBar
              value={progressAttendance}
              ariaLabel={`${t("activity:sections.attendance.title")}: ${attendancePctAnimated}%`}
              className="h-2 rounded-full"
              barClassName="bg-[var(--activity-present-accent)] rounded-full transition-[width] duration-slow"
            />
            <p className="truncate text-sm text-text-secondary">
              {t("activity:sections.attendance.summary", {
                present: attendance?.present ?? 0,
                total: attendance?.total ?? 0,
                period: attendance?.periodLabel,
              })}
            </p>
          </div>
        </div>
      </SkeletonMorph>
    </CardShell>
  )
}
