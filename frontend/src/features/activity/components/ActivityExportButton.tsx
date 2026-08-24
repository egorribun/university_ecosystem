import { useState, useRef, useEffect, useCallback, type RefObject } from "react"
import { useTranslation } from "react-i18next"
import { Download, FileImage, FileText, Loader2, Check, AlertCircle } from "lucide-react"
import { cn } from "@/utils/cn"
import { exportActivityAsPng, exportActivityAsPdf } from "@/utils/activityExport"

type ActivityExportButtonProps = {
  contentRef: RefObject<HTMLDivElement | null>
}

type FeedbackState = { type: "success" | "error"; message: string } | null

export function ActivityExportButton({ contentRef }: ActivityExportButtonProps) {
  const { t } = useTranslation(["activity"])
  const [open, setOpen] = useState(false)
  const [exporting, setExporting] = useState(false)
  const exportingRef = useRef(false)
  const [feedback, setFeedback] = useState<FeedbackState>(null)
  const menuRef = useRef<HTMLDivElement>(null)
  const triggerRef = useRef<HTMLButtonElement>(null)

  // Auto-clear feedback after 3s
  useEffect(() => {
    if (!feedback) return
    const timer = setTimeout(() => setFeedback(null), 3000)
    return () => clearTimeout(timer)
  }, [feedback])

  // Close on outside click (L5: instanceof Node guard)
  useEffect(() => {
    if (!open) return
    const handler = (e: MouseEvent) => {
      const target = e.target
      if (target instanceof Node && menuRef.current && !menuRef.current.contains(target)) {
        setOpen(false)
      }
    }
    document.addEventListener("mousedown", handler)
    return () => document.removeEventListener("mousedown", handler)
  }, [open])

  // M3: Escape key handler + focus restore
  useEffect(() => {
    if (!open) return
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setOpen(false)
        triggerRef.current?.focus()
      }
    }
    document.addEventListener("keydown", handler)
    return () => document.removeEventListener("keydown", handler)
  }, [open])

  // H2: Show feedback on export success/failure
  const handleExport = useCallback(
    async (format: "pdf" | "png") => {
      const el = contentRef.current
      if (!el || exportingRef.current) return
      exportingRef.current = true
      setExporting(true)
      setOpen(false)
      try {
        const result =
          format === "pdf"
            ? await exportActivityAsPdf(el, t("activity:title"))
            : await exportActivityAsPng(el)
        if (result.success) {
          setFeedback({ type: "success", message: t("activity:export.success") })
        } else {
          setFeedback({ type: "error", message: result.error ?? t("activity:export.error") })
        }
      } catch {
        setFeedback({ type: "error", message: t("activity:export.error") })
      } finally {
        exportingRef.current = false
        setExporting(false)
        triggerRef.current?.focus()
      }
    },
    [contentRef, t]
  )

  return (
    <div ref={menuRef} className="relative">
      <button
        ref={triggerRef}
        type="button"
        onClick={() => setOpen((v) => !v)}
        disabled={exporting}
        className={cn(
          "activity-export-btn inline-flex min-h-[44px] items-center gap-2 px-3 py-2 text-sm font-semibold text-text-primary",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
        )}
        aria-label={t("activity:export.title")}
        aria-expanded={open}
        aria-haspopup="menu"
      >
        {exporting ? (
          <Loader2 size={16} className="animate-spin" aria-hidden="true" />
        ) : feedback?.type === "success" ? (
          <Check size={16} className="text-[var(--activity-positive-accent)]" aria-hidden="true" />
        ) : feedback?.type === "error" ? (
          <AlertCircle
            size={16}
            className="text-[var(--activity-negative-accent)]"
            aria-hidden="true"
          />
        ) : (
          <Download size={16} aria-hidden="true" />
        )}
        <span className="hidden sm:inline">
          {exporting
            ? t("activity:export.exporting")
            : feedback
              ? feedback.message
              : t("activity:export.title")}
        </span>
      </button>

      {open && (
        <div
          className="absolute right-0 top-full z-30 mt-1 min-w-[140px] rounded-lg bg-[var(--bg-surface)] shadow-lg ring-1 ring-black/5"
          role="menu"
          aria-label={t("activity:export.title")}
        >
          <button
            type="button"
            role="menuitem"
            onClick={() => void handleExport("pdf")}
            className="flex w-full min-h-[44px] items-center gap-2 px-3 py-2 text-sm text-text-primary hover:bg-[var(--bg-surface-hover)] rounded-t-lg focus-visible:outline-none focus-visible:bg-[var(--bg-surface-hover)]"
          >
            <FileText size={14} aria-hidden="true" />
            {t("activity:export.pdf")}
          </button>
          <button
            type="button"
            role="menuitem"
            onClick={() => void handleExport("png")}
            className="flex w-full min-h-[44px] items-center gap-2 px-3 py-2 text-sm text-text-primary hover:bg-[var(--bg-surface-hover)] rounded-b-lg focus-visible:outline-none focus-visible:bg-[var(--bg-surface-hover)]"
          >
            <FileImage size={14} aria-hidden="true" />
            {t("activity:export.png")}
          </button>
        </div>
      )}
    </div>
  )
}
