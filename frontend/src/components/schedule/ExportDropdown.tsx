/**
 * ExportDropdown — Multi-format export menu for schedule.
 * Wave 66 (Idea #9). Supports .ics, PDF, PNG, Google Calendar.
 */
import { useState, useCallback, useRef, useEffect } from "react"
import { useTranslation } from "react-i18next"
import { AnimatePresence, motion } from "framer-motion"
import {
  Download,
  ChevronDown,
  FileText,
  Image,
  Calendar,
  FileDown,
} from "lucide-react"
import { Button } from "@/components/ui"

interface ExportDropdownProps {
  onExportIcs?: () => void
  isExporting?: boolean
  /** Ref to the grid element for canvas-based export */
  gridRef?: React.RefObject<HTMLElement | null>
  className?: string
}

export function ExportDropdown({
  onExportIcs,
  isExporting,
  gridRef,
  className,
}: ExportDropdownProps) {
  const { t } = useTranslation(["schedule"])
  const [open, setOpen] = useState(false)
  const [exporting, setExporting] = useState<string | null>(null)
  const dropdownRef = useRef<HTMLDivElement>(null)

  // Close on outside click
  useEffect(() => {
    if (!open) return
    const handleClick = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener("mousedown", handleClick)
    return () => document.removeEventListener("mousedown", handleClick)
  }, [open])

  // Close on Escape
  useEffect(() => {
    if (!open) return
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false)
    }
    document.addEventListener("keydown", handleKey)
    return () => document.removeEventListener("keydown", handleKey)
  }, [open])

  const handleExportPng = useCallback(async () => {
    if (!gridRef?.current) return
    setExporting("png")
    try {
      const { exportScheduleAsPng } = await import("@/utils/scheduleExport")
      await exportScheduleAsPng(gridRef.current)
    } catch {
      // silently fail
    } finally {
      setExporting(null)
      setOpen(false)
    }
  }, [gridRef])

  const handleExportPdf = useCallback(async () => {
    if (!gridRef?.current) return
    setExporting("pdf")
    try {
      const { exportScheduleAsPdf } = await import("@/utils/scheduleExport")
      await exportScheduleAsPdf(gridRef.current, t("schedule:title.default"))
    } catch {
      // silently fail
    } finally {
      setExporting(null)
      setOpen(false)
    }
  }, [gridRef, t])

  const handleIcs = useCallback(() => {
    onExportIcs?.()
    setOpen(false)
  }, [onExportIcs])

  const items = [
    {
      id: "ics",
      icon: Calendar,
      label: t("schedule:export.ics", { defaultValue: "iCalendar (.ics)" }),
      onClick: handleIcs,
      disabled: !onExportIcs || isExporting,
    },
    {
      id: "pdf",
      icon: FileText,
      label: t("schedule:export.pdf", { defaultValue: "PDF" }),
      onClick: handleExportPdf,
      disabled: !gridRef?.current,
    },
    {
      id: "png",
      icon: Image,
      label: t("schedule:export.png", { defaultValue: "PNG" }),
      onClick: handleExportPng,
      disabled: !gridRef?.current,
    },
    {
      id: "gcal",
      icon: FileDown,
      label: t("schedule:export.googleCalendar", { defaultValue: "Google Calendar" }),
      onClick: () => {
        // Opens Google Calendar with first lesson — user can adjust
        window.open("https://calendar.google.com/calendar/r/week", "_blank", "noopener")
        setOpen(false)
      },
    },
  ]

  return (
    <div ref={dropdownRef} className={`relative ${className ?? ""}`}>
      <Button
        variant="ghost"
        size="sm"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-haspopup="menu"
        className="gap-1.5"
      >
        {isExporting || exporting ? (
          <div className="h-4 w-4 animate-spin rounded-full border-2 border-current/30 border-t-current" aria-hidden="true" />
        ) : (
          <Download size={15} aria-hidden="true" />
        )}
        <span className="hidden sm:inline">{t("schedule:toolbar.export")}</span>
        <ChevronDown size={12} aria-hidden="true" className={`transition-transform ${open ? "rotate-180" : ""}`} />
      </Button>

      <AnimatePresence>
        {open && (
          <motion.div
            role="menu"
            initial={{ opacity: 0, y: -4, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -4, scale: 0.95 }}
            transition={{ duration: 0.15 }}
            className="sched-export-dropdown border border-glass-border bg-surface/(--opacity-heavy) shadow-glass-strong backdrop-blur-xl glass-noise"
          >
            {items.map(({ id, icon: Icon, label, onClick, disabled }) => (
              <button
                key={id}
                role="menuitem"
                disabled={disabled || exporting === id}
                onClick={onClick}
                className="flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-left text-sm font-medium text-text-primary transition-colors hover:bg-surface-elevated/(--opacity-dim) disabled:opacity-40 disabled:cursor-not-allowed focus-visible:ring-2 focus-visible:ring-brand"
              >
                {exporting === id ? (
                  <div className="h-4 w-4 animate-spin rounded-full border-2 border-current/30 border-t-current" />
                ) : (
                  <Icon size={15} className="text-text-secondary" aria-hidden="true" />
                )}
                {label}
              </button>
            ))}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
