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

type EventFilterPopoverProps = {
  type: string
  onTypeChange: (value: string) => void
  location: string
  onLocationChange: (value: string) => void
  placement?: Placement
}

/**
 * Headless hook that manages filter popover state, positioning, and accessibility.
 * Returns `referenceProps` (spread onto the trigger button) and `popoverNode` (render in tree).
 */
export function useEventFilterPopover({
  type,
  onTypeChange,
  location,
  onLocationChange,
  placement = "bottom-end",
}: EventFilterPopoverProps) {
  const { t } = useTranslation(["events", "common"])
  const [isOpen, setIsOpen] = useState(false)

  const filtersActive = Boolean(type?.trim() || location?.trim())

  const { refs, floatingStyles, context } = useFloating({
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
    onTypeChange("")
    onLocationChange("")
  }

  return {
    isOpen,
    filtersActive,
    referenceProps: { ref: refs.setReference, ...getReferenceProps() },
    popoverNode: isOpen ? (
      <FloatingFocusManager context={context} modal={false}>
        <div
          ref={refs.setFloating}
          style={floatingStyles}
          {...getFloatingProps()}
          className="z-modal min-w-64 rounded-md border border-glass-border bg-(--bg-surface)/(--opacity-heavy) p-4 shadow-glass backdrop-blur-xl"
        >
          <div className="space-y-4">
            <TextField
              label={t("events:filters.type")}
              value={type}
              onChange={(event) => onTypeChange(event.target.value)}
              fullWidth
            />
            <TextField
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
