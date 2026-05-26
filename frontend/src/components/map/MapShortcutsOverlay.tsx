/**
 * MapShortcutsOverlay.tsx — Keyboard shortcuts help dialog for the campus map.
 *
 * Follows the exact same pattern as ScheduleShortcutsOverlay:
 * AnimatePresence + motion backdrop/dialog, useFocusTrap, useReducedMotion,
 * semantic <dl> with <kbd> elements.
 *
 * Wave 108 — map keyboard shortcuts overlay.
 */

import { useCallback } from "react"
import { useTranslation } from "react-i18next"
import { X as CloseIcon, Keyboard as KeyboardIcon } from "lucide-react"
import { AnimatePresence, m } from "framer-motion"
import useFocusTrap from "@/hooks/useFocusTrap"
import useMediaQuery from "@/hooks/useMediaQuery"

interface MapShortcutsOverlayProps {
  open: boolean
  onClose: () => void
}

// Wave 120 SW4 \u2014 added arrow / zoom / rotate / pitch shortcuts (verified
// working via chrome-devtools-mcp keyboard synthesis on /map). MapLibre's
// built-in KeyboardHandler handles these natively when canvas is focused.
const SHORTCUTS = [
  { keys: ["1", "\u2013", "9"], labelKey: "shortcuts.buildings" },
  { keys: ["\u2191", "\u2193", "\u2190", "\u2192"], labelKey: "shortcuts.pan" },
  { keys: ["+", "\u2212"], labelKey: "shortcuts.zoom" },
  { keys: ["\u21e7+\u2190", "\u21e7+\u2192"], labelKey: "shortcuts.rotate" },
  { keys: ["\u21e7+\u2191", "\u21e7+\u2193"], labelKey: "shortcuts.pitch" },
  { keys: ["F"], labelKey: "shortcuts.fullscreen" },
  { keys: ["/"], labelKey: "shortcuts.search" },
  { keys: ["Esc"], labelKey: "shortcuts.close" },
  { keys: ["?"], labelKey: "shortcuts.help" },
] as const

/**
 * Centered modal overlay listing map keyboard shortcuts.
 *
 * @param open    Whether the overlay is visible
 * @param onClose Callback to dismiss the overlay
 */
export function MapShortcutsOverlay({ open, onClose }: MapShortcutsOverlayProps) {
  const { t } = useTranslation("map")
  // Wave 189 SW3 — migrated from framer-motion's `useReducedMotion()` (jsdom-
  // incompat per W184 SW6 Gotcha) to project's `useMediaQuery` DEFAULT export.
  // Behaviour preserved: hook returns boolean (was `boolean | null`; null was
  // already falsy in the downstream conditional render).
  const prefersReduced = useMediaQuery("(prefers-reduced-motion: reduce)")

  const handleClose = useCallback(() => onClose(), [onClose])

  const dialogRef = useFocusTrap<HTMLDivElement>({
    active: open,
    onDeactivate: handleClose,
  })

  return (
    <AnimatePresence>
      {open && (
        <m.div
          className="fixed inset-0 z-modal flex items-center justify-center p-4"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.2 }}
        >
          {/* Backdrop */}
          <div
            className="absolute inset-0 bg-[var(--map-overlay-bg,rgba(0,0,0,0.4))] backdrop-blur-sm"
            onClick={onClose}
            aria-hidden="true"
          />

          {/* Dialog */}
          <m.div
            ref={dialogRef}
            role="dialog"
            aria-modal="true"
            aria-label={t("shortcuts.title")}
            className="map-card-matte relative w-full max-w-sm overflow-hidden rounded-2xl p-6"
            initial={prefersReduced ? false : { scale: 0.95, y: 8 }}
            animate={{ scale: 1, y: 0 }}
            exit={prefersReduced ? { opacity: 0 } : { scale: 0.95, y: 8 }}
            transition={
              prefersReduced ? { duration: 0 } : { type: "spring", stiffness: 400, damping: 30 }
            }
          >
            {/* Header */}
            <div className="mb-5 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <KeyboardIcon size={18} className="text-brand" aria-hidden="true" />
                <h2 className="text-lg font-bold text-text-primary">{t("shortcuts.title")}</h2>
              </div>
              <button
                type="button"
                onClick={onClose}
                aria-label={t("sidebar.close")}
                className="flex min-h-[44px] min-w-[44px] items-center justify-center rounded-lg text-text-secondary transition-colors hover:bg-[var(--bg-surface-hover)] hover:text-text-primary focus-visible:ring-2 focus-visible:ring-brand focus-visible:outline-none"
              >
                <CloseIcon size={16} aria-hidden="true" />
              </button>
            </div>

            {/* Shortcut list */}
            <dl className="space-y-3">
              {SHORTCUTS.map(({ keys, labelKey }) => (
                <div key={labelKey} className="flex items-center justify-between gap-4">
                  <dt className="text-sm text-text-secondary">{t(labelKey)}</dt>
                  <dd className="flex items-center gap-1">
                    {keys.map((key) => (
                      <kbd
                        key={key}
                        className="inline-flex h-6 min-w-6 items-center justify-center rounded-md matte-chip px-1.5 text-xs font-semibold text-text-primary"
                      >
                        {key}
                      </kbd>
                    ))}
                  </dd>
                </div>
              ))}
            </dl>
          </m.div>
        </m.div>
      )}
    </AnimatePresence>
  )
}
