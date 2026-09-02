/**
 * EventQuickView — hover popover showing expanded preview of an event card.
 * Pointer-events-none so it doesn't block clicks.
 * Pattern source: components/news/NewsQuickView.tsx
 */

import { m, AnimatePresence } from "framer-motion"
import useMediaQuery from "@/hooks/useMediaQuery"
import { Calendar, MapPin, Users } from "lucide-react"
import { formatDate } from "@/utils/date"
import { useTranslation } from "react-i18next"
import { EventCategoryBadge } from "./EventCategoryBadge"
import type { EventCategory } from "@/features/events/categories"

interface EventQuickViewProps {
  visible: boolean
  title: string
  description: string
  startsAt: string
  endsAt?: string
  location?: string
  participantCount: number
  category: EventCategory
  position?: "top" | "bottom"
}

function formatShortDate(s: string): string {
  return (
    formatDate(s, {
      day: "numeric",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    }) || ""
  )
}

export function EventQuickView({
  visible,
  title,
  description,
  startsAt,
  endsAt: _endsAt,
  location,
  participantCount,
  category,
  position = "top",
}: EventQuickViewProps) {
  const { t } = useTranslation(["events"])
  const prefersReduced = useMediaQuery("(prefers-reduced-motion: reduce)")

  return (
    <AnimatePresence>
      {visible && (
        <m.div
          aria-hidden="true"
          initial={
            prefersReduced ? false : { opacity: 0, y: position === "top" ? 8 : -8, scale: 0.96 }
          }
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={
            prefersReduced
              ? { opacity: 0 }
              : { opacity: 0, y: position === "top" ? 4 : -4, scale: 0.98 }
          }
          transition={
            prefersReduced ? { duration: 0 } : { duration: 0.18, ease: [0.16, 1, 0.3, 1] }
          }
          className={`absolute left-0 right-0 z-floating pointer-events-none ${
            position === "top" ? "bottom-full mb-2" : "top-full mt-2"
          }`}
        >
          <div className="glass-layer-floating glass-noise rounded-xl p-4 shadow-premium-lift border border-glass-border/(--opacity-soft) max-w-[24rem] mx-auto">
            {/* Category + date */}
            <div className="flex items-center gap-2 mb-2 flex-wrap">
              <EventCategoryBadge category={category} size="sm" />
              {startsAt && (
                <span className="flex items-center gap-1 text-[11px] text-(--text-secondary)">
                  <Calendar size={11} />
                  {formatShortDate(startsAt)}
                </span>
              )}
            </div>

            {/* Title */}
            <h4 className="text-sm font-bold text-text-primary line-clamp-2 mb-1.5">{title}</h4>

            {/* Description preview */}
            {description && (
              <p className="text-xs leading-relaxed text-(--text-secondary) line-clamp-3 mb-3">
                {description}
              </p>
            )}

            {/* Stats footer */}
            <div className="flex items-center gap-3 text-[11px] text-(--text-secondary)">
              {location && (
                <span className="flex items-center gap-1">
                  <MapPin size={11} />
                  <span className="truncate max-w-[8rem]">{location}</span>
                </span>
              )}
              <span className="flex items-center gap-1">
                <Users size={11} />
                {participantCount}
              </span>
              <span className="ml-auto text-brand font-semibold">
                {t("events:quickView.viewDetails")}
              </span>
            </div>
          </div>
        </m.div>
      )}
    </AnimatePresence>
  )
}
