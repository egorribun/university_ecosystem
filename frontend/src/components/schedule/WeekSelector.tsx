import { useTranslation } from "react-i18next"
import { motion, useReducedMotion } from "framer-motion"
import { cn } from "@/utils/cn"

interface WeekSelectorProps {
  currentParity: "odd" | "even"
  setCurrentParity: (parity: "odd" | "even") => void
}

export const WeekSelector = ({ currentParity, setCurrentParity }: WeekSelectorProps) => {
  const { t } = useTranslation(["schedule"])
  const prefersReduced = useReducedMotion()

  // FIX-71-WS: extracted shared className to avoid duplication
  const parityBtnClass = (active: boolean) =>
    cn(
      "relative rounded-lg px-2.5 py-1.5 text-sm font-semibold transition-colors duration-rapid sm:px-3",
      active
        ? "text-[var(--sched-on-accent)]"
        : "text-(--text-secondary)/(--opacity-hover) hover:bg-surface-elevated/(--opacity-dim) dark:text-(--text-secondary)/(--opacity-strong) dark:hover:bg-surface-elevated/(--opacity-dim)"
    )

  const springTransition = prefersReduced ? { duration: 0 } : { type: "spring" as const, stiffness: 400, damping: 30 }

  return (
    <div className="flex items-center gap-2.5">
      <span id="week-parity-label" className="text-sm font-semibold tracking-wide text-(--text-secondary)/(--opacity-hover) hidden sm:inline">
        {t("schedule:week.label")}
      </span>
      {/* FIX-69-05: radiogroup semantics for exclusive selection */}
      <div
        role="radiogroup"
        aria-labelledby="week-parity-label"
        className="relative inline-flex items-center gap-1 rounded-xl border border-glass-border bg-glass-subtle p-1 shadow-sm md:shadow-glass"
      >
        <button
          type="button"
          id="week-parity-odd"
          role="radio"
          onClick={() => setCurrentParity("odd")}
          aria-checked={currentParity === "odd"}
          aria-label={t("schedule:week.odd")}
          className={parityBtnClass(currentParity === "odd")}
        >
          {currentParity === "odd" && (
            <motion.span
              layoutId="schedule-week-indicator"
              className="absolute inset-0 rounded-lg bg-brand shadow-glow-primary"
              transition={springTransition}
            />
          )}
          <span className="relative z-surface">{t("schedule:week.odd")}</span>
        </button>
        <button
          type="button"
          id="week-parity-even"
          role="radio"
          onClick={() => setCurrentParity("even")}
          aria-checked={currentParity === "even"}
          aria-label={t("schedule:week.even")}
          className={parityBtnClass(currentParity === "even")}
        >
          {currentParity === "even" && (
            <motion.span
              layoutId="schedule-week-indicator"
              className="absolute inset-0 rounded-lg bg-brand shadow-glow-primary"
              transition={springTransition}
            />
          )}
          <span className="relative z-surface">{t("schedule:week.even")}</span>
        </button>
      </div>
    </div>
  )
}
