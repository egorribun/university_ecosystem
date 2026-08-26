/**
 * BuildingMarker.tsx — Premium pin-style marker for GUU campus buildings.
 * SVG drop-pin shape with category icon + building letter badge.
 * Wave 102 — premium redesign from plain circles.
 */

import type React from "react"
import { useRef } from "react"
import type { MarkerInstance } from "react-map-gl/maplibre"
import { Marker, Popup } from "react-map-gl/maplibre"
import { useTranslation } from "react-i18next"
import type { CampusBuilding, BuildingId } from "@/data/campusBuildings"
import { isOpenNow } from "@/utils/buildingHours"
import { getPrimaryIcon } from "@/utils/buildingCategoryIcons"
import { useStripMaplibreMarkerChrome } from "@/utils/stripMaplibreMarkerChrome"
import { MAP_INTERACTIVE_TARGET_PX } from "@/constants/campus"
import type { MapMarkerOffset } from "@/features/map/markerCollisionLayout"

interface BuildingMarkerProps {
  building: CampusBuilding
  isSelected: boolean
  isHighlighted: boolean
  onClick: (letter: BuildingId) => void
  /** Array index for stagger entrance animation */
  index?: number
  /** Lifted popup state — only one popup open at a time (FIX-109-07) */
  isPopupOpen?: boolean
  onPopupOpen?: () => void
  onPopupClose?: () => void
  /** Number of upcoming events at this building (FIX-109-11) */
  eventCount?: number
  offset?: MapMarkerOffset
}

