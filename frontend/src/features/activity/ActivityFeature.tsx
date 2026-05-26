import { useRef, type CSSProperties } from "react"
import { Activity as TimelineIcon } from "lucide-react"
import { cn } from "@/utils/cn"
import useMediaQuery from "@/hooks/useMediaQuery"
import { breakpoints } from "@/theme/tokens"
import FadeSection from "@/components/motion/FadeSection"
import useActivityData from "@/hooks/useActivityData"
import { useActivityComparative } from "@/hooks/useActivityComparative"
import { useSlidingIndicator } from "@/hooks/ui/useSlidingIndicator"

import { ActivityBackdrop } from "./components/ActivityBackdrop"
import { ActivityMotivation } from "./components/ActivityMotivation"
import { AttendanceCard } from "./components/AttendanceCard"
import { GradesCard } from "./components/GradesCard"
import { ParticipationCard } from "./components/ParticipationCard"
import { ActivityTrendChart } from "./components/ActivityTrendChart"
import { ActivityBarChart } from "./components/ActivityBarChart"
import { ActivityHeatmap } from "./components/ActivityHeatmap"
import { ActivityComparativeCard } from "./components/ActivityComparativeCard"
import { ActivityExportButton } from "./components/ActivityExportButton"
import { ActivityTimeline } from "./components/ActivityTimeline"

/**
 * ActivityFeature — Wave 112 SW2 orchestrator.
 *
 * Migrated from `pages/Activity.tsx` (267 lines) into `features/activity/` to
 * match the News/Events pattern. Behaviour is byte-equivalent — the only
 * changes are import paths (relative within the feature) and the removal of
 * <PageLayout> + SEO wrapping (now lives in `pages/Activity.tsx` to keep the
 * feature reusable in non-page contexts like Storybook).
 *
 * Data layer (`useActivityData` + `useActivityComparative`) is internally
 * backed by TanStack Query (`useActivitySummaryQuery`) — see
 * `@/api/hooks/activity` for the queryKey factory and cache behaviour.
 */
export function ActivityFeature() {
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

  const reduce = useMediaQuery("(prefers-reduced-motion: reduce)")
  const isSm = useMediaQuery(`(max-width: ${breakpoints.small})`)
  const isMd = useMediaQuery(`(max-width: ${breakpoints.mobile})`)
  const isNarrow = useMediaQuery(`(max-width: ${breakpoints.dashboard})`)
  const isXl = useMediaQuery(`(min-width: ${breakpoints.desktop})`)
  const isLgCompact = useMediaQuery("(min-width: 1024px) and (max-width: 1199px)")
  const ringSize = isSm ? 68 : isMd ? 84 : isLgCompact ? 72 : isXl ? 104 : 96

  const contentRef = useRef<HTMLDivElement>(null)

  // Wave 124 SW1 — replaces framer-motion layoutId="activity-period-indicator"
  // (requires domMax). Single absolutely-positioned indicator slides between
  // active period buttons via CSS transform transition. ResizeObserver-driven
  // re-measurement handles i18n length changes.
  const periodSelectorRef = useRef<HTMLDivElement>(null)
  const periodRect = useSlidingIndicator(periodSelectorRef, period)

  return (
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

        {/* ── Period Selector ────────────────────────
            Wave 124 SW1 — refactored from framer-motion layoutId to CSS
            sliding indicator. Same UX, no domMax features. */}
        <FadeSection delay="100ms">
          <div
            ref={periodSelectorRef}
            className="activity-period-selector mb-6 relative inline-flex items-center gap-1"
            role="radiogroup"
            aria-label={t("activity:a11y.periodSelector")}
          >
            {periodRect && (
              <span
                aria-hidden="true"
                className="absolute rounded-full bg-[var(--activity-present-accent)] z-negative"
                style={{
                  transform: `translate3d(${periodRect.left}px, ${periodRect.top}px, 0)`,
                  width: periodRect.width,
                  height: periodRect.height,
                  boxShadow: "var(--activity-period-indicator-shadow)",
                  transition: reduce
                    ? "none"
                    : "transform 280ms cubic-bezier(0.34, 1.3, 0.64, 1), width 280ms cubic-bezier(0.34, 1.3, 0.64, 1), height 280ms cubic-bezier(0.34, 1.3, 0.64, 1)",
                }}
              />
            )}
            {periodOptions.map((option) => (
              <button
                key={option.value}
                data-tab-key={option.value}
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
                <span className="relative z-base">{option.label}</span>
              </button>
            ))}
          </div>
        </FadeSection>

        {/* ── Stat Cards ──────────────────────────── */}
        <section aria-label={t("activity:title")} className="mb-8 md:mb-10">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 md:gap-6">
            <div
              className="activity-card-container activity-stagger-item"
              style={{ "--stagger-index": 0 } as CSSProperties}
            >
              <AttendanceCard
                attendance={attendance}
                hasInitiallyLoaded={hasInitiallyLoaded}
                ringSize={ringSize}
              />
            </div>
            <div
              className="activity-card-container activity-stagger-item"
              style={{ "--stagger-index": 1 } as CSSProperties}
            >
              <GradesCard
                grades={grades}
                hasInitiallyLoaded={hasInitiallyLoaded}
                ringSize={ringSize}
              />
            </div>
            <div
              className="activity-card-container activity-stagger-item"
              style={{ "--stagger-index": 2 } as CSSProperties}
            >
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
                <div
                  className="activity-stagger-item"
                  style={{ "--stagger-index": 3 } as CSSProperties}
                >
                  <ActivityTrendChart
                    data={attendanceTrendData}
                    colorVar="var(--activity-present-accent)"
                    ariaLabel={t("activity:a11y.attendanceTrend")}
                    formatDate={formatDate}
                  />
                </div>
                <div
                  className="activity-stagger-item"
                  style={{ "--stagger-index": 4 } as CSSProperties}
                >
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
                <div
                  className="activity-stagger-item"
                  style={{ "--stagger-index": 5 } as CSSProperties}
                >
                  <ActivityComparativeCard
                    label={t("activity:comparative.attendanceLabel")}
                    current={comparative.attendance.current}
                    previous={comparative.attendance.previous}
                    delta={comparative.attendance.delta}
                    format="percent"
                    colorVar="var(--activity-present-accent)"
                  />
                </div>
                <div
                  className="activity-stagger-item"
                  style={{ "--stagger-index": 6 } as CSSProperties}
                >
                  <ActivityComparativeCard
                    label={t("activity:comparative.gradesLabel")}
                    current={comparative.grades.current}
                    previous={comparative.grades.previous}
                    delta={comparative.grades.delta}
                    format="decimal"
                    colorVar="var(--activity-grade-accent)"
                  />
                </div>
                <div
                  className="activity-stagger-item"
                  style={{ "--stagger-index": 7 } as CSSProperties}
                >
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
  )
}
