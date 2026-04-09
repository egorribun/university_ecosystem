/**
 * EventDetailNavigation — prev/next event navigation links.
 * Pattern source: components/news/NewsDetailNavigation.tsx
 */

import { Link } from "@tanstack/react-router"
import { ChevronLeft, ChevronRight } from "lucide-react"
import { useTranslation } from "react-i18next"

interface EventDetailNavigationProps {
  prevId: string | null
  nextId: string | null
  prevTitle: string | null
  nextTitle: string | null
}

export function EventDetailNavigation({
  prevId,
  nextId,
  prevTitle,
  nextTitle,
}: EventDetailNavigationProps) {
  const { t } = useTranslation(["events"])

  if (!prevId && !nextId) return null

  return (
    <nav
      aria-label={t("events:detail.nav.label")}
      className="flex items-stretch gap-4 border-t border-glass-border/(--opacity-soft) pt-6 mt-8"
    >
      {/* Previous event */}
      {prevId ? (
        <Link
          to="/events/$id"
          params={{ id: prevId }}
          className="flex flex-1 items-center gap-2 rounded-xl glass-layer-surface border border-glass-border/(--opacity-soft) px-4 py-3 transition hover:shadow-glass hover:-translate-y-0.5 focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2"
        >
          <ChevronLeft size={16} className="shrink-0 text-(--text-secondary)" />
          <div className="min-w-0">
            <div className="text-[10px] font-semibold uppercase tracking-wider text-(--text-secondary)">
              {t("events:detail.nav.prev")}
            </div>
            <div className="text-sm font-semibold text-text-primary line-clamp-1">
              {prevTitle}
            </div>
          </div>
        </Link>
      ) : (
        <div className="flex-1" />
      )}

      {/* Next event */}
      {nextId ? (
        <Link
          to="/events/$id"
          params={{ id: nextId }}
          className="flex flex-1 items-center justify-end gap-2 rounded-xl glass-layer-surface border border-glass-border/(--opacity-soft) px-4 py-3 text-right transition hover:shadow-glass hover:-translate-y-0.5 focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2"
        >
          <div className="min-w-0">
            <div className="text-[10px] font-semibold uppercase tracking-wider text-(--text-secondary)">
              {t("events:detail.nav.next")}
            </div>
            <div className="text-sm font-semibold text-text-primary line-clamp-1">
              {nextTitle}
            </div>
          </div>
          <ChevronRight size={16} className="shrink-0 text-(--text-secondary)" />
        </Link>
      ) : (
        <div className="flex-1" />
      )}
    </nav>
  )
}
