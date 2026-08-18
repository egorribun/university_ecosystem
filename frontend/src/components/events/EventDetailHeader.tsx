/**
 * EventDetailHeader — title, meta pills, action buttons.
 * Pattern source: components/news/NewsDetailHeader.tsx
 */

import { Calendar, MapPin, Users, Mic2, Share2, Pencil, Trash2 } from "lucide-react"
import { useTranslation } from "react-i18next"
import { formatDate } from "@/utils/date"
import { Button } from "@/components/ui"
import { EventCategoryBadge } from "./EventCategoryBadge"
import { inferEventCategory } from "@/features/events/categories"

interface EventDetailHeaderProps {
  title: string
  eventType?: string
  eventTypeEn?: string
  participantCount: number
  startsAt?: string
  endsAt?: string
  location?: string
  speaker?: string
  isRegistered: boolean
  isEnded: boolean
  isAdmin: boolean
  registering: boolean
  onShare: () => void
  onRegister: () => void
  onUnregister: () => void
  onEditOpen: () => void
  onDeleteOpen: () => void
}

const formatShortDateTime = (s: string) =>
  formatDate(s, {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  })

export function EventDetailHeader({
  title,
  eventType,
  eventTypeEn,
  participantCount,
  startsAt,
  endsAt,
  location,
  speaker,
  isRegistered,
  isEnded,
  isAdmin,
  registering,
  onShare,
  onRegister,
  onUnregister,
  onEditOpen,
  onDeleteOpen,
}: EventDetailHeaderProps) {
  const { t } = useTranslation(["events", "common"])
  const category = inferEventCategory(eventType ?? eventTypeEn)

  return (
    <header className="space-y-4">
      {/* Category badge */}
      <EventCategoryBadge category={category} size="md" />

      {/* Title */}
      <h1 className="text-fluid-h1 font-extrabold tracking-tight text-text-primary">{title}</h1>

      {/* Meta pills row */}
      <div className="flex flex-wrap items-center gap-2">
        {/* Participants */}
        <span className="matte-chip flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-semibold">
          <Users size={13} className="text-brand" />
          <span className="tabular-nums">
            {t("events:card.participants", { count: participantCount })}
          </span>
        </span>

        {/* Date range */}
        {startsAt && (
          <time
            dateTime={new Date(startsAt).toISOString()}
            className="matte-chip flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-semibold"
          >
            <Calendar size={13} className="text-brand" />
            <span>
              {formatShortDateTime(startsAt)}
              {endsAt ? ` — ${formatShortDateTime(endsAt)}` : ""}
            </span>
          </time>
        )}

        {/* Location */}
        {location && (
          <span className="matte-chip flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-semibold">
            <MapPin size={13} className="text-brand" />
            <span className="max-w-[12rem] truncate">{location}</span>
          </span>
        )}

        {/* Speaker */}
        {speaker && (
          <span className="matte-chip flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-semibold">
            <Mic2 size={13} className="text-brand" />
            <span>{speaker}</span>
          </span>
        )}
      </div>

      {/* Action buttons */}
      <div className="flex flex-wrap items-center gap-2 pt-1">
        {/* Share */}
        <Button
          variant="glass"
          size="sm"
          onClick={onShare}
          leadingIcon={<Share2 size={15} />}
          aria-label={t("events:detail.actions.share")}
        >
          {t("events:detail.actions.share")}
        </Button>

        {/* Register / Unregister — aria-live for screen reader announcements */}
        {!isEnded &&
          !isAdmin &&
          (isRegistered ? (
            <Button variant="outline" size="sm" onClick={onUnregister} disabled={registering}>
              {t("events:card.actions.unregister")}
            </Button>
          ) : (
            <Button
              variant="solid"
              size="sm"
              onClick={onRegister}
              disabled={registering}
              className="events-register-pulse"
            >
              {t("events:card.actions.register")}
            </Button>
          ))}

        {/* Admin actions */}
        {isAdmin && (
          <>
            <div className="hidden sm:block h-5 w-px bg-(--glass-border)" aria-hidden="true" />
            <Button
              variant="glass"
              size="sm"
              onClick={onEditOpen}
              leadingIcon={<Pencil size={14} />}
            >
              {t("common:buttons.edit")}
            </Button>
            <Button
              variant="glass"
              size="sm"
              onClick={onDeleteOpen}
              leadingIcon={<Trash2 size={14} />}
              className="text-error-text"
            >
              {t("common:buttons.delete")}
            </Button>
          </>
        )}
      </div>

      {/* Screen reader live region for registration status changes */}
      <div aria-live="polite" aria-atomic="true" className="sr-only">
        {isRegistered
          ? t("events:card.statuses.registered")
          : isEnded
            ? t("events:card.statuses.ended")
            : ""}
      </div>
    </header>
  )
}
