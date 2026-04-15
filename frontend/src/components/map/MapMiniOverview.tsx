/**
 * MapMiniOverview.tsx — Miniature overview map for the campus map page.
 *
 * Renders a second non-interactive MapLibre GL instance at a fixed zoom level
 * showing the full campus area. A teal dot indicates the main map's current
 * viewport center. Clicking the mini-map flies the main map to that location.
 *
 * Wave 108 — mini overview map for spatial context.
 */

import { useState, useEffect, useCallback } from "react"
import { Map } from "react-map-gl/maplibre"
import type { MapRef } from "react-map-gl/maplibre"
import { useTranslation } from "react-i18next"
import { CAMPUS_COORDINATES } from "@/constants/campus"

const STYLE_LIGHT = "https://tiles.openfreemap.org/styles/bright"
const STYLE_DARK = "https://tiles.openfreemap.org/styles/dark"

/** Fixed overview zoom — shows full campus with surrounding context. */
const OVERVIEW_ZOOM = 14

/** Pixel dimensions of the mini-map container. */
const CONTAINER_WIDTH = 140
const CONTAINER_HEIGHT = 100

/* Polling replaced with MapLibre move event (Wave 109 — PERF-109-01) */

interface MapMiniOverviewProps {
  mainMapRef: React.MutableRefObject<MapRef | null>
  isDark: boolean
  visible: boolean
}

/**
 * Convert geographic coordinates to pixel position within the mini-map.
 *
 * Uses a simple Mercator approximation relative to the mini-map's fixed
 * center and zoom level. Accurate enough for the small campus area.
 */
function geoToPixel(
  lng: number,
  lat: number,
  centerLng: number,
  centerLat: number,
  zoom: number,
  width: number,
  height: number,
): { x: number; y: number } {
  const scale = (256 / (2 * Math.PI)) * Math.pow(2, zoom)

  const lngToX = (l: number) => scale * ((l * Math.PI) / 180 + Math.PI)
  const latToY = (l: number) =>
    scale * (Math.PI - Math.log(Math.tan(Math.PI / 4 + (l * Math.PI) / 360)))

  const cx = lngToX(centerLng)
  const cy = latToY(centerLat)

  const px = lngToX(lng)
  const py = latToY(lat)

  return {
    x: width / 2 + (px - cx),
    y: height / 2 + (py - cy),
  }
}

/**
 * Inverse of geoToPixel — convert a pixel click position back to lng/lat.
 */
function pixelToGeo(
  px: number,
  py: number,
  centerLng: number,
  centerLat: number,
  zoom: number,
  width: number,
  height: number,
): { lng: number; lat: number } {
  const scale = (256 / (2 * Math.PI)) * Math.pow(2, zoom)

  const lngToX = (l: number) => scale * ((l * Math.PI) / 180 + Math.PI)
  const latToY = (l: number) =>
    scale * (Math.PI - Math.log(Math.tan(Math.PI / 4 + (l * Math.PI) / 360)))

  const cx = lngToX(centerLng)
  const cy = latToY(centerLat)

  const worldX = cx + (px - width / 2)
  const worldY = cy + (py - height / 2)

  const lng = ((worldX / scale - Math.PI) * 180) / Math.PI
  const lat = ((2 * Math.atan(Math.exp(Math.PI - worldY / scale)) - Math.PI / 2) * 180) / Math.PI

  return { lng, lat }
}

/**
 * Non-interactive mini-map showing the full campus with a viewport indicator dot.
 *
 * @param mainMapRef  Ref to the primary MapLibre GL map instance
 * @param isDark      Whether dark mode is active
 * @param visible     Controls visibility — returns null when false
 */
export function MapMiniOverview({ mainMapRef, isDark, visible }: MapMiniOverviewProps) {
  const { t } = useTranslation("map")
  const [dotPos, setDotPos] = useState<{ x: number; y: number } | null>(null)

  /** Update dot on main map move events instead of polling (PERF-109-01). */
  useEffect(() => {
    if (!visible) return

    const map = mainMapRef.current
    if (!map) return

    function updateDot() {
      const center = mainMapRef.current?.getCenter()
      if (!center) return

      const pos = geoToPixel(
        center.lng,
        center.lat,
        CAMPUS_COORDINATES.lon,
        CAMPUS_COORDINATES.lat,
        OVERVIEW_ZOOM,
        CONTAINER_WIDTH,
        CONTAINER_HEIGHT,
      )
      setDotPos(pos)
    }

    // Initial position
    updateDot()

    // Subscribe to map movement — fires only when viewport changes
    const mapInstance = map.getMap()
    mapInstance.on("move", updateDot)

    return () => {
      mapInstance.off("move", updateDot)
    }
  }, [visible, mainMapRef])

  /** Click handler — fly main map to the clicked location. */
  const handleClick = useCallback(
    (e: React.MouseEvent<HTMLDivElement>) => {
      const rect = e.currentTarget.getBoundingClientRect()
      const px = e.clientX - rect.left
      const py = e.clientY - rect.top

      const { lng, lat } = pixelToGeo(
        px,
        py,
        CAMPUS_COORDINATES.lon,
        CAMPUS_COORDINATES.lat,
        OVERVIEW_ZOOM,
        CONTAINER_WIDTH,
        CONTAINER_HEIGHT,
      )

      mainMapRef.current?.flyTo({ center: [lng, lat], duration: 800 })
    },
    [mainMapRef],
  )

  if (!visible) return null

  return (
    <div
      className="map-mini-overview"
      style={{
        position: "absolute",
        width: CONTAINER_WIDTH,
        height: CONTAINER_HEIGHT,
        borderRadius: 10,
        overflow: "hidden",
        cursor: "pointer",
      }}
      onClick={handleClick}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault()
          // Center click — recenter to campus
          mainMapRef.current?.flyTo({
            center: [CAMPUS_COORDINATES.lon, CAMPUS_COORDINATES.lat],
            duration: 800,
          })
        }
      }}
      role="button"
      tabIndex={0}
      aria-label={t("a11y.miniMapLabel", { defaultValue: "Campus overview — click to recenter" })}
    >
      <Map
        mapStyle={isDark ? STYLE_DARK : STYLE_LIGHT}
        initialViewState={{
          longitude: CAMPUS_COORDINATES.lon,
          latitude: CAMPUS_COORDINATES.lat,
          zoom: OVERVIEW_ZOOM,
          pitch: 0,
          bearing: 0,
        }}
        style={{ width: "100%", height: "100%" }}
        interactive={false}
        attributionControl={false}
        reuseMaps
      />

      {/* Viewport indicator dot */}
      {dotPos && (
        <div
          aria-hidden="true"
          style={{
            position: "absolute",
            left: dotPos.x - 3,
            top: dotPos.y - 3,
            width: 6,
            height: 6,
            borderRadius: "50%",
            backgroundColor: "var(--map-accent)",
            boxShadow: "0 0 4px var(--map-accent)",
            pointerEvents: "none",
          }}
        />
      )}
    </div>
  )
}
