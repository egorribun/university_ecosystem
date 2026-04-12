/**
 * POIMarker.tsx — Marker for a point of interest on the map.
 * react-map-gl/maplibre Marker with JSX children + Popup.
 * Wave 100 — Leaflet → MapLibre GL migration.
 */

import { useState } from "react"
import { Marker, Popup } from "react-map-gl/maplibre"
import { useTranslation } from "react-i18next"
import type { CampusPOI } from "@/data/campusPOI"

const CATEGORY_HEX: Record<string, string> = {
  transport: "#3b82f6",
  food: "#f59e0b",
  shop: "#8b5cf6",
  service: "#10b981",
  campus: "#14b8a6",
}

interface POIMarkerProps {
  poi: CampusPOI & { osmName?: string }
}

export function POIMarker({ poi }: POIMarkerProps) {
  const { t } = useTranslation("map")
  const [showPopup, setShowPopup] = useState(false)

  const DEFAULT_HEX = "#94a3b8" // --color-slate-400
  const hex = CATEGORY_HEX[poi.type] ?? DEFAULT_HEX

  const displayName = poi.i18nKey
    ? t(`poi.items.${poi.i18nKey}.name`)
    : poi.osmName ?? t(`poi.categories.${poi.type}`)

  const yandexMapsUrl = `https://yandex.ru/maps/?pt=${poi.coords[1]},${poi.coords[0]}&z=17&l=map`

  return (
    <>
      <Marker
        longitude={poi.coords[1]}
        latitude={poi.coords[0]}
        anchor="center"
        onClick={(e) => {
          e.originalEvent.stopPropagation()
          setShowPopup(true)
        }}
      >
        <div
          aria-label={`${displayName} — ${t(`poi.categories.${poi.type}`)}`}
          className="map-poi-marker-3d"
          style={{
            width: 28,
            height: 28,
            background: hex,
            border: "2px solid white",
            borderRadius: "50%",
            boxShadow: "0 1px 4px rgba(0,0,0,0.25)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            cursor: "pointer",
          }}
        >
          <div style={{ width: 8, height: 8, background: "white", borderRadius: "50%" }} />
        </div>
      </Marker>

      {showPopup && (
        <Popup
          longitude={poi.coords[1]}
          latitude={poi.coords[0]}
          anchor="bottom"
          offset={16}
          closeButton={true}
          closeOnClick={false}
          onClose={() => setShowPopup(false)}
          className="map-poi-popup"
        >
          <div className="map-popup-content">
            <p className="font-semibold text-sm mb-0.5">{displayName}</p>
            <p className="text-xs opacity-60 mb-1.5">{t(`poi.categories.${poi.type}`)}</p>
            <a
              href={yandexMapsUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs font-medium"
              style={{ color: "var(--map-accent-line, #14b8a6)" }}
            >
              {t("poi.openInMaps")}
            </a>
          </div>
        </Popup>
      )}
    </>
  )
}
