import { PageLayout } from "@/components/layout/PageLayout"
import { type CSSProperties } from "react"
import { motion, useReducedMotion } from "framer-motion"
import { Activity as TimelineIcon } from "lucide-react"
import { cn } from "@/utils/cn"
import useMediaQuery from "@/hooks/useMediaQuery"
import { breakpoints } from "@/theme/tokens"
import FadeSection from "@/components/motion/FadeSection"
import useActivityData from "@/hooks/useActivityData"
import { EASE_OUT_EXPO } from "@/components/activity/activityTypes"

import { AttendanceCard } from "@/components/activity/AttendanceCard"
import { GradesCard } from "@/components/activity/GradesCard"
import { ParticipationCard } from "@/components/activity/ParticipationCard"
import { RecentActivityGrid } from "@/components/activity/RecentActivityGrid"
import { ActivityDetailDialog } from "@/components/activity/ActivityDetailDialog"

const fadeDelayStyle = (value: string): CSSProperties =>
  ({ "--fade-delay": value }) as CSSProperties

export default function Activity() {
  const {
    t,
    period,
    setPeriod,
    attendance,
    grades,
    participation,
    hasInitiallyLoaded,
    detail,
    setDetail,
    detailSection,
    periodOptions,
    separator,
    attendanceLessonFallback,
    formatDate,
    attendanceStatusLabel,
    labelByPeriod,
  } = useActivityData()

  const reduce = useReducedMotion() ?? false
  const isSm = useMediaQuery(`(max-width: ${breakpoints.small})`)
  const isMd = useMediaQuery(`(max-width: ${breakpoints.mobile})`)
  const isXl = useMediaQuery(`(min-width: ${breakpoints.desktop})`)
  const ringSize = isSm ? 68 : isMd ? 84 : isXl ? 104 : 96

  // Removed explicit will-change styles in favor of CSS classes or framework defaults
  // to avoid persistent GPU layers. Animation variants trigger composition layers automatically.
  const headerVariants = {
    hidden: { opacity: 0, y: reduce ? 0 : 10 },
    show: {
      opacity: 1,
      y: 0,
      transition: { duration: 0.35, ease: EASE_OUT_EXPO },
    },
  }
  const gridVariants = {
    show: {
      transition: { staggerChildren: reduce ? 0 : 0.06, delayChildren: 0.05 },
    },
  }

  return (
    <PageLayout
      seo={{
        title: t("activity:title"),
        description: t("activity:pageDescription", "Your academic activity dashboard."),
      }}
    >
      <motion.div initial="hidden" animate="show" variants={headerVariants} className="pb-16">
        <header>
          <FadeSection delay="80ms" className="mb-8 flex flex-wrap items-center gap-4 sm:gap-5">
            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-brand-subtle-bg text-brand shadow-glass transition-transform duration-fast hover:scale-105 backdrop-blur-sm">
              <TimelineIcon className="text-3xl" />
            </div>
            <h1 className="text-page-title font-bold tracking-tight text-text-primary">
              {t("activity:title")}
            </h1>
          </FadeSection>
        </header>
        <section aria-label={t("activity:title")}>
          <motion.div
            data-fade
            initial={{ opacity: 0, y: reduce ? 0 : 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: reduce ? 0 : 0.35 }}
            style={{
              ...fadeDelayStyle("140ms"),
            }}
            className="mb-6 inline-flex items-center gap-1 rounded-full border border-glass-border bg-(--bg-surface)/(--opacity-medium) p-1 shadow-premium backdrop-blur-xl [-webkit-backdrop-filter:blur(var(--blur-md))] dark:border-glass-border dark:bg-page/(--opacity-medium) dark:shadow-premium"
          >
            {periodOptions.map((option) => (
              <button
                key={option.value}
                onClick={() => setPeriod(option.value)}
                className={cn(
                  "relative rounded-full border-0 px-4 py-1.5 text-sm font-bold transition-colors duration-rapid",
                  period === option.value
                    ? "text-white"
                    : "bg-transparent text-text-primary hover:bg-brand-subtle-bg hover:text-brand"
                )}
              >
                {period === option.value && (
                  <motion.span
                    layoutId="activity-period-indicator"
                    className="absolute inset-0 rounded-full bg-brand shadow-glass"
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
          </motion.div>

          <motion.div
            variants={gridVariants}
            initial="hidden"
            animate="show"
            className="mb-4 grid grid-cols-1 gap-4 sm:grid-cols-2 md:mb-6 md:grid-cols-3 md:gap-6"
          >
            <AttendanceCard
              attendance={attendance}
              hasInitiallyLoaded={hasInitiallyLoaded}
              reduceMotion={reduce}
              onClick={() => setDetail("attendance")}
              ringSize={ringSize}
            />
            <GradesCard
              grades={grades}
              hasInitiallyLoaded={hasInitiallyLoaded}
              reduceMotion={reduce}
              onClick={() => setDetail("grades")}
            />
            <ParticipationCard
              participation={participation}
              hasInitiallyLoaded={hasInitiallyLoaded}
              reduceMotion={reduce}
              onClick={() => setDetail("participation")}
              separator={separator}
            />
          </motion.div>

          <div className="my-4 border-t border-glass-border-subtle md:my-6" />

          <motion.div variants={gridVariants} initial="hidden" animate="show">
            <RecentActivityGrid
              attendance={attendance}
              grades={grades}
              participation={participation}
              hasInitiallyLoaded={hasInitiallyLoaded}
              reduceMotion={reduce}
              onDetailClick={setDetail}
              separator={separator}
              attendanceLessonFallback={attendanceLessonFallback}
              attendanceStatusLabel={attendanceStatusLabel}
              formatDate={formatDate}
            />
          </motion.div>
        </section>
      </motion.div>
      <ActivityDetailDialog
        detail={detail}
        onClose={() => setDetail("")}
        detailSection={detailSection}
        attendance={attendance}
        grades={grades}
        participation={participation}
        labelByPeriod={labelByPeriod}
        period={period}
        attendanceStatusLabel={attendanceStatusLabel}
        formatDate={formatDate}
        separator={separator}
      />
    </PageLayout>
  )
}
