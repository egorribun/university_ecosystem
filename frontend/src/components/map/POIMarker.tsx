/**
 * POIMarker.tsx — Premium POI marker with category-specific Lucide icons.
 * react-map-gl/maplibre Marker with hover tooltip + click popup.
 * Wave 102 — redesign from generic white-dot circles.
 * Wave 107 — replace hardcoded hex with CSS tokens.
 */

import { useRef, useState } from "react"
import type { MarkerInstance } from "react-map-gl/maplibre"
import { Marker, Popup } from "react-map-gl/maplibre"
import { useTranslation } from "react-i18next"
import { useStripMaplibreMarkerChrome } from "@/utils/stripMaplibreMarkerChrome"
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
  BookOpen,
  type LucideIcon,
} from "lucide-react"
import type { CampusPOI, POIIconName } from "@/data/campusPOI"
import { MAP_INTERACTIVE_TARGET_PX } from "@/constants/campus"
import type { MapMarkerOffset } from "@/features/map/markerCollisionLayout"

/** Resolve a persisted POI icon name while keeping an explicit safe fallback. */
export function getPoiIcon(icon: POIIconName): LucideIcon {
  switch (icon) {
    case "BookOpen":
      return BookOpen
    case "TrainFront":
      return TrainFront
    case "Bus":
      return Bus
    case "UtensilsCrossed":
      return UtensilsCrossed
    case "Coffee":
      return Coffee
    case "ShoppingCart":
      return ShoppingCart
    case "ShoppingBag":
      return ShoppingBag
    case "Pill":
      return Pill
    case "Landmark":
      return Landmark
    case "ParkingCircle":
      return ParkingCircle
    default:
      return MapPin
  }
}

const noop = () => undefined

/** CSS token reference for POI category colors — defined in map.css */
function poiColorVar(type: string): string {
  // Fallback = --color-slate-400 equivalent; inline because CSS var nesting limit
  return `var(--map-poi-${type}, var(--color-slate-400, #94a3b8))`
}

interface POIMarkerProps {
  poi: CampusPOI & { osmName?: string }
  /** Lifted popup state (FIX-109-07) */
  isPopupOpen?: boolean
  onPopupOpen?: () => void
  onPopupClose?: () => void
  offset?: MapMarkerOffset
}

export function POIMarker({
  poi,
  isPopupOpen,
  onPopupOpen = noop,
  onPopupClose = noop,
  offset,
}: POIMarkerProps) {
  const { t } = useTranslation("map")
  const [isHovered, setIsHovered] = useState(false)
  const markerRef = useRef<MarkerInstance | null>(null)
  // Wave 116 polish — see BuildingMarker + utils/stripMaplibreMarkerChrome.ts.
  useStripMaplibreMarkerChrome(markerRef)

  const colorVar = poiColorVar(poi.type)
  const Icon = getPoiIcon(poi.icon)

  const displayName = poi.i18nKey
    ? t(`poi.items.${poi.i18nKey}.name`)
    : (poi.osmName ?? t(`poi.categories.${poi.type}`))

  const yandexMapsUrl = `https://yandex.ru/maps/?pt=${poi.coords[1]},${poi.coords[0]}&z=17&l=map`

  return (
    <>
      <Marker
        ref={markerRef}
        longitude={poi.coords[1]}
        latitude={poi.coords[0]}
        anchor="center"
        offset={offset}
      >
        <div
          role="button"
          tabIndex={0}
          aria-label={`${displayName} — ${t(`poi.categories.${poi.type}`)}`}
          className={`map-poi-pin${isHovered ? " map-poi-pin--hover" : ""}`}
          style={
            {
              "--_poi-color": colorVar,
              minWidth: MAP_INTERACTIVE_TARGET_PX,
              minHeight: MAP_INTERACTIVE_TARGET_PX,
            } as React.CSSProperties
          }
          onPointerEnter={() => setIsHovered(true)}
          onPointerLeave={() => setIsHovered(false)}
          onClick={(e) => {
            e.stopPropagation()
            onPopupOpen()
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault()
              onPopupOpen()
            }
          }}
        >
          <Icon size={14} color="white" strokeWidth={2.5} />
        </div>
      </Marker>

      {/* Hover tooltip — name only */}
      {isHovered && !isPopupOpen && (
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
      {isPopupOpen && (
        <Popup
          longitude={poi.coords[1]}
          latitude={poi.coords[0]}
          anchor="bottom"
          offset={18}
          closeButton
          closeOnClick={false}
          onClose={onPopupClose}
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
