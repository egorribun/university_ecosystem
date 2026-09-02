/**
 * RelatedEvents — 3-column grid of same-type events.
 * Pattern source: components/news/RelatedNews.tsx
 */

import { Link } from "@tanstack/react-router"
import SmartImage from "@/components/media/SmartImage"
import { CalendarDays, ArrowRight } from "lucide-react"
import { useTranslation } from "react-i18next"
import { useLanguage } from "@/contexts/LanguageContext"
import { EventCategoryBadge } from "./EventCategoryBadge"
import { inferEventCategory } from "@/features/events/categories"
import { localizeField } from "@/utils/localize"
import { formatDate } from "@/utils/date"
import type { Event } from "@/types/Event"

interface RelatedEventsProps {
  items: Event[]
}

export const RELATED_EVENTS_TRANSLATION_NAMESPACES = ["events", "common"] as const
export const RELATED_EVENT_CARD_TRANSLATION_NAMESPACES = ["events"] as const

export function RelatedEvents({ items }: RelatedEventsProps) {
  const { t } = useTranslation([...RELATED_EVENTS_TRANSLATION_NAMESPACES])
  const { language } = useLanguage()

  if (items.length === 0) return null

  return (
    <section className="mt-10" aria-labelledby="related-events-heading">
      <h2
        id="related-events-heading"
        className="text-lg font-bold text-text-primary mb-4"
        style={{ scrollMarginTop: "5rem" }}
      >
        {t("events:detail.related.title")}
      </h2>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        {items.map((event) => (
          <RelatedEventCard key={event.id} event={event} language={language} />
        ))}
      </div>
    </section>
  )
}

function RelatedEventCard({ event, language }: { event: Event; language: "en" | "ru" }) {
  const { t } = useTranslation([...RELATED_EVENT_CARD_TRANSLATION_NAMESPACES])

  // These values are deliberately computed inline: each is a small, pure
  // presentation transform and keeping them as ordinary expressions makes
  // their empty/locale fallback behavior observable in the rendered card.
  const title = typeof event.title === "string" ? event.title : ""
  const eventType =
    event.event_type === null || event.event_type === undefined
      ? event.event_type_en
      : event.event_type
  const localizedTitle = localizeField(title, event.title_en, language)
  const category = inferEventCategory(eventType)
  const dateLabel = event.starts_at
    ? formatDate(event.starts_at, { day: "numeric", month: "short" })
    : ""

  return (
    <Link
      to="/events/$id"
      params={{ id: event.id }}
      className="group relative rounded-xl card-matte glass-noise border border-glass-border/(--opacity-soft) overflow-hidden transition-all duration-slower hover:shadow-premium-lift hover:-translate-y-1"
    >
      {/* Image */}
      <div className="relative h-32 overflow-hidden">
        {event.image_url ? (
          <SmartImage
            srcRaw={event.image_url}
            alt={localizedTitle}
            sizes="(min-width: 40rem) 33vw, 100vw"
            className="h-full w-full object-cover transition-transform duration-slower group-hover:scale-105"
          />
        ) : (
          <div className="flex h-full w-full items-center justify-center bg-linear-to-br from-brand/(--opacity-subtle) to-transparent">
            <CalendarDays className="h-8 w-8 text-brand/(--opacity-medium)" />
          </div>
        )}

        {/* Category badge */}
        <div className="absolute top-2 left-2">
          <EventCategoryBadge category={category} size="sm" />
        </div>
      </div>

      {/* Content */}
      <div className="flex flex-col gap-1.5 p-4">
        <h3 className="text-sm font-bold text-text-primary line-clamp-2 leading-snug">
          {localizedTitle}
        </h3>
        {dateLabel && <span className="text-[11px] text-(--text-secondary)">{dateLabel}</span>}
        <span className="mt-auto flex items-center gap-1 text-[11px] font-semibold text-brand opacity-0 group-hover:opacity-100 transition-opacity">
          {t("events:quickView.viewDetails")}
          <ArrowRight size={11} />
        </span>
      </div>
    </Link>
  )
}
