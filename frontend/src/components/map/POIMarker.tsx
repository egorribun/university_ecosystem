/**
 * POIMarker.tsx — Premium POI marker with category-specific Lucide icons.
 * react-map-gl/maplibre Marker with hover tooltip + click popup.
 * Wave 102 — redesign from generic white-dot circles.
 * Wave 107 — replace hardcoded hex with CSS tokens.
 */

import { useState } from "react"
import { Marker, Popup } from "react-map-gl/maplibre"
import { useTranslation } from "react-i18next"
import {
  TrainFront,
  Bus,
  UtensilsCrossed,
  Coffee,
  ShoppingCart,
  ShoppingBag,
  Pill,
  Landmark,
  ParkingCircle,
  MapPin,
  type LucideIcon,
} from "lucide-react"
import type { CampusPOI } from "@/data/campusPOI"

/* ── Icon lookup by lucide icon name ── */
const ICON_MAP: Record<string, LucideIcon> = {
  TrainFront,
  Bus,
  UtensilsCrossed,
  Coffee,
  ShoppingCart,
  ShoppingBag,
  Pill,
  Landmark,
  ParkingCircle,
  MapPin,
}

/** CSS token reference for POI category colors — defined in map.css */
function poiColorVar(type: string): string {
  return `var(--map-poi-${type}, #94a3b8)`
}

interface POIMarkerProps {
  poi: CampusPOI & { osmName?: string }
}

export function POIMarker({ poi }: POIMarkerProps) {
  const { t } = useTranslation("map")
  const [showPopup, setShowPopup] = useState(false)
  const [isHovered, setIsHovered] = useState(false)

  const colorVar = poiColorVar(poi.type)
  const Icon = ICON_MAP[poi.icon] ?? MapPin

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
          role="button"
          tabIndex={0}
          aria-label={`${displayName} — ${t(`poi.categories.${poi.type}`)}`}
          className={`map-poi-pin${isHovered ? " map-poi-pin--hover" : ""}`}
          style={{
            "--_poi-color": colorVar,
          } as React.CSSProperties}
          onPointerEnter={() => setIsHovered(true)}
          onPointerLeave={() => setIsHovered(false)}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault()
              setShowPopup(true)
            }
          }}
        >
          <Icon size={14} color="white" strokeWidth={2.5} />
        </div>
      </Marker>

      {/* Hover tooltip — name only */}
      {isHovered && !showPopup && (
        <Popup
          longitude={poi.coords[1]}
          latitude={poi.coords[0]}
          anchor="bottom"
          offset={18}
          closeButton={false}
          closeOnClick={false}
          className="map-poi-tooltip"
        >
          <span className="text-xs font-semibold">{displayName}</span>
        </Popup>
      )}

      {/* Click popup — full details */}
      {showPopup && (
        <Popup
          longitude={poi.coords[1]}
          latitude={poi.coords[0]}
          anchor="bottom"
          offset={18}
          closeButton
          closeOnClick={false}
          onClose={() => setShowPopup(false)}
          className="map-popup-premium"
          maxWidth="240px"
        >
          <div className="map-popup-card map-popup-card--compact">
            <div className="flex items-center gap-2 mb-1.5">
              <div
                className="flex items-center justify-center w-7 h-7 rounded-full"
                style={{ backgroundColor: colorVar }}
              >
                <Icon size={14} color="white" strokeWidth={2.5} />
              </div>
              <div>
                <p className="font-bold text-sm leading-tight">{displayName}</p>
                <p className="text-[10px] opacity-50">{t(`poi.categories.${poi.type}`)}</p>
              </div>
            </div>
            <a
              href={yandexMapsUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="map-popup-link"
            >
              {t("poi.openInMaps")} &rarr;
            </a>
          </div>
        </Popup>
      )}
    </>
  )
}
