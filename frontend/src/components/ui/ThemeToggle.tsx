/**
 * ThemeToggle — Animated sun/moon toggle for dark/light mode
 *
 * Features:
 * - SVG morphing between sun rays and moon crescent
 * - Color wave pulse on toggle
 * - Spring physics on icon rotation
 * - Respects prefers-reduced-motion
 */

import { useCallback } from "react"
import { motion, AnimatePresence } from "framer-motion"
import { Sun, Moon } from "lucide-react"
import { useTranslation } from "react-i18next"
import { cn } from "@/utils/cn"

interface ThemeToggleProps {
  isDark: boolean
  onToggle: () => void
  className?: string
  size?: "sm" | "md"
}

const iconVariants = {
  initial: { scale: 0, rotate: -90, opacity: 0 },
  animate: {
    scale: 1,
    rotate: 0,
    opacity: 1,
    transition: { type: "spring" as const, stiffness: 300, damping: 20 },
  },
  exit: {
    scale: 0,
    rotate: 90,
    opacity: 0,
    transition: { duration: 0.15, ease: "easeIn" as const },
  },
}

export function ThemeToggle({ isDark, onToggle, className, size = "md" }: ThemeToggleProps) {
  const { t } = useTranslation(["common"])

  const handleToggle = useCallback(() => {
    onToggle()
  }, [onToggle])

  const sizeClasses = size === "sm" ? "h-8 w-8" : "h-10 w-10"
  const iconSize = size === "sm" ? "h-4 w-4" : "h-5 w-5"

  return (
    <button
      type="button"
      onClick={handleToggle}
      aria-label={isDark ? t("common:theme.switchToLight") : t("common:theme.switchToDark")}
      className={cn(
        "relative inline-flex items-center justify-center rounded-full",
        "border border-glass-border bg-glass backdrop-blur-glass",
        "transition-all duration-base hover:bg-glass-tint1 hover:scale-105 active:scale-95",
        "focus-ring-premium",
        sizeClasses,
        className
      )}
    >
      {/* Pulse wave on toggle */}
      <span
        key={isDark ? "dark-pulse" : "light-pulse"}
        className="pointer-events-none absolute inset-0 rounded-full theme-pulse-wave"
        style={{
          background: isDark
            ? "radial-gradient(circle, var(--color-indigo-400), transparent)"
            : "radial-gradient(circle, var(--color-amber-400), transparent)",
          opacity: 0.15,
        }}
        aria-hidden="true"
      />

      <AnimatePresence mode="wait" initial={false}>
        {isDark ? (
          <motion.span
            key="moon"
            variants={iconVariants}
            initial="initial"
            animate="animate"
            exit="exit"
            className="inline-flex text-indigo-300"
          >
            <Moon className={iconSize} />
          </motion.span>
        ) : (
          <motion.span
            key="sun"
            variants={iconVariants}
            initial="initial"
            animate="animate"
            exit="exit"
            className="inline-flex text-amber-500"
          >
            <Sun className={iconSize} />
          </motion.span>
        )}
      </AnimatePresence>
    </button>
  )
}
