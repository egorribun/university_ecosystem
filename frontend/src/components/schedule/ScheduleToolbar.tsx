import { useTranslation } from "react-i18next"
import { motion } from "framer-motion"
import {
  ChevronLeft,
  ChevronRight,
  RotateCcw,
  Settings2,
  LayoutGrid,
  CalendarDays,
  List,
  Printer,
} from "lucide-react"
import { Button } from "@/components/ui"
import { ExportDropdown } from "@/components/schedule/ExportDropdown"
import { cn } from "@/utils/cn"
import {
  useWeekOffset,
  useViewMode,
  useScheduleUIActions,
} from "@/stores/scheduleUIStore"
import type { ScheduleViewMode } from "@/stores/types"

interface ScheduleToolbarProps {
  onExportIcs?: () => void
  onOpenSettings?: () => void
  isExporting?: boolean
  /** Ref to the grid element for canvas-based export */
  gridRef?: React.RefObject<HTMLElement | null>
}

const VIEW_MODES: { id: ScheduleViewMode; icon: typeof LayoutGrid; labelKey: string }[] = [
  { id: "week", icon: LayoutGrid, labelKey: "schedule:toolbar.week" },
  { id: "day", icon: CalendarDays, labelKey: "schedule:toolbar.day" },
  { id: "list", icon: List, labelKey: "schedule:toolbar.list" },
]

export function ScheduleToolbar({ onExportIcs, onOpenSettings, isExporting, gridRef }: ScheduleToolbarProps) {
  const { t } = useTranslation(["schedule"])
  const weekOffset = useWeekOffset()
  const viewMode = useViewMode()
  const { nextWeek, previousWeek, goToCurrentWeek, setViewMode } = useScheduleUIActions()

  return (
    <div className="flex flex-wrap items-center gap-3">
      {/* ── Week navigation ────────────────────────────── */}
      <div className="flex items-center gap-1 rounded-xl border border-glass-border bg-glass-subtle p-1 shadow-sm">
        <button
          onClick={previousWeek}
          aria-label={t("schedule:toolbar.prevWeek")}
          className="flex h-8 w-8 items-center justify-center rounded-lg text-text-secondary transition-colors hover:bg-surface-elevated/(--opacity-dim) hover:text-text-primary focus-visible:ring-2 focus-visible:ring-brand"
        >
          <ChevronLeft size={16} aria-hidden="true" />
        </button>
        <button
          onClick={goToCurrentWeek}
          className={cn(
            "relative min-w-24 px-3 py-1.5 text-sm font-semibold transition-colors rounded-lg",
            weekOffset === 0
              ? "text-white"
              : "text-text-secondary hover:bg-surface-elevated/(--opacity-dim)"
          )}
        >
          {weekOffset === 0 && (
            <motion.span
              layoutId="schedule-week-nav"
              className="absolute inset-0 rounded-lg bg-brand shadow-glow-primary"
              transition={{ type: "spring", stiffness: 400, damping: 30 }}
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
          className="flex h-8 w-8 items-center justify-center rounded-lg text-text-secondary transition-colors hover:bg-surface-elevated/(--opacity-dim) hover:text-text-primary focus-visible:ring-2 focus-visible:ring-brand"
        >
          <ChevronRight size={16} aria-hidden="true" />
        </button>
        {weekOffset !== 0 && (
          <button
            onClick={goToCurrentWeek}
            aria-label={t("schedule:toolbar.goToToday")}
            className="flex h-8 w-8 items-center justify-center rounded-lg text-brand transition-colors hover:bg-brand/(--opacity-subtle) focus-visible:ring-2 focus-visible:ring-brand"
          >
            <RotateCcw size={14} aria-hidden="true" />
          </button>
        )}
      </div>

      {/* ── View mode segment control ──────────────────── */}
      <div className="sched-segment" role="radiogroup" aria-label={t("schedule:toolbar.viewMode")}>
        {VIEW_MODES.map(({ id, icon: Icon, labelKey }) => (
          <button
            key={id}
            role="radio"
            aria-checked={viewMode === id}
            data-active={viewMode === id}
            className="sched-segment-btn"
            onClick={() => setViewMode(id)}
          >
            {viewMode === id && (
              <motion.span
                layoutId="schedule-view-mode"
                className="absolute inset-0 rounded-lg bg-brand shadow-glow-primary"
                transition={{ type: "spring", stiffness: 400, damping: 30 }}
              />
            )}
            <span className="relative z-surface flex items-center gap-1.5">
              <Icon size={14} aria-hidden="true" />
              <span className="hidden sm:inline">{t(labelKey)}</span>
            </span>
          </button>
        ))}
      </div>

      {/* ── Action buttons ─────────────────────────────── */}
      <div className="ml-auto flex items-center gap-2">
        {/* Export dropdown (Wave 66: multi-format) */}
        <ExportDropdown
          onExportIcs={onExportIcs}
          isExporting={isExporting}
          gridRef={gridRef}
        />
        {/* Print button */}
        <Button
          variant="ghost"
          size="sm"
          onClick={() => window.print()}
          aria-label={t("schedule:toolbar.print", { defaultValue: "Print schedule" })}
          className="no-print"
        >
          <Printer size={15} aria-hidden="true" />
        </Button>
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
