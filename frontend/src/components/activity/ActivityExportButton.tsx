import { useState, useRef, useEffect, type RefObject } from "react"
import { useTranslation } from "react-i18next"
import { Download, FileImage, FileText, Loader2 } from "lucide-react"
import { cn } from "@/utils/cn"
import { exportActivityAsPng, exportActivityAsPdf } from "@/utils/activityExport"

type ActivityExportButtonProps = {
  contentRef: RefObject<HTMLDivElement | null>
}

export function ActivityExportButton({ contentRef }: ActivityExportButtonProps) {
  const { t } = useTranslation(["activity"])
  const [open, setOpen] = useState(false)
  const [exporting, setExporting] = useState(false)
  const menuRef = useRef<HTMLDivElement>(null)

  // Close on outside click
  useEffect(() => {
    if (!open) return
    const handler = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener("mousedown", handler)
    return () => document.removeEventListener("mousedown", handler)
  }, [open])

  const handleExport = async (format: "pdf" | "png") => {
    const el = contentRef.current
    if (!el || exporting) return
    setExporting(true)
    setOpen(false)
    try {
      if (format === "pdf") {
        await exportActivityAsPdf(el, t("activity:title"))
      } else {
        await exportActivityAsPng(el)
      }
    } finally {
      setExporting(false)
    }
  }

  return (
    <div ref={menuRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        disabled={exporting}
        className={cn(
          "activity-export-btn inline-flex min-h-[44px] items-center gap-2 px-3 py-2 text-sm font-semibold text-text-primary",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
        )}
        aria-label={t("activity:export.title")}
        aria-expanded={open}
      >
        {exporting ? (
          <Loader2 size={16} className="animate-spin" aria-hidden="true" />
        ) : (
          <Download size={16} aria-hidden="true" />
        )}
        <span className="hidden sm:inline">
          {exporting ? t("activity:export.exporting") : t("activity:export.title")}
        </span>
      </button>

      {open && (
        <div className="absolute right-0 top-full z-30 mt-1 min-w-[140px] rounded-lg bg-[var(--bg-surface)] shadow-lg ring-1 ring-black/5">
          <button
            type="button"
            onClick={() => void handleExport("pdf")}
            className="flex w-full items-center gap-2 px-3 py-2 text-sm text-text-primary hover:bg-[var(--bg-surface-hover)] rounded-t-lg"
          >
            <FileText size={14} aria-hidden="true" />
            {t("activity:export.pdf")}
          </button>
          <button
            type="button"
            onClick={() => void handleExport("png")}
            className="flex w-full items-center gap-2 px-3 py-2 text-sm text-text-primary hover:bg-[var(--bg-surface-hover)] rounded-b-lg"
          >
            <FileImage size={14} aria-hidden="true" />
            {t("activity:export.png")}
          </button>
        </div>
      )}
    </div>
  )
}
