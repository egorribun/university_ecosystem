/**
 * POIMarker.tsx — Premium POI marker with category-specific Lucide icons.
 * react-map-gl/maplibre Marker with hover tooltip + click popup.
 * Wave 102 — redesign from generic white-dot circles.
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
  const [isHovered, setIsHovered] = useState(false)

  const hex = CATEGORY_HEX[poi.type] ?? "#94a3b8"
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
          aria-label={`${displayName} — ${t(`poi.categories.${poi.type}`)}`}
          className={`map-poi-pin${isHovered ? " map-poi-pin--hover" : ""}`}
          style={{
            "--_poi-color": hex,
          } as React.CSSProperties}
          onPointerEnter={() => setIsHovered(true)}
          onPointerLeave={() => setIsHovered(false)}
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
                style={{ backgroundColor: hex }}
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
