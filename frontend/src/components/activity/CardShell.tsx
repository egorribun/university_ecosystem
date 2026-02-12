import { motion } from "framer-motion"
import { cn } from "@/utils/cn"

const TONE_CLASSES = {
  neutral: "bg-glass-elevated",
  success:
    "bg-linear-to-b from-success-bg/(--opacity-soft) to-success-bg/(--opacity-medium) dark:from-success-bg/(--opacity-dim) dark:to-success-bg/(--opacity-medium)",
  info: "bg-linear-to-b from-brand/(--opacity-subtle) to-brand/(--opacity-dim) dark:from-brand/(--opacity-dim) dark:to-brand/(--opacity-soft)",
  warning:
    "bg-linear-to-b from-warning-bg/(--opacity-soft) to-warning-bg/(--opacity-medium) dark:from-warning-bg/(--opacity-dim) dark:to-warning-bg/(--opacity-medium)",
} as const

export type CardShellTone = keyof typeof TONE_CLASSES

export default function CardShell({
  tone = "neutral",
  onClick,
  children,
  hasInitiallyLoaded,
  reduceMotion,
}: {
  tone?: CardShellTone
  onClick?: () => void
  children: React.ReactNode
  hasInitiallyLoaded: boolean
  reduceMotion: boolean
}) {
  return (
    <motion.div
      initial={
        hasInitiallyLoaded ? false : { y: reduceMotion ? 0 : 14, opacity: reduceMotion ? 1 : 0 }
      }
      animate={{ y: 0, opacity: 1 }}
      transition={{ type: "spring", stiffness: 260, damping: 32, mass: 1 }}
      className={cn(
        "relative flex h-full flex-col overflow-hidden rounded-2xl border border-glass-border-subtle backdrop-blur-xl [-webkit-backdrop-filter:blur(12px)]",
        TONE_CLASSES[tone],
        "shadow-premium",
        "transition-all duration-180",
        reduceMotion ? "" : "hover:-translate-y-0.5 hover:shadow-premium",
        "active:translate-y-0",
        onClick &&
          "cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2"
      )}
      style={
        reduceMotion ? undefined : { willChange: "transform, opacity", transform: "translateZ(0)" }
      }
    >
      <button
        onClick={onClick}
        className={cn(
          "flex h-full flex-col items-stretch rounded-2xl p-4 text-left md:p-6 xl:p-8",
          onClick ? "" : "pointer-events-none"
        )}
      >
        <div className="flex flex-1 flex-col gap-2">{children}</div>
      </button>
    </motion.div>
  )
}
