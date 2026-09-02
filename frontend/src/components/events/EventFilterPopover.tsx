import { useState } from "react"
import { useTranslation } from "react-i18next"
import {
  useFloating,
  useClick,
  useDismiss,
  useRole,
  useInteractions,
  offset,
  flip,
  shift,
  autoUpdate,
  FloatingFocusManager,
  type Placement,
} from "@floating-ui/react"

import { Button } from "@/components/ui"
import { TextField } from "@/components/ui/TextField"
import { cn } from "@/utils/cn"
import type { EventDateRange } from "@/features/events/types"

const DATE_OPTIONS: { value: EventDateRange; labelKey: string }[] = [
  { value: "", labelKey: "events:filters.allDates" },
  { value: "today", labelKey: "events:filters.today" },
  { value: "week", labelKey: "events:filters.thisWeek" },
  { value: "month", labelKey: "events:filters.thisMonth" },
]

export const DEFAULT_EVENT_FILTER_PLACEMENT: Placement = "bottom-end"

type EventFilterPopoverProps = {
  dateRange: EventDateRange
  onDateRangeChange: (value: EventDateRange) => void
  location: string
  onLocationChange: (value: string) => void
  placement?: Placement
}

/**
 * Headless hook that manages filter popover state, positioning, and accessibility.
 * Returns `referenceProps` (spread onto the trigger button) and `popoverNode` (render in tree).
 */
export function useEventFilterPopover({
  dateRange,
  onDateRangeChange,
  location,
  onLocationChange,
  placement = DEFAULT_EVENT_FILTER_PLACEMENT,
}: EventFilterPopoverProps) {
  const { t } = useTranslation(["events", "common"])
  const [isOpen, setIsOpen] = useState(false)

  const normalizedLocation = typeof location === "string" ? location.trim() : ""
  const filtersActive = Boolean(dateRange || normalizedLocation)

  const {
    refs: { setReference, setFloating },
    floatingStyles,
    context,
  } = useFloating({
    open: isOpen,
    onOpenChange: setIsOpen,
    placement,
    middleware: [offset(8), flip(), shift({ padding: 8 })],
    whileElementsMounted: autoUpdate,
  })

  const click = useClick(context)
  const dismiss = useDismiss(context, { outsidePressEvent: "mousedown" })
  const role = useRole(context, { role: "dialog" })

  const { getReferenceProps, getFloatingProps } = useInteractions([click, dismiss, role])

  const handleReset = () => {
    onDateRangeChange("")
    onLocationChange("")
  }

  return {
    isOpen,
    filtersActive,
    referenceProps: { ref: setReference, ...getReferenceProps() },
    popoverNode: isOpen ? (
      <FloatingFocusManager context={context} modal={false}>
        <div
          ref={setFloating}
          style={floatingStyles}
          {...getFloatingProps()}
          className="z-modal min-w-64 rounded-xl border border-glass-border bg-(--bg-surface)/(--opacity-heavy) p-4 shadow-glass backdrop-blur-xl"
        >
          <div className="space-y-4">
            {/* Date range quick buttons */}
            <fieldset>
              <legend className="text-xs font-semibold text-(--text-secondary) mb-2">
                {t("events:filters.dateRange")}
              </legend>
              <div className="flex flex-wrap gap-1.5">
                {DATE_OPTIONS.map((opt) => (
                  <button
                    key={opt.value}
                    type="button"
                    onClick={() => onDateRangeChange(opt.value)}
                    className={cn(
                      "rounded-full px-3 py-1.5 text-xs font-semibold transition-colors duration-fast focus-visible:ring-2 focus-visible:ring-brand",
                      dateRange === opt.value
                        ? "bg-brand text-[var(--text-inverse)] shadow-sm"
                        : "matte-chip text-(--text-secondary) hover:text-text-primary"
                    )}
                  >
                    {t(opt.labelKey)}
                  </button>
                ))}
              </div>
            </fieldset>

            {/* Location filter */}
            <TextField
              id="events-filter-location"
              label={t("events:filters.location")}
              value={location}
              onChange={(event) => onLocationChange(event.target.value)}
              fullWidth
            />

            <div className="flex justify-end gap-2">
              <Button variant="ghost" size="sm" onClick={handleReset}>
                {t("common:buttons.reset")}
              </Button>
              <Button variant="solid" size="sm" onClick={() => setIsOpen(false)}>
                {t("common:buttons.done")}
              </Button>
            </div>
          </div>
        </div>
      </FloatingFocusManager>
    ) : null,
  }
}
