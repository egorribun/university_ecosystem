/**
 * ExportDropdown — Multi-format export menu for schedule.
 * Wave 66 (Idea #9). Supports PDF, PNG, Google Calendar.
 */
import { useState, useCallback, useRef, useEffect } from "react"
import { useTranslation } from "react-i18next"
import { AnimatePresence, m } from "framer-motion"
import { Download, ChevronDown, FileText, Image, FileDown } from "lucide-react"
import { logError } from "@/app/logger"
import { cn } from "@/utils/cn"

interface ExportDropdownProps {
  isExporting?: boolean
  /** Ref to the grid element for canvas-based export */
  gridRef?: React.RefObject<HTMLElement | null>
  className?: string
}

export function ExportDropdown({ isExporting, gridRef, className }: ExportDropdownProps) {
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

  // Close on Escape + arrow-key navigation (FIX-67-05: menu a11y)
  useEffect(() => {
    if (!open) return
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setOpen(false)
        return
      }
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault()
        const menu = dropdownRef.current!.querySelector('[role="menu"]')!
        const items = Array.from(
          menu.querySelectorAll<HTMLElement>('[role="menuitem"]:not([disabled])')
        )
        const focused = document.activeElement as HTMLElement
        const idx = items.indexOf(focused)
        const next =
          e.key === "ArrowDown"
            ? items[(idx + 1) % items.length]
            : items[(idx - 1 + items.length) % items.length]
        next?.focus()
      }
    }
    document.addEventListener("keydown", handleKey)
    return () => document.removeEventListener("keydown", handleKey)
  }, [open])

  const handleExportPng = useCallback(async () => {
    const grid = gridRef!.current!
    setExporting("png")
    try {
      const { exportScheduleAsPng } = await import("@/utils/scheduleExport")
      const result = await exportScheduleAsPng(grid)
      if (!result.success) {
        logError("[schedule:export:png]", result.error)
      }
    } catch (err) {
      logError("[schedule:export:png]", err)
    } finally {
      setExporting(null)
      setOpen(false)
    }
  }, [gridRef])

  const handleExportPdf = useCallback(async () => {
    const grid = gridRef!.current!
    setExporting("pdf")
    try {
      const { exportScheduleAsPdf } = await import("@/utils/scheduleExport")
      const result = await exportScheduleAsPdf(grid, t("schedule:title.default"))
      if (!result.success) {
        logError("[schedule:export:pdf]", result.error)
      }
    } catch (err) {
      logError("[schedule:export:pdf]", err)
    } finally {
      setExporting(null)
      setOpen(false)
    }
  }, [gridRef, t])

  const items = [
    {
      id: "pdf",
      icon: FileText,
      label: t("schedule:export.pdf"),
      onClick: handleExportPdf,
      disabled: !gridRef?.current,
    },
    {
      id: "png",
      icon: Image,
      label: t("schedule:export.png"),
      onClick: handleExportPng,
      disabled: !gridRef?.current,
    },
    {
      id: "gcal",
      icon: FileDown,
      label: t("schedule:export.googleCalendar"),
      onClick: () => {
        // Opens Google Calendar with first lesson — user can adjust
        window.open("https://calendar.google.com/calendar/r/week", "_blank", "noopener")
        setOpen(false)
      },
    },
  ]

  return (
    <div ref={dropdownRef} className={cn("relative z-30", className)}>
      {/* FIX-68-27: plain button — no Button wrapper to avoid gap/wrap issues */}
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-haspopup="menu"
        className="inline-flex items-center gap-1.5 whitespace-nowrap rounded-lg px-2.5 py-1.5 text-sm font-semibold text-text-secondary transition-colors hover:bg-surface-elevated/(--opacity-dim) hover:text-text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
      >
        {isExporting || exporting ? (
          <div
            className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-current/30 border-t-current"
            aria-hidden="true"
          />
        ) : (
          <Download size={14} aria-hidden="true" className="shrink-0" />
        )}
        {t("schedule:toolbar.export")}
        <ChevronDown
          size={11}
          aria-hidden="true"
          className={`shrink-0 opacity-50 transition-transform duration-200 ${open ? "rotate-180" : ""}`}
        />
      </button>

      <AnimatePresence>
        {open && (
          <m.div
            role="menu"
            initial={{ opacity: 0, y: -4, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -4, scale: 0.95 }}
            transition={{ duration: 0.15 }}
            className="sched-export-dropdown sched-matte-card"
          >
            {items.map(({ id, icon: Icon, label, onClick, disabled }) => (
              <button
                key={id}
                type="button"
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
          </m.div>
        )}
      </AnimatePresence>
    </div>
  )
}
