import { useRef, type CSSProperties } from "react"
import { motion, useReducedMotion } from "framer-motion"
import { Activity as TimelineIcon } from "lucide-react"
import { cn } from "@/utils/cn"
import useMediaQuery from "@/hooks/useMediaQuery"
import { breakpoints } from "@/theme/tokens"
import { PageLayout } from "@/components/layout/PageLayout"
import FadeSection from "@/components/motion/FadeSection"
import useActivityData from "@/hooks/useActivityData"
import { useActivityComparative } from "@/hooks/useActivityComparative"

import { ActivityBackdrop } from "@/components/activity/ActivityBackdrop"
import { ActivityMotivation } from "@/components/activity/ActivityMotivation"
import { AttendanceCard } from "@/components/activity/AttendanceCard"
import { GradesCard } from "@/components/activity/GradesCard"
import { ParticipationCard } from "@/components/activity/ParticipationCard"
import { ActivityTrendChart } from "@/components/activity/ActivityTrendChart"
import { ActivityBarChart } from "@/components/activity/ActivityBarChart"
import { ActivityHeatmap } from "@/components/activity/ActivityHeatmap"
import { ActivityComparativeCard } from "@/components/activity/ActivityComparativeCard"
import { ActivityExportButton } from "@/components/activity/ActivityExportButton"
import { ActivityTimeline } from "@/components/activity/ActivityTimeline"

