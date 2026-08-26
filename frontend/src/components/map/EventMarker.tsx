/**
 * EventMarker.tsx — Warm amber event pin for campus map.
 * Distinct from blue building markers and small POI dots.
 * Uses react-map-gl/maplibre Marker + Popup, follows BuildingMarker pattern.
 * Wave 108
 */

import { useMemo, useRef } from "react"
import type { MarkerInstance } from "react-map-gl/maplibre"
import { Marker, Popup } from "react-map-gl/maplibre"
import { Link } from "@tanstack/react-router"
import { useTranslation } from "react-i18next"
import { CalendarDays } from "lucide-react"
import type { MapEvent } from "@/hooks/useMapEvents"
import { logError } from "@/app/logger"
import { useStripMaplibreMarkerChrome } from "@/utils/stripMaplibreMarkerChrome"
import { MAP_INTERACTIVE_TARGET_PX } from "@/constants/campus"
import type { MapMarkerOffset } from "@/features/map/markerCollisionLayout"

/**
 * Event pin color — uses CSS token var(--map-event-color) in stylesheets.
 * Hex fallback needed here because SVG `fill` in JSX is inline, not DOM CSS.
 * Matches --color-amber-500.
 */
const EVENT_PIN_COLOR = "#f59e0b"

interface EventMarkerProps {
  event: MapEvent
  /** Lifted popup state (FIX-109-07) */
  isPopupOpen?: boolean
  onPopupOpen?: () => void
  onPopupClose?: () => void
  offset?: MapMarkerOffset
}

/**
 * Format a date-time string with locale-aware short format.
 * Returns e.g. "Apr 14, 18:00" or "14 апр., 18:00".
 */
function formatEventDate(isoString: string, locale: string): string {
  try {
    const date = new Date(isoString)
    return new Intl.DateTimeFormat(locale, {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      timeZone: Intl.DateTimeFormat().resolvedOptions().timeZone,
    }).format(date)
  } catch (err) {
    logError(err)
    return isoString
  }
}

export function EventMarker({
  event,
  isPopupOpen,
  onPopupOpen,
  onPopupClose,
  offset,
}: EventMarkerProps) {
  const { t, i18n } = useTranslation("map")
  const markerRef = useRef<MarkerInstance | null>(null)
  // Wave 116 polish — see BuildingMarker + utils/stripMaplibreMarkerChrome.ts.
  useStripMaplibreMarkerChrome(markerRef)

  const formattedDate = useMemo(
    () => formatEventDate(event.startsAt, i18n.language),
    [event.startsAt, i18n.language]
  )

  const ariaLabel = t("events.markerLabel", {
    title: event.title,
    date: formattedDate,
  })

  return (
    <>
      <Marker
        ref={markerRef}
        longitude={event.geoCoords[1]}
        latitude={event.geoCoords[0]}
        anchor="bottom"
        offset={offset}
      >
        <div
          role="button"
          tabIndex={0}
          aria-label={ariaLabel}
          className="map-event-pin"
          style={{
            minWidth: MAP_INTERACTIVE_TARGET_PX,
            minHeight: MAP_INTERACTIVE_TARGET_PX,
          }}
          onClick={(e) => {
            e.stopPropagation()
            onPopupOpen?.()
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault()
              onPopupOpen?.()
            }
          }}
        >
          {/* SVG pin shape — smaller than building pins */}
          <svg
            width={36}
            height={45}
            viewBox="0 0 40 50"
            fill="none"
            xmlns="http://www.w3.org/2000/svg"
            className="map-event-pin-svg"
          >
            <ellipse cx="20" cy="48" rx="7" ry="2" fill="rgba(0,0,0,0.15)" />
            <path
              d="M20 47C20 47 36 30.5 36 19C36 10.16 28.84 3 20 3C11.16 3 4 10.16 4 19C4 30.5 20 47 20 47Z"
              fill={EVENT_PIN_COLOR}
              stroke="white"
              strokeWidth="2.5"
            />
            <circle cx="20" cy="19" r="10" fill="rgba(255,255,255,0.25)" />
          </svg>

          {/* Calendar icon overlay — decorative, label is on parent button */}
          <div className="map-event-pin-icon" aria-hidden="true">
            <CalendarDays size={15} color="white" strokeWidth={2.5} />
          </div>
        </div>
      </Marker>

      {isPopupOpen && (
        <Popup
          longitude={event.geoCoords[1]}
          latitude={event.geoCoords[0]}
          anchor="bottom"
          offset={48}
          closeButton
          closeOnClick={false}
          onClose={() => onPopupClose?.()}
          className="map-popup-premium"
          maxWidth="260px"
        >
          <div className="map-popup-card map-popup-card--compact">
            {/* Header row: icon + title */}
            <div className="flex items-center gap-2 mb-1.5">
              <div
                className="flex items-center justify-center w-7 h-7 rounded-full shrink-0"
                style={{ backgroundColor: EVENT_PIN_COLOR }}
              >
                <CalendarDays size={14} color="white" strokeWidth={2.5} />
              </div>
              <p className="font-bold text-sm leading-tight line-clamp-2">{event.title}</p>
            </div>

            {/* Date/time */}
            <p className="text-xs opacity-70 mb-1">{formattedDate}</p>

            {/* Location */}
            <p className="text-[10px] opacity-50 mb-1">{event.location}</p>

            {/* Participant count */}
            {event.participantCount != null && event.participantCount > 0 && (
              <p className="text-[10px] opacity-50 mb-2">
                {t("events.participants", {
                  count: event.participantCount,
                })}
              </p>
            )}

            {/* View details link — client-side navigation (A11Y-110-03) */}
            <Link to="/events/$id" params={{ id: event.id }} className="map-popup-link">
              {t("events.viewDetails")} &rarr;
            </Link>
          </div>
        </Popup>
      )}
    </>
  )
}
