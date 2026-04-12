/**
 * BuildingMarker.tsx — Premium pin-style marker for GUU campus buildings.
 * SVG drop-pin shape with category icon + building letter badge.
 * Wave 102 — premium redesign from plain circles.
 */

import { useState, useMemo } from "react"
import { Marker, Popup } from "react-map-gl/maplibre"
import { useTranslation } from "react-i18next"
import {
  BookOpen,
  Building2,
  Dumbbell,
  Home,
  GraduationCap,
  type LucideIcon,
} from "lucide-react"
import type { CampusBuilding, BuildingLetter, MapCategory } from "@/data/campusBuildings"

/* ── Category → icon mapping ── */
const CATEGORY_ICONS: Record<string, LucideIcon> = {
  study: BookOpen,
  services: Building2,
  sports: Dumbbell,
  housing: Home,
  events: GraduationCap,
}

function getPrimaryIcon(tags: MapCategory[]): LucideIcon {
  for (const tag of tags) {
    if (CATEGORY_ICONS[tag]) return CATEGORY_ICONS[tag]
  }
  return Building2
}

interface BuildingMarkerProps {
  building: CampusBuilding
  isSelected: boolean
  isHighlighted: boolean
  onClick: (letter: BuildingLetter) => void
}

export function BuildingMarker({ building, isSelected, isHighlighted, onClick }: BuildingMarkerProps) {
  const { t } = useTranslation("map")
  const [showPopup, setShowPopup] = useState(false)

  const isActive = isSelected || isHighlighted
  const Icon = getPrimaryIcon(building.tags)

  const roomCount = useMemo(
    () => building.floors.reduce((sum, f) => sum + f.rooms.length, 0),
    [building.floors],
  )

  return (
    <>
      <Marker
        longitude={building.geoCoords[1]}
        latitude={building.geoCoords[0]}
        anchor="bottom"
        onClick={(e) => {
          e.originalEvent.stopPropagation()
          onClick(building.letter)
          setShowPopup(true)
        }}
      >
        <div
          role="button"
          tabIndex={0}
          aria-label={t("a11y.buildingSelected", {
            name: building.name,
            floors: building.floorCount,
            rooms: roomCount,
          })}
          className={`map-building-pin${isActive ? " map-building-pin--active" : ""}${isHighlighted ? " map-building-pin--pulse" : ""}`}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault()
              onClick(building.letter)
              setShowPopup(true)
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
          <div
            className="map-pin-icon"
            style={{ top: isActive ? 12 : 10 }}
          >
            <Icon size={isActive ? 18 : 16} color="white" strokeWidth={2.5} />
          </div>

          {/* Letter badge removed — not needed per user request (Wave 104) */}
        </div>
      </Marker>

      {showPopup && (
        <Popup
          longitude={building.geoCoords[1]}
          latitude={building.geoCoords[0]}
          anchor="bottom"
          offset={isActive ? 62 : 52}
          closeButton
          closeOnClick={false}
          onClose={() => setShowPopup(false)}
          className="map-popup-premium"
          maxWidth="280px"
        >
          <div className="map-popup-card">
            {/* Header: color bar + letter badge + name */}
            <div className="map-popup-header" style={{ "--_popup-accent": building.colorHex } as React.CSSProperties}>
              <div className="map-popup-badge" style={{ backgroundColor: building.colorHex }}>
                {building.letter}
              </div>
              <div className="map-popup-title-block">
                <p className="map-popup-name">{building.name}</p>
                <p className="map-popup-structure">{building.structureId}</p>
              </div>
            </div>

            {/* Description */}
            {building.description && (
              <p className="map-popup-desc">{building.description}</p>
            )}

            {/* Stats row */}
            <div className="map-popup-stats">
              <span>{t("tooltip.floors", { count: building.floorCount })}</span>
              <span className="map-popup-stats-dot" />
              <span>{t("sidebar.roomCount", { count: roomCount })}</span>
            </div>

            {/* Amenity chips */}
            {building.amenities.length > 0 && (
              <div className="map-popup-amenities">
                {building.amenities.slice(0, 4).map((a) => (
                  <span key={a} className="map-popup-chip">{a}</span>
                ))}
              </div>
            )}
          </div>
        </Popup>
      )}
    </>
  )
}
