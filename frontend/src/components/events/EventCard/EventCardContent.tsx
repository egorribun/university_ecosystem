/**
 * EventCardContent — text content section of the event card.
 * Contains: title (as Link), speaker, date range, location,
 * description preview, participant count, register CTA.
 * Pattern source: components/news/NewsCardContent.tsx
 */

import { memo } from "react"
import { Link } from "@tanstack/react-router"
import { Calendar, MapPin, Users, Mic2 } from "lucide-react"
import { useTranslation } from "react-i18next"
import { formatDate } from "@/utils/date"
import { cn } from "@/utils/cn"

interface EventCardContentProps {
  id: string
  title: string
  speaker?: string
  startsAt: string
  endsAt?: string
  location?: string
  description?: string
  participantCount: number
  isRegistered: boolean
  isEnded: boolean
  /** Disable hover effects when edit dialog open */
  hoveringDisabled?: boolean
}

const formatShortDate = (s: string) =>
  formatDate(s, {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }) || ""

const EventCardContent = ({
  id,
  title,
  speaker,
  startsAt,
  endsAt,
  location,
  description,
  participantCount,
  isRegistered,
  isEnded,
  hoveringDisabled,
}: EventCardContentProps) => {
  const { t } = useTranslation(["events"])

  return (
    <div className="flex flex-1 flex-col gap-2.5 p-4 pt-3">
      {/* Title — Link covers entire card via before:absolute */}
      <h3
        id={`event-title-${id}`}
        className="events-card-title font-bold text-text-primary leading-snug line-clamp-2"
      >
        <Link
          to="/events/$id"
          params={{ id }}
          className={cn(
            "before:absolute before:inset-0 outline-none",
            !hoveringDisabled && "group-hover:text-brand transition-colors duration-fast"
          )}
          tabIndex={-1}
        >
          {title}
        </Link>
      </h3>

      {/* Speaker */}
      {speaker && (
        <div className="flex items-center gap-1.5 text-xs text-(--text-secondary)">
          <Mic2 size={12} className="shrink-0" />
          <span className="truncate">{speaker}</span>
        </div>
      )}

      {/* Date range */}
      <div className="flex items-center gap-1.5 text-xs text-(--text-secondary)">
        <Calendar size={12} className="shrink-0" />
        <span>
          {formatShortDate(startsAt)}
          {endsAt ? ` — ${formatShortDate(endsAt)}` : ""}
        </span>
      </div>

      {/* Location */}
      {location && (
        <div
          id={`event-location-${id}`}
          className="flex items-center gap-1.5 text-xs text-(--text-secondary)"
        >
          <MapPin size={12} className="shrink-0" />
          <span className="truncate">{location}</span>
        </div>
      )}

      {/* Description preview */}
      {description && (
        <p className="events-card-preview text-xs leading-relaxed text-(--text-secondary) line-clamp-2 mt-0.5">
          {description}
        </p>
      )}

      {/* Footer — participant count + status */}
      <div className="events-card-footer mt-auto flex items-center gap-3 pt-2 border-t border-glass-border/(--opacity-soft)">
        <span className="flex items-center gap-1 text-xs text-(--text-secondary)">
          <Users size={12} />
          <span className="tabular-nums">{participantCount}</span>
        </span>

        {isEnded ? (
          <span className="ml-auto text-[10px] font-semibold uppercase tracking-wider text-(--text-secondary)">
            {t("events:card.statuses.ended")}
          </span>
        ) : isRegistered ? (
          <span className="ml-auto text-[10px] font-semibold uppercase tracking-wider text-success-text">
            {t("events:card.statuses.registered")}
          </span>
        ) : (
          <span className="ml-auto text-[10px] font-semibold uppercase tracking-wider text-brand">
            {t("events:card.statuses.open")}
          </span>
        )}
      </div>
    </div>
  )
}

export default memo(EventCardContent)