export function BuildingMarker({
  building,
  isSelected,
  isHighlighted,
  onClick,
  index = 0,
  isPopupOpen,
  onPopupOpen,
  onPopupClose,
  eventCount = 0,
  offset,
}: BuildingMarkerProps) {
  const { t } = useTranslation("map")
  const markerRef = useRef<MarkerInstance | null>(null)
  // Wave 116 polish — maplibre-gl's Marker class unconditionally stamps
  // role="button" + generic aria-label="Map marker" onto its wrapper element.
  // Nesting our rich inner role="button" inside that generic outer button
  // triggered axe `nested-interactive` × 20 markers. See
  // utils/stripMaplibreMarkerChrome.ts for the full rationale — TL;DR: strip
  // outer role/aria-label/tabindex post-mount so the inner stays the single
  // interactive element with the localized building accessible name.
  useStripMaplibreMarkerChrome(markerRef)

  // FIX-109-03: "highlighted" (schedule next lesson) is visually distinct from
  // "selected" (user clicked). Highlighted = subtle pulse only, NOT full active state.
  const isActive = isSelected
  const Icon = getPrimaryIcon(building.tags)

  const roomCount = building.floors.reduce((sum, f) => sum + f.rooms.length, 0)

  return (
    <>
      <Marker
        ref={markerRef}
        longitude={building.geoCoords[1]}
        latitude={building.geoCoords[0]}
        anchor="bottom"
        offset={offset}
      >
        <div
          role="button"
          tabIndex={0}
          aria-label={t("a11y.buildingSelected", {
            name: building.name,
            floors: building.floorCount,
            rooms: roomCount,
          })}
          className={`map-building-pin map-building-pin--entering${isActive ? " map-building-pin--active" : ""}${isHighlighted && !isActive ? " map-building-pin--pulse" : ""}`}
          style={
            {
              "--stagger-index": index,
              "--_pin-color": building.colorHex,
              minWidth: MAP_INTERACTIVE_TARGET_PX,
              minHeight: MAP_INTERACTIVE_TARGET_PX,
            } as React.CSSProperties
          }
          onClick={(e) => {
            e.stopPropagation()
            onClick(building.letter)
            onPopupOpen?.()
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault()
              onClick(building.letter)
              onPopupOpen?.()
            }
          }}
        >
          {/* SVG pin shape */}
          <svg
            width={isActive ? 48 : 40}
            height={isActive ? 60 : 50}
            viewBox="0 0 40 50"
            fill="none"
            xmlns="http://www.w3.org/2000/svg"
            className="map-pin-svg"
          >
            {/* Shadow ellipse */}
            <ellipse cx="20" cy="48" rx="8" ry="2" fill="rgba(0,0,0,0.2)" />
            {/* Pin body */}
            <path
              d="M20 47C20 47 36 30.5 36 19C36 10.16 28.84 3 20 3C11.16 3 4 10.16 4 19C4 30.5 20 47 20 47Z"
              fill={building.colorHex}
              stroke="white"
              strokeWidth="2.5"
            />
            {/* Inner circle background for icon */}
            <circle cx="20" cy="19" r="11" fill="rgba(255,255,255,0.25)" />
          </svg>

          {/* Icon overlay */}
          <div className="map-pin-icon" style={{ top: isActive ? 12 : 10 }}>
            <Icon size={isActive ? 18 : 16} color="white" strokeWidth={2.5} />
          </div>

          {/* Event indicator badge — amber dot with count (FIX-109-11) */}
          {eventCount > 0 && (
            <div
              className="map-event-badge"
              aria-label={t("events.badgeLabel", { count: eventCount })}
            >
              {eventCount}
            </div>
          )}
        </div>
      </Marker>

      {isPopupOpen && (
        <Popup
          longitude={building.geoCoords[1]}
          latitude={building.geoCoords[0]}
          anchor="bottom"
          offset={isActive ? 62 : 52}
          closeButton
          closeOnClick={false}
          onClose={() => onPopupClose?.()}
          className="map-popup-premium"
          maxWidth="280px"
        >
          {building.photo ? (
            <img
              src={building.photo}
              alt={building.name}
              className="map-popup-photo"
              loading="lazy"
            />
          ) : (
            <div
              className="map-photo-placeholder"
              style={{
                background: `linear-gradient(135deg, ${building.colorHex}, color-mix(in srgb, ${building.colorHex} 60%, black))`,
              }}
            >
              <Icon size={32} strokeWidth={1.5} />
            </div>
          )}
          <div className="map-popup-card">
            {/* Header: color bar + letter badge + name */}
            <div
              className="map-popup-header"
              style={{ "--_popup-accent": building.colorHex } as React.CSSProperties}
            >
              <div className="map-popup-badge" style={{ backgroundColor: building.colorHex }}>
                {building.letter}
              </div>
              <div className="map-popup-title-block">
                <p className="map-popup-name">{building.name}</p>
                <p className="map-popup-structure">{building.structureId}</p>
              </div>
            </div>

            {/* Description */}
            {building.description && <p className="map-popup-desc">{building.description}</p>}

            {/* Stats row */}
            <div className="map-popup-stats">
              <span>{t("tooltip.floors", { count: building.floorCount })}</span>
              <span className="map-popup-stats-dot" />
              <span>{t("sidebar.roomCount", { count: roomCount })}</span>
              <span className="map-popup-stats-dot" />
              <span
                className="font-bold text-[10px] px-1.5 py-0.5 rounded-full"
                style={{
                  backgroundColor: isOpenNow(building.hours)
                    ? "color-mix(in srgb, var(--color-emerald-500) 15%, transparent)"
                    : "color-mix(in srgb, var(--color-rose-500) 15%, transparent)",
                  color: isOpenNow(building.hours)
                    ? "var(--color-emerald-500)"
                    : "var(--color-rose-500)",
                }}
              >
                {isOpenNow(building.hours) ? t("hours.openNow") : t("hours.closedNow")}
              </span>
            </div>

            {/* Amenity chips */}
            {building.amenities.length > 0 && (
              <div className="map-popup-amenities">
                {building.amenities.slice(0, 4).map((a) => (
                  <span key={a} className="map-popup-chip">
                    {a}
                  </span>
                ))}
              </div>
            )}
          </div>
        </Popup>
      )}
    </>
  )
}
