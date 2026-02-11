import React from "react"
import { useTranslation } from "react-i18next"
import { motion } from "framer-motion"
import { cn } from "@/utils/cn"
import { type LessonParity } from "./scheduleUtils"

interface WeekSelectorProps {
  currentParity: "odd" | "even"
  setCurrentParity: (parity: "odd" | "even") => void
}

export const WeekSelector = ({ currentParity, setCurrentParity }: WeekSelectorProps) => {
  const { t } = useTranslation(["schedule"])

  return (
    <div className="flex flex-wrap items-center gap-5">
      <span className="text-sm font-semibold tracking-wide text-(--text-secondary)/80">
        {t("schedule:week.label")}
      </span>
      <div className="relative inline-flex items-center gap-1 rounded-xl border border-glass-border bg-glass-subtle p-1 shadow-sm md:shadow-glass">
        <button
          onClick={() => setCurrentParity("odd")}
          className={cn(
            "relative min-w-[72px] rounded-lg px-3 py-1.5 text-sm font-semibold transition-colors duration-150",
            currentParity === "odd"
              ? "text-white"
              : "text-(--text-secondary)/80 hover:bg-surface-elevated/40 dark:text-(--text-secondary)/70 dark:hover:bg-surface-elevated/20"
          )}
        >
          {currentParity === "odd" && (
            <motion.span
              layoutId="schedule-week-indicator"
              className="absolute inset-0 rounded-lg bg-brand shadow-glow-primary"
              transition={{ type: "spring", stiffness: 400, damping: 30 }}
            />
          )}
          <span className="relative z-(--z-surface)">{t("schedule:week.odd")}</span>
        </button>
        <button
          onClick={() => setCurrentParity("even")}
          className={cn(
            "relative min-w-[72px] rounded-lg px-3 py-1.5 text-sm font-semibold transition-colors duration-150",
            currentParity === "even"
              ? "text-white"
              : "text-(--text-secondary)/80 hover:bg-surface-elevated/40 dark:text-(--text-secondary)/70 dark:hover:bg-surface-elevated/20"
          )}
        >
          {currentParity === "even" && (
            <motion.span
              layoutId="schedule-week-indicator"
              className="absolute inset-0 rounded-lg bg-brand shadow-glass"
              transition={{ type: "spring", stiffness: 400, damping: 30 }}
            />
          )}
          <span className="relative z-(--z-surface)">{t("schedule:week.even")}</span>
        </button>
      </div>
    </div>
  )
}
