import { useTranslation } from "react-i18next"
import { motion, useReducedMotion } from "framer-motion"
import {
  ChevronLeft,
  ChevronRight,
  RotateCcw,
  Settings2,
} from "lucide-react"
import { Button } from "@/components/ui"
import { ExportDropdown } from "@/components/schedule/ExportDropdown"
import { cn } from "@/utils/cn"
import {
  useWeekOffset,
  useScheduleUIActions,
} from "@/stores/scheduleUIStore"

interface ScheduleToolbarProps {
  onOpenSettings?: () => void
  isExporting?: boolean
  /** Ref to the grid element for canvas-based export */
  gridRef?: React.RefObject<HTMLElement | null>
  /** Slot rendered between week nav and actions (e.g. WeekSelector) */
  children?: React.ReactNode
}

export function ScheduleToolbar({ onOpenSettings, isExporting, gridRef, children }: ScheduleToolbarProps) {
  const { t } = useTranslation(["schedule"])
  const weekOffset = useWeekOffset()
  const { nextWeek, previousWeek, goToCurrentWeek } = useScheduleUIActions()
  const prefersReduced = useReducedMotion()

  return (
    <div className="flex flex-wrap items-center gap-2 sm:gap-3">
      {/* ── Week navigation ────────────────────────────── */}
      <div className="flex items-center gap-1 rounded-xl border border-glass-border bg-glass-subtle p-1 shadow-sm">
        <button
          onClick={previousWeek}
          aria-label={t("schedule:toolbar.prevWeek")}
          className="flex h-9 w-9 min-h-[44px] min-w-[44px] items-center justify-center rounded-lg text-text-secondary transition-colors hover:bg-surface-elevated/(--opacity-dim) hover:text-text-primary focus-visible:ring-2 focus-visible:ring-brand"
        >
          <ChevronLeft size={16} aria-hidden="true" />
        </button>
        <button
          onClick={goToCurrentWeek}
          className={cn(
            "relative min-w-24 px-3 py-1.5 text-sm font-semibold transition-colors rounded-lg",
            weekOffset === 0
              ? "text-[var(--sched-on-accent)]"
              : "text-text-secondary hover:bg-surface-elevated/(--opacity-dim)"
          )}
        >
          {weekOffset === 0 && (
            <motion.span
              layoutId="schedule-week-nav"
              className="absolute inset-0 rounded-lg bg-brand shadow-glow-primary"
              transition={prefersReduced ? { duration: 0 } : { type: "spring", stiffness: 400, damping: 30 }}
            />
          )}
          <span className="relative z-surface">
            {weekOffset === 0
              ? t("schedule:toolbar.thisWeek")
              : weekOffset > 0
                ? t("schedule:toolbar.weekOffset", { offset: `+${weekOffset}` })
                : t("schedule:toolbar.weekOffset", { offset: String(weekOffset) })}
          </span>
        </button>
        <button
          onClick={nextWeek}
          aria-label={t("schedule:toolbar.nextWeek")}
          className="flex h-9 w-9 min-h-[44px] min-w-[44px] items-center justify-center rounded-lg text-text-secondary transition-colors hover:bg-surface-elevated/(--opacity-dim) hover:text-text-primary focus-visible:ring-2 focus-visible:ring-brand"
        >
          <ChevronRight size={16} aria-hidden="true" />
        </button>
        {weekOffset !== 0 && (
          <button
            onClick={goToCurrentWeek}
            aria-label={t("schedule:toolbar.goToToday")}
            className="flex h-9 w-9 min-h-[44px] min-w-[44px] items-center justify-center rounded-lg text-brand transition-colors hover:bg-brand/(--opacity-subtle) focus-visible:ring-2 focus-visible:ring-brand"
          >
            <RotateCcw size={14} aria-hidden="true" />
          </button>
        )}
      </div>

      {/* ── Slot: parity selector or other controls ──── */}
      {children}

      {/* ── Action buttons — pushed to far right ──────── */}
      <div className="ml-auto flex items-center gap-2">
        <ExportDropdown
          isExporting={isExporting}
          gridRef={gridRef}
        />
        {onOpenSettings && (
          <Button
            variant="ghost"
            size="sm"
            onClick={onOpenSettings}
            aria-label={t("schedule:toolbar.settings")}
          >
            <Settings2 size={15} aria-hidden="true" />
          </Button>
        )}
      </div>
    </div>
  )
}
