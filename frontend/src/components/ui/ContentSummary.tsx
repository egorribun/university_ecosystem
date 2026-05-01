/**
 * ContentSummary — AI-generated summary with expand/collapse
 *
 * Shows a concise AI-generated summary with "Read more" to expand full content.
 * Includes "AI Summary" badge for transparency.
 *
 * Wave 38: AI features foundation
 */

import { useState } from "react"
import { m, AnimatePresence } from "framer-motion"
import { Sparkles, ChevronDown } from "lucide-react"
import { useTranslation } from "react-i18next"
import { cn } from "@/utils/cn"

interface ContentSummaryProps {
  /** AI-generated summary text */
  summary: string | null | undefined
  /** Full content to show when expanded */
  children: React.ReactNode
  /** Whether summary is still loading */
  loading?: boolean
  /** Additional className */
  className?: string
}

export function ContentSummary({
  summary,
  children,
  loading = false,
  className,
}: ContentSummaryProps) {
  const { t } = useTranslation(["common"])
  const [expanded, setExpanded] = useState(false)

  if (!summary && !loading) {
    return <>{children}</>
  }

  return (
    <div className={cn("space-y-3", className)}>
      {/* AI Summary Badge + Text */}
      <div className="glass-layer-surface rounded-xl p-4">
        <div className="mb-2 flex items-center gap-2">
          <div className="flex items-center gap-1.5 rounded-full bg-brand/(--opacity-subtle) px-2.5 py-1 text-xs font-bold text-brand">
            <Sparkles className="h-3 w-3" aria-hidden="true" />
            {t("common:ai.summaryBadge")}
          </div>
        </div>

        {loading ? (
          <div className="space-y-2">
            <div className="h-4 w-full animate-pulse rounded bg-(--bg-surface-hover)" />
            <div className="h-4 w-3/4 animate-pulse rounded bg-(--bg-surface-hover)" />
          </div>
        ) : (
          <p className="text-sm font-medium leading-relaxed text-text-secondary">{summary}</p>
        )}

        {!loading && (
          <button
            type="button"
            onClick={() => setExpanded(!expanded)}
            className="mt-3 flex items-center gap-1.5 text-xs font-bold text-brand transition-colors hover:text-primary-hover focus-ring-premium rounded-md px-1 py-0.5"
            aria-expanded={expanded}
          >
            {expanded ? t("common:ai.showLess") : t("common:ai.readMore")}
            <ChevronDown
              className={cn(
                "h-3.5 w-3.5 transition-transform duration-base",
                expanded && "rotate-180"
              )}
              aria-hidden="true"
            />
          </button>
        )}
      </div>

      {/* Expandable Full Content */}
      <AnimatePresence>
        {expanded && (
          <m.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
            className="overflow-hidden"
          >
            {children}
          </m.div>
        )}
      </AnimatePresence>
    </div>
  )
}
