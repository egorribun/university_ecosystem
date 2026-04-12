/**
 * BuildingMarker.tsx — Custom marker for a GUU campus building.
 * react-map-gl/maplibre Marker with JSX children + Popup.
 * Wave 100 — Leaflet → MapLibre GL migration.
 */

import { useState, useMemo } from "react"
import { Marker, Popup } from "react-map-gl/maplibre"
import { useTranslation } from "react-i18next"
import type { CampusBuilding, BuildingLetter } from "@/data/campusBuildings"

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
  const size = isActive ? 44 : 36
  const fontSize = isActive ? 18 : 15
  const borderWidth = isActive ? 3 : 2

  const roomCount = useMemo(
    () => building.floors.reduce((sum, f) => sum + f.rooms.length, 0),
    [building.floors],
  )

  return (
    <>
      <Marker
        longitude={building.geoCoords[1]}
        latitude={building.geoCoords[0]}
        anchor="center"
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
          className="map-building-marker-3d"
          style={{
            width: size,
            height: size,
            background: building.colorHex,
            border: `${borderWidth}px solid white`,
            borderRadius: "50%",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            color: "white",
            fontWeight: 900,
            fontSize,
            boxShadow: `0 2px 8px rgba(0,0,0,0.3)${isActive ? `, 0 0 0 4px ${building.colorHex}40` : ""}`,
            cursor: "pointer",
            fontFamily: "var(--font-ui), Inter, system-ui, sans-serif",
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault()
              onClick(building.letter)
              setShowPopup(true)
            }
          }}
        >
          {building.letter}
        </div>
      </Marker>

      {showPopup && (
        <Popup
          longitude={building.geoCoords[1]}
          latitude={building.geoCoords[0]}
          anchor="bottom"
          offset={25}
          closeButton={true}
          closeOnClick={false}
          onClose={() => setShowPopup(false)}
          className="map-building-popup"
        >
          <div className="map-popup-content">
            <div className="flex items-center gap-2 mb-1">
              <span
                className="inline-flex items-center justify-center w-7 h-7 rounded-full text-white font-black text-sm"
                style={{ backgroundColor: building.colorHex }}
              >
                {building.letter}
              </span>
              <span className="font-bold text-sm">{building.name}</span>
            </div>
            <p className="text-xs opacity-70 mb-1">{building.structureId}</p>
            {building.description && (
              <p className="text-xs opacity-80 line-clamp-2">{building.description}</p>
            )}
            <div className="text-xs opacity-60 mt-1">
              {t("tooltip.floors", { count: building.floorCount })}
            </div>
          </div>
        </Popup>
      )}
    </>
  )
}
