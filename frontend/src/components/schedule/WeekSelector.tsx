import { useTranslation } from "react-i18next"
import { motion } from "framer-motion"
import { cn } from "@/utils/cn"

interface WeekSelectorProps {
  currentParity: "odd" | "even"
  setCurrentParity: (parity: "odd" | "even") => void
}

export const WeekSelector = ({ currentParity, setCurrentParity }: WeekSelectorProps) => {
  const { t } = useTranslation(["schedule"])

  return (
    <div className="flex flex-wrap items-center gap-5">
      <span className="text-sm font-semibold tracking-wide text-(--text-secondary)/(--opacity-hover)">
        {t("schedule:week.label")}
      </span>
      <div className="relative inline-flex items-center gap-1 rounded-xl border border-glass-border bg-glass-subtle p-1 shadow-sm md:shadow-glass">
        <button
          id="week-parity-odd"
          onClick={() => setCurrentParity("odd")}
          aria-pressed={currentParity === "odd"}
          aria-label={t("schedule:week.odd")}
          className={cn(
            "relative min-w-18 rounded-lg px-3 py-1.5 text-sm font-semibold transition-colors duration-rapid",
            currentParity === "odd"
              ? "text-white"
              : "text-(--text-secondary)/(--opacity-hover) hover:bg-surface-elevated/(--opacity-dim) dark:text-(--text-secondary)/(--opacity-strong) dark:hover:bg-surface-elevated/(--opacity-dim)"
          )}
        >
          {currentParity === "odd" && (
            <motion.span
              layoutId="schedule-week-indicator"
              className="absolute inset-0 rounded-lg bg-brand shadow-glow-primary"
              transition={{ type: "spring", stiffness: 400, damping: 30 }}
            />
          )}
          <span className="relative z-surface">{t("schedule:week.odd")}</span>
        </button>
        <button
          id="week-parity-even"
          onClick={() => setCurrentParity("even")}
          aria-pressed={currentParity === "even"}
          aria-label={t("schedule:week.even")}
          className={cn(
            "relative min-w-18 rounded-lg px-3 py-1.5 text-sm font-semibold transition-colors duration-rapid",
            currentParity === "even"
              ? "text-white"
              : "text-(--text-secondary)/(--opacity-hover) hover:bg-surface-elevated/(--opacity-dim) dark:text-(--text-secondary)/(--opacity-strong) dark:hover:bg-surface-elevated/(--opacity-dim)"
          )}
        >
          {currentParity === "even" && (
            <motion.span
              layoutId="schedule-week-indicator"
              className="absolute inset-0 rounded-lg bg-brand shadow-glow-primary"
              transition={{ type: "spring", stiffness: 400, damping: 30 }}
            />
          )}
          <span className="relative z-surface">{t("schedule:week.even")}</span>
        </button>
      </div>
    </div>
  )
}
