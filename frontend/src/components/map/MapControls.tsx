/**
 * MapControls.tsx — Premium map control panel.
 * Zoom, compass, pitch toggle, fullscreen, recenter.
 * Wave 103 — premium map control panel.
 */

import { useState, useCallback, useEffect } from "react"
import { useTranslation } from "react-i18next"
import { logError } from "@/app/logger"
import useMediaQuery from "@/hooks/useMediaQuery"
import {
  Plus,
  Minus,
  Compass,
  Box,
  Map as MapIcon,
  Maximize2,
  Minimize2,
  LocateFixed,
} from "lucide-react"
import type { MapRef } from "react-map-gl/maplibre"
import {
  CAMPUS_COORDINATES,
  CAMPUS_DETAIL_ZOOM,
  MAP_INTERACTIVE_TARGET_PX,
} from "@/constants/campus"

interface MapControlsProps {
  mapRef: React.MutableRefObject<MapRef | null>
}

type MapInstance = ReturnType<MapRef["getMap"]>

/**
 * Map controls are rendered before MapLibre has mounted (and can outlive it
 * during route transitions).  Normalising the absent map to a no-op instance
 * keeps every event handler total: a click during that short window is safe
 * and does not need a branch that can drift away from the operation itself.
 */
const NOOP_FULLSCREEN_CONTAINER = {
  requestFullscreen: () => Promise.resolve(),
} as unknown as HTMLElement

const NOOP_MAP_CONTAINER = {
  closest: () => NOOP_FULLSCREEN_CONTAINER,
} as unknown as HTMLElement

const NOOP_MAP = {
  zoomIn: () => undefined,
  zoomOut: () => undefined,
  easeTo: () => undefined,
  flyTo: () => undefined,
  getContainer: () => NOOP_MAP_CONTAINER,
} as unknown as MapInstance

const NOOP_MAP_REF = { getMap: () => NOOP_MAP } as unknown as MapRef

function resolveMap(mapRef: React.MutableRefObject<MapRef | null>) {
  return (mapRef.current ?? NOOP_MAP_REF).getMap() ?? NOOP_MAP
}

export function MapControls({ mapRef }: MapControlsProps) {
  const { t } = useTranslation("map")
  const [isFullscreen, setIsFullscreen] = useState(false)
  const [is3D, setIs3D] = useState(true) // starts with pitch 45
  /** Responsive icon sizing — matches CSS breakpoints in map.css (FIX-111-02) */
  const isMobile = useMediaQuery("(max-width: 640px)")
  const isSmall = useMediaQuery("(max-width: 380px), (max-height: 500px)")
  const iconSize = isSmall ? 12 : isMobile ? 14 : 16
  const targetStyle = { minWidth: MAP_INTERACTIVE_TARGET_PX, minHeight: MAP_INTERACTIVE_TARGET_PX }

  const zoomIn = useCallback(() => {
    const map = resolveMap(mapRef)
    map.zoomIn()
  }, [mapRef])
  const zoomOut = useCallback(() => {
    const map = resolveMap(mapRef)
    map.zoomOut()
  }, [mapRef])

  const resetNorth = useCallback(() => {
    const map = resolveMap(mapRef)
    map.easeTo({ bearing: 0, duration: 400 })
  }, [mapRef])

  const togglePitch = useCallback(() => {
    const newPitch = is3D ? 0 : 45
    const map = resolveMap(mapRef)
    map.easeTo({ pitch: newPitch, duration: 400 })
    setIs3D(!is3D)
  }, [mapRef, is3D])

  const recenter = useCallback(() => {
    const map = resolveMap(mapRef)
    map.flyTo({
      center: [CAMPUS_COORDINATES.lon, CAMPUS_COORDINATES.lat],
      zoom: CAMPUS_DETAIL_ZOOM,
      pitch: 45,
      bearing: 0,
      duration: 800,
    })
    setIs3D(true)
  }, [mapRef])

  /* FIX-111-07: Sync state when user exits fullscreen via Esc (bypasses button click) */
  useEffect(() => {
    const handler = () => setIsFullscreen(!!document.fullscreenElement)
    document.addEventListener("fullscreenchange", handler)
    return () => document.removeEventListener("fullscreenchange", handler)
  }, [])

  const toggleFullscreen = useCallback(() => {
    const map = resolveMap(mapRef)
    const mapContainer = map.getContainer() ?? NOOP_MAP_CONTAINER
    const container = mapContainer.closest(".map-card-matte") ?? NOOP_FULLSCREEN_CONTAINER

    if (!document.fullscreenElement) {
      container.requestFullscreen().catch(logError)
    } else {
      document.exitFullscreen().catch(logError)
    }
    // State sync handled by fullscreenchange listener (FIX-111-07)
  }, [mapRef])

  return (
    <div className="map-control-panel" role="group" aria-label={t("zoom.ariaLabel")}>
      {/* Zoom */}
      <button
        type="button"
        onClick={zoomIn}
        className="map-control-btn"
        aria-label={t("zoom.in")}
        style={targetStyle}
      >
        <Plus size={iconSize} />
      </button>
      <button
        type="button"
        onClick={zoomOut}
        className="map-control-btn"
        aria-label={t("zoom.out")}
        style={targetStyle}
      >
        <Minus size={iconSize} />
      </button>

      <div className="map-control-divider" />

      {/* Compass — reset north */}
      <button
        type="button"
        onClick={resetNorth}
        className="map-control-btn"
        aria-label={t("controls.compass")}
        style={targetStyle}
      >
        <Compass size={iconSize} />
      </button>

      {/* 3D / 2D toggle */}
      <button
        type="button"
        onClick={togglePitch}
        className="map-control-btn"
        aria-label={t("controls.pitchToggle")}
        style={targetStyle}
      >
        {is3D ? <MapIcon size={iconSize} /> : <Box size={iconSize} />}
      </button>

      <div className="map-control-divider" />

      {/* Recenter campus */}
      <button
        type="button"
        onClick={recenter}
        className="map-control-btn map-control-btn--accent"
        aria-label={t("zoom.reset")}
        style={targetStyle}
      >
        <LocateFixed size={iconSize} />
      </button>

      {/* Fullscreen */}
      <button
        type="button"
        onClick={toggleFullscreen}
        className="map-control-btn"
        aria-label={t("controls.fullscreen")}
        style={targetStyle}
      >
        {isFullscreen ? <Minimize2 size={iconSize} /> : <Maximize2 size={iconSize} />}
      </button>
    </div>
  )
}
