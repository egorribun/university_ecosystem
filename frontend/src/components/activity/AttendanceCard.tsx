import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { animate, useMotionValue } from "framer-motion"
import { ProgressBar } from "@/components/ui"
import AnimatedRing, { useAnimatedNumber } from "@/components/activity/AnimatedRing"
import CardShell from "@/components/activity/CardShell"
import TrendChip from "@/components/activity/TrendChip"
import { EASE_OUT_EXPO } from "@/components/activity/activityTypes"
import type { AttendanceStats } from "@/components/activity/activityTypes"

type AttendanceCardProps = {
  attendance?: AttendanceStats | null
  loading?: boolean
  hasInitiallyLoaded: boolean
  reduceMotion: boolean
  onClick: () => void
  ringSize: number
}

export function AttendanceCard({
  attendance,
  hasInitiallyLoaded,
  reduceMotion,
  onClick,
  ringSize,
}: AttendanceCardProps) {
  const { t } = useTranslation(["activity"])

  const attendancePctAnimated = useAnimatedNumber(
    Math.max(0, Math.min(100, attendance?.percent ?? 0)),
    0.9,
    0
  )

  const progressAttendanceMv = useMotionValue(0)
  const [progressAttendance, setProgressAttendance] = useState(0)

  useEffect(() => {
    const target = Math.max(0, Math.min(100, attendance?.percent ?? 0))
    const controls = animate(progressAttendanceMv, target, {
      duration: reduceMotion ? 0 : 0.9,
      ease: EASE_OUT_EXPO,
    })
    const unsubscribe = progressAttendanceMv.on("change", (value: number) =>
      setProgressAttendance(value)
    )
    return () => {
      controls.stop()
      unsubscribe()
    }
  }, [attendance?.percent, reduceMotion, progressAttendanceMv])

  return (
    <CardShell
      tone="success"
      onClick={onClick}
      hasInitiallyLoaded={hasInitiallyLoaded}
      reduceMotion={reduceMotion}
    >
      <div className="flex items-center gap-4">
        <AnimatedRing
          value={attendance?.percent ?? 0}
          size={ringSize}
          tone="success"
        />
        <div className="flex min-w-0 flex-1 flex-col gap-1">
          <p className="text-micro font-semibold uppercase tracking-wider text-(--text-tertiary)">
            {t("activity:sections.attendance.title")}
          </p>
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-(--fs-card-stat) font-black tracking-tighter tabular-nums lining-nums">
              {attendancePctAnimated}%
            </span>
            <TrendChip value={attendance?.trend} />
          </div>
          <ProgressBar
            value={progressAttendance}
            className="h-2 rounded-full"
            barClassName="bg-(--success-text) rounded-full transition-[width] duration-slow"
          />
          <p className="truncate text-sm text-(--text-muted-subtle)">
            {t("activity:sections.attendance.summary", {
              present: attendance?.present ?? 0,
              total: attendance?.total ?? 0,
              period: attendance?.periodLabel,
            })}
          </p>
        </div>
      </div>
    </CardShell>
  )
}
