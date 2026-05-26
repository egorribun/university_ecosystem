import { useCallback } from "react"
import { useTranslation } from "react-i18next"
import { X as CloseIcon, Keyboard as KeyboardIcon } from "lucide-react"
import { AnimatePresence, m } from "framer-motion"
import useFocusTrap from "@/hooks/useFocusTrap"
import useMediaQuery from "@/hooks/useMediaQuery"

interface ScheduleShortcutsOverlayProps {
  open: boolean
  onClose: () => void
}

const SHORTCUTS = [
  { keys: ["←", "→", "↑", "↓"], labelKey: "schedule:shortcuts.arrowNav" },
  { keys: ["Enter"], labelKey: "schedule:shortcuts.enter" },
  { keys: ["E"], labelKey: "schedule:shortcuts.edit" },
  { keys: ["Del"], labelKey: "schedule:shortcuts.delete" },
  { keys: ["T"], labelKey: "schedule:shortcuts.today" },
  { keys: ["?"], labelKey: "schedule:shortcuts.help" },
  { keys: ["Esc"], labelKey: "schedule:shortcuts.escape" },
] as const

// A11Y-65-01: Added useFocusTrap — replaces manual focus + keydown listener
export function ScheduleShortcutsOverlay({ open, onClose }: ScheduleShortcutsOverlayProps) {
  const { t } = useTranslation(["schedule"])
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
            className="absolute inset-0 bg-[var(--sched-modal-overlay-bg)] backdrop-blur-sm"
            onClick={onClose}
            aria-hidden="true"
          />

          {/* Dialog */}
          <m.div
            ref={dialogRef}
            role="dialog"
            aria-modal="true"
            aria-labelledby="sched-shortcuts-title"
            className="sched-settings-dialog relative w-full max-w-sm overflow-hidden rounded-2xl p-6"
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
                <h2 id="sched-shortcuts-title" className="text-lg font-bold text-text-primary">
                  {t("schedule:shortcuts.title")}
                </h2>
              </div>
              <button
                type="button"
                onClick={onClose}
                aria-label={t("common:buttons.close")}
                className="flex h-8 w-8 items-center justify-center rounded-lg text-text-secondary transition-colors hover:bg-surface-elevated/(--opacity-dim) hover:text-text-primary focus-visible:ring-2 focus-visible:ring-brand"
              >
                <CloseIcon size={16} aria-hidden="true" />
              </button>
            </div>

            {/* Shortcut list — semantic <dl> (FIX-69-04) */}
            <dl className="space-y-3">
              {/* FIX-70-DL: corrected dt/dd order — dt=term (description), dd=definition (keys) */}
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
