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
    <nav aria-label={t("events:detail.nav.label")} className="flex items-stretch gap-4 mt-10">
      {/* Previous event */}
      {prevId ? (
        <Link
          to="/events/$id"
          params={{ id: prevId }}
          className="group flex flex-1 items-center gap-3 rounded-xl events-nav-btn px-4 py-3 min-h-[44px] focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2"
        >
          <ChevronLeft
            size={16}
            className="shrink-0 text-(--text-secondary) transition-transform duration-fast group-hover:-translate-x-0.5"
          />
          <div className="min-w-0">
            <div className="text-[10px] font-semibold uppercase tracking-wider text-(--text-secondary)">
              {t("events:detail.nav.prev")}
            </div>
            <div className="text-sm font-semibold text-text-primary line-clamp-1 transition-colors duration-fast group-hover:text-brand">
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
          className="group flex flex-1 items-center justify-end gap-3 rounded-xl events-nav-btn px-4 py-3 text-right min-h-[44px] focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2"
        >
          <div className="min-w-0">
            <div className="text-[10px] font-semibold uppercase tracking-wider text-(--text-secondary)">
              {t("events:detail.nav.next")}
            </div>
            <div className="text-sm font-semibold text-text-primary line-clamp-1 transition-colors duration-fast group-hover:text-brand">
              {nextTitle}
            </div>
          </div>
          <ChevronRight
            size={16}
            className="shrink-0 text-(--text-secondary) transition-transform duration-fast group-hover:translate-x-0.5"
          />
        </Link>
      ) : (
        <div className="flex-1" />
      )}
    </nav>
  )
}
