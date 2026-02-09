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
      <span className="text-sm font-semibold tracking-wide text-[color-mix(in_srgb,var(--text-secondary)_78%,var(--primary-main)_22%)] dark:text-[color-mix(in_srgb,var(--text-secondary)_88%,var(--primary-main)_12%)]">
        {t("schedule:week.label")}
      </span>
      <div className="relative inline-flex items-center gap-1 rounded-xl border border-[color-mix(in_srgb,white_12%,var(--primary-main)_88%)] bg-[color-mix(in_srgb,var(--bg-surface)_96%,white_4%)] p-1 shadow-[0_2px_8px_rgba(0,0,0,0.04)] dark:border-[color-mix(in_srgb,white_8%,var(--primary-main)_92%)] dark:bg-[color-mix(in_srgb,var(--bg-surface)_94%,transparent_6%)] dark:shadow-[0_4px_12px_rgba(0,0,0,0.16)]">
        <button
          onClick={() => setCurrentParity("odd")}
          className={cn(
            "relative min-w-[72px] rounded-lg px-3 py-1.5 text-sm font-semibold transition-colors duration-150",
            currentParity === "odd"
              ? "text-white"
              : "text-[color-mix(in_srgb,var(--text-secondary)_75%,var(--primary-main)_25%)] hover:bg-[color-mix(in_srgb,var(--bg-surface)_88%,white_12%)] dark:text-[color-mix(in_srgb,var(--text-secondary)_85%,var(--primary-main)_15%)] dark:hover:bg-[color-mix(in_srgb,var(--bg-surface)_92%,transparent_8%)]"
          )}
        >
          {currentParity === "odd" && (
            <motion.span
              layoutId="schedule-week-indicator"
              className="absolute inset-0 rounded-lg bg-(--primary-main) shadow-[0_2px_8px_rgba(0,0,0,0.08)] dark:shadow-[0_4px_12px_rgba(0,0,0,0.2)]"
              transition={{ type: "spring", stiffness: 400, damping: 30 }}
            />
          )}
          <span className="relative z-10">{t("schedule:week.odd")}</span>
        </button>
        <button
          onClick={() => setCurrentParity("even")}
          className={cn(
            "relative min-w-[72px] rounded-lg px-3 py-1.5 text-sm font-semibold transition-colors duration-150",
            currentParity === "even"
              ? "text-white"
              : "text-[color-mix(in_srgb,var(--text-secondary)_75%,var(--primary-main)_25%)] hover:bg-[color-mix(in_srgb,var(--bg-surface)_88%,white_12%)] dark:text-[color-mix(in_srgb,var(--text-secondary)_85%,var(--primary-main)_15%)] dark:hover:bg-[color-mix(in_srgb,var(--bg-surface)_92%,transparent_8%)]"
          )}
        >
          {currentParity === "even" && (
            <motion.span
              layoutId="schedule-week-indicator"
              className="absolute inset-0 rounded-lg bg-(--primary-main) shadow-[0_2px_8px_rgba(0,0,0,0.08)] dark:shadow-[0_4px_12px_rgba(0,0,0,0.2)]"
              transition={{ type: "spring", stiffness: 400, damping: 30 }}
            />
          )}
          <span className="relative z-10">{t("schedule:week.even")}</span>
        </button>
      </div>
    </div>
  )
}