export default function Activity() {
  const {
    t,
    period,
    setPeriod,
    attendance,
    grades,
    participation,
    hasInitiallyLoaded,
    periodOptions,
    separator,
    formatDate,
    attendanceStatusLabel,
    attendanceTrendData,
    gradesBySubject,
    heatmapData,
  } = useActivityData()

  const comparative = useActivityComparative(attendance, grades, participation, period)

  const reduce = useReducedMotion() ?? false
  const isSm = useMediaQuery(`(max-width: ${breakpoints.small})`)
  const isMd = useMediaQuery(`(max-width: ${breakpoints.mobile})`)
  const isNarrow = useMediaQuery(`(max-width: ${breakpoints.dashboard})`)
  const isXl = useMediaQuery(`(min-width: ${breakpoints.desktop})`)
  const ringSize = isSm ? 68 : isMd ? 84 : isXl ? 104 : 96

  const contentRef = useRef<HTMLDivElement>(null)

  return (
    <PageLayout
      variant="full"
      seo={{
        title: t("activity:title"),
        description: t("activity:pageDescription"),
      }}
    >
      <div className="activity-theme aurora-mesh relative w-full overflow-x-clip py-6 sm:py-8 md:py-10 px-4 sm:px-6 md:px-10 lg:px-14">
        {/* Layer 0: Decorative backdrop */}
        <ActivityBackdrop isNarrow={isNarrow} prefersReducedMotion={reduce} />

        {/* Layer 1: Content */}
        <div ref={contentRef} className="relative z-[1]">
          {/* ── Header ──────────────────────────────── */}
          <header>
            <FadeSection delay="60ms" className="mb-4 flex flex-wrap items-center gap-3 sm:gap-4">
              <div
                className={cn(
                  "activity-badge-matte hidden sm:flex h-11 w-11 items-center justify-center",
                  "bg-[var(--bg-surface)] text-[var(--activity-present-accent)]"
                )}
              >
                <TimelineIcon size={20} aria-hidden="true" />
              </div>
              <h1 className="flex-1 text-fluid-h1 font-extrabold tracking-tight text-text-primary">
                {t("activity:title")}
                <span
                  className="ml-2 inline-block align-middle rounded-full bg-[var(--activity-present-accent)] px-2 text-[var(--text-inverse)]"
                  style={{ fontSize: "0.45em" }}
                >
                  {t("activity:hero.badge")}
                </span>
              </h1>
              <ActivityExportButton contentRef={contentRef} />
            </FadeSection>
          </header>

          {/* ── Motivation ──────────────────────────── */}
          <ActivityMotivation
            attendance={attendance}
            grades={grades}
            participation={participation}
            hasInitiallyLoaded={hasInitiallyLoaded}
          />

          {/* ── Period Selector ──────────────────────── */}
          <FadeSection delay="100ms">
            <div
              className="activity-period-selector mb-6 inline-flex items-center gap-1"
              role="radiogroup"
              aria-label={t("activity:a11y.periodSelector")}
            >
              {periodOptions.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  role="radio"
                  aria-checked={period === option.value}
                  onClick={() => setPeriod(option.value)}
                  className={cn(
                    "relative min-h-[44px] rounded-full border-0 px-4 py-1.5 text-sm font-bold transition-colors duration-rapid",
                    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand",
                    period === option.value
                      ? "text-[var(--text-inverse)]"
                      : "bg-transparent text-text-primary hover:text-[var(--activity-present-accent)]"
                  )}
                >
                  {period === option.value && (
                    <motion.span
                      layoutId="activity-period-indicator"
                      className="absolute inset-0 rounded-full bg-[var(--activity-present-accent)]"
                      style={{ boxShadow: "0 2px 8px color-mix(in srgb, var(--activity-present-accent) 30%, transparent)" } as CSSProperties}
                      transition={{
                        type: "spring",
                        stiffness: 400,
                        damping: 30,
                      }}
                    />
                  )}
                  <span className="relative z-base">{option.label}</span>
                </button>
              ))}
            </div>
          </FadeSection>

          {/* ── Stat Cards ──────────────────────────── */}
          <section aria-label={t("activity:title")} className="mb-8 md:mb-10">
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 md:gap-6">
              <div className="activity-card-container activity-stagger-item" style={{ "--stagger-index": 0 } as CSSProperties}>
                <AttendanceCard
                  attendance={attendance}
                  hasInitiallyLoaded={hasInitiallyLoaded}
                  reduceMotion={reduce}
                  ringSize={ringSize}
                />
              </div>
              <div className="activity-card-container activity-stagger-item" style={{ "--stagger-index": 1 } as CSSProperties}>
                <GradesCard
                  grades={grades}
                  hasInitiallyLoaded={hasInitiallyLoaded}
                  ringSize={ringSize}
                />
              </div>
              <div className="activity-card-container activity-stagger-item" style={{ "--stagger-index": 2 } as CSSProperties}>
                <ParticipationCard
                  participation={participation}
                  hasInitiallyLoaded={hasInitiallyLoaded}
                  separator={separator}
                  ringSize={ringSize}
                />
              </div>
            </div>
          </section>

          {/* ── Charts ──────────────────────────────── */}
          {hasInitiallyLoaded && (
            <FadeSection delay="140ms">
              <section aria-label={t("activity:charts.title")} className="mb-8 md:mb-10">
                <h2 className="mb-4 text-lg font-extrabold text-text-primary">
                  {t("activity:charts.title")}
                </h2>
                <div className="grid grid-cols-1 gap-4 md:grid-cols-2 md:gap-6">
                  <div className="activity-stagger-item" style={{ "--stagger-index": 3 } as CSSProperties}>
                    <ActivityTrendChart
                      data={attendanceTrendData}
                      colorVar="var(--activity-present-accent)"
                      ariaLabel={t("activity:a11y.attendanceTrend")}
                      formatDate={formatDate}
                    />
                  </div>
                  <div className="activity-stagger-item" style={{ "--stagger-index": 4 } as CSSProperties}>
                    <ActivityBarChart
                      data={gradesBySubject}
                      colorVar="var(--activity-grade-accent)"
                      ariaLabel={t("activity:a11y.gradesBySubject")}
                    />
                  </div>
                </div>
              </section>
            </FadeSection>
          )}

          {/* ── Heatmap Calendar ────────────────────── */}
          {hasInitiallyLoaded && (
            <FadeSection delay="180ms">
              <section className="mb-8 md:mb-10">
                <ActivityHeatmap
                  data={heatmapData}
                  period={period}
                  ariaLabel={t("activity:a11y.heatmapCalendar")}
                />
              </section>
            </FadeSection>
          )}

          {/* ── Comparative Analytics ────────────────── */}
          {hasInitiallyLoaded && comparative.hasData && (
            <FadeSection delay="200ms">
              <section aria-label={t("activity:comparative.title")} className="mb-8 md:mb-10">
                <h2 className="mb-4 text-lg font-extrabold text-text-primary">
                  {t("activity:comparative.title")}
                </h2>
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-3 md:gap-6">
                  <div className="activity-stagger-item" style={{ "--stagger-index": 5 } as CSSProperties}>
                    <ActivityComparativeCard
                      label={t("activity:comparative.attendanceLabel")}
                      current={comparative.attendance.current}
                      previous={comparative.attendance.previous}
                      delta={comparative.attendance.delta}
                      format="percent"
                      colorVar="var(--activity-present-accent)"
                    />
                  </div>
                  <div className="activity-stagger-item" style={{ "--stagger-index": 6 } as CSSProperties}>
                    <ActivityComparativeCard
                      label={t("activity:comparative.gradesLabel")}
                      current={comparative.grades.current}
                      previous={comparative.grades.previous}
                      delta={comparative.grades.delta}
                      format="decimal"
                      colorVar="var(--activity-grade-accent)"
                    />
                  </div>
                  <div className="activity-stagger-item" style={{ "--stagger-index": 7 } as CSSProperties}>
                    <ActivityComparativeCard
                      label={t("activity:comparative.participationLabel")}
                      current={comparative.participation.current}
                      previous={comparative.participation.previous}
                      delta={comparative.participation.delta}
                      format="count"
                      colorVar="var(--activity-participation-accent)"
                    />
                  </div>
                </div>
              </section>
            </FadeSection>
          )}

          {/* ── Timeline ────────────────────────────── */}
          <ActivityTimeline
            attendance={attendance}
            grades={grades}
            participation={participation}
            hasInitiallyLoaded={hasInitiallyLoaded}
            attendanceStatusLabel={attendanceStatusLabel}
            formatDate={formatDate}
          />
        </div>
      </div>
    </PageLayout>
  )
}
