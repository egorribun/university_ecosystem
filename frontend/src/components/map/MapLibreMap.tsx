/**
 * MapLibreMap.tsx — Premium geographic map with MapLibre GL + OpenFreeMap.
 *
 * WebGL-powered: 3D buildings (generic + custom campus colors), sky, fog,
 * walking paths, cinematic camera intro, premium markers.
 *
 * Wave 100 — Leaflet → MapLibre; Wave 102-103 — premium visual masterpiece.
 * Wave 107 — reduced-motion, sky dedup, extrusion fix, timeout cleanup, POI perf.
 */

import { useState, useEffect, useMemo, useCallback, useRef } from "react"
import { Map, Layer } from "react-map-gl/maplibre"
import type { MapRef, LayerProps } from "react-map-gl/maplibre"
import { useTranslation } from "react-i18next"
import { CAMPUS_COORDINATES } from "@/constants/campus"
import { getCampusBuildings, type BuildingId, type MapCategory } from "@/data/campusBuildings"
import { CAMPUS_POIS, type CampusPOI } from "@/data/campusPOI"
import { useOverpassPOI } from "@/hooks/useOverpassPOI"
import { BuildingMarker } from "./BuildingMarker"
import { POIMarker } from "./POIMarker"
import { POIControls } from "./POIControls"
import { MapControls } from "./MapControls"
import { WeatherParticles } from "./WeatherParticles"
import { EventMarker } from "./EventMarker"
import { MapMiniOverview } from "./MapMiniOverview"
import type { WeatherCondition } from "@/utils/weatherCodes"
import type { MapEvent } from "@/hooks/useMapEvents"
import "maplibre-gl/dist/maplibre-gl.css"

/* ── Tile styles ── */
const STYLE_LIGHT = "https://tiles.openfreemap.org/styles/bright"
const STYLE_DARK = "https://tiles.openfreemap.org/styles/dark"

/* ── Generic 3D buildings from vector tiles (gray, surrounding) ── */
const GENERIC_BUILDINGS_LAYER: LayerProps = {
  id: "3d-buildings-generic",
  type: "fill-extrusion" as const,
  source: "openmaptiles",
  "source-layer": "building",
  minzoom: 15,
  paint: {
    "fill-extrusion-color": [
      "interpolate",
      ["linear"],
      ["get", "render_height"],
      0, "#d1d5db",   // ≈ --color-gray-300
      50, "#9ca3af",  // ≈ --color-gray-400
      100, "#6b7280", // ≈ --color-gray-500
    ],
    "fill-extrusion-height": [
      "interpolate",
      ["linear"],
      ["zoom"],
      15, 0,
      16, ["get", "render_height"],
    ],
    // render_min_height used directly — minzoom: 15 already gates visibility
    "fill-extrusion-base": ["get", "render_min_height"],
    "fill-extrusion-opacity": 0.5,
  },
}

/**
 * Sky/fog configuration — MapLibre GL doesn't support CSS variables in paint
 * properties, so hex values are used with token equivalents documented.
 * Wave 108: period-aware sky colors (dawn=warm, dusk=orange, night=deep navy).
 */
type TimePeriod = "dawn" | "morning" | "afternoon" | "dusk" | "night"

const SKY_PRESETS: Record<TimePeriod, { sky: string; horizon: string; fog: string }> = {
  dawn:      { sky: "#fbbf24", horizon: "#fca5a5", fog: "#fef3c7" }, // warm amber-pink sunrise
  morning:   { sky: "#87ceeb", horizon: "#f0f4ff", fog: "#e8edf5" }, // default bright blue
  afternoon: { sky: "#87ceeb", horizon: "#f0f4ff", fog: "#e8edf5" }, // same as morning
  dusk:      { sky: "#f59e0b", horizon: "#a78bfa", fog: "#fde68a" }, // orange-violet sunset
  night:     { sky: "#0f172a", horizon: "#1e293b", fog: "#1e293b" }, // deep navy
}

const SKY_DARK: { sky: string; horizon: string; fog: string } = {
  sky: "#0f172a", horizon: "#1e293b", fog: "#1e293b",
}

function getSkyConfig(isDark: boolean, period?: TimePeriod) {
  // Dark mode always uses deep navy regardless of period
  const preset = isDark ? SKY_DARK : SKY_PRESETS[period ?? "afternoon"]
  return {
    "sky-color": preset.sky,
    "sky-horizon-blend": 0.3,
    "horizon-color": preset.horizon,
    "horizon-fog-blend": 0.8,
    "fog-color": preset.fog,
    "fog-ground-blend": 0.5,
  }
}

interface MapLibreMapProps {
  selectedBuilding: BuildingId | null
  activeCategory: MapCategory
  highlightedBuilding: BuildingId | null
  onSelectBuilding: (letter: BuildingId) => void
  mapRef?: React.MutableRefObject<MapRef | null>
  isDark?: boolean
  timePeriod?: TimePeriod
  weatherCondition?: WeatherCondition
  showEvents?: boolean
  mapEvents?: MapEvent[]
  onToggleEvents?: () => void
}

export function MapLibreMapComponent({
  selectedBuilding,
  activeCategory,
  highlightedBuilding,
  onSelectBuilding,
  mapRef,
  isDark,
  timePeriod,
  weatherCondition,
  showEvents,
  mapEvents,
  onToggleEvents,
}: MapLibreMapProps) {
  const { i18n } = useTranslation("map")
  const hasAnimatedIntro = useRef(false)
  const introTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const [currentZoom, setCurrentZoom] = useState(16)

  const buildings = useMemo(
    () => getCampusBuildings(i18n.resolvedLanguage ?? i18n.language),
    [i18n.resolvedLanguage, i18n.language],
  )

  const filteredBuildings = useMemo(() => {
    if (activeCategory === "all") return buildings
    return buildings.filter((b) => b.tags.includes(activeCategory))
  }, [buildings, activeCategory])

  /* ── Gentle pan to selected building (no zoom/pitch jump) ── */
  useEffect(() => {
    if (!selectedBuilding || !mapRef?.current) return
    const building = buildings.find((b) => b.letter === selectedBuilding)
    if (!building) return

    mapRef.current.easeTo({
      center: [building.geoCoords[1], building.geoCoords[0]],
      duration: 600,
    })
  }, [selectedBuilding, buildings, mapRef])

  /* ── POI state ── */
  const { pois: overpassPois, isLoading: poisLoading, loadMore, hasLoaded } = useOverpassPOI()
  const [poiCategory, setPoiCategory] = useState<string>("all")

  /* ── Merge hardcoded + Overpass POIs with O(n) spatial dedup ── */
  const allPois = useMemo(() => {
    const base: CampusPOI[] = [...CAMPUS_POIS]
    if (hasLoaded) {
      // Spatial hash for O(n) dedup — key = rounded lat/lng grid cell
      const seen = new Set(
        base.map((bp) =>
          `${Math.round(bp.coords[0] / 0.0005)}_${Math.round(bp.coords[1] / 0.0005)}`,
        ),
      )
      for (const op of overpassPois) {
        const key = `${Math.round(op.coords[0] / 0.0005)}_${Math.round(op.coords[1] / 0.0005)}`
        if (!seen.has(key)) {
          seen.add(key)
          base.push(op)
        }
      }
    }
    if (poiCategory === "all") return base
    return base.filter((p) => p.type === poiCategory)
  }, [overpassPois, hasLoaded, poiCategory])

  const mapStyle = isDark ? STYLE_DARK : STYLE_LIGHT

  /* ── Cinematic intro + sky/fog setup on map load ── */
  const onMapLoad = useCallback(() => {
    const map = mapRef?.current?.getMap()
    if (!map) return

    map.setSky(getSkyConfig(!!isDark, timePeriod))

    // Cinematic intro — fly from high altitude (skip if reduced-motion)
    if (!hasAnimatedIntro.current) {
      hasAnimatedIntro.current = true
      const prefersReduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches

      if (prefersReduced) {
        // Jump directly to final position — no animation
        map.jumpTo({
          center: [CAMPUS_COORDINATES.lon, CAMPUS_COORDINATES.lat],
          zoom: 16,
          pitch: 45,
          bearing: 0,
        })
      } else {
        map.jumpTo({
          center: [CAMPUS_COORDINATES.lon, CAMPUS_COORDINATES.lat],
          zoom: 13,
          pitch: 0,
          bearing: -20,
        })
        introTimeoutRef.current = setTimeout(() => {
          // Guard against unmount during delay
          if (!mapRef?.current) return
          map.flyTo({
            center: [CAMPUS_COORDINATES.lon, CAMPUS_COORDINATES.lat],
            zoom: 16,
            pitch: 45,
            bearing: 0,
            duration: 2500,
            essential: true,
          })
        }, 300)
      }
    }
  }, [mapRef, isDark])

  /* ── Cleanup cinematic intro timeout on unmount ── */
  useEffect(() => {
    return () => {
      if (introTimeoutRef.current) {
        clearTimeout(introTimeoutRef.current)
        introTimeoutRef.current = null
      }
    }
  }, [])

  /* ── Update sky on theme/time-of-day change ── */
  useEffect(() => {
    const map = mapRef?.current?.getMap()
    if (!map || !map.loaded()) return
    map.setSky(getSkyConfig(!!isDark, timePeriod))
  }, [isDark, timePeriod, mapRef])

  return (
    <div className="maplibre-map-wrapper relative h-full min-h-[inherit]">
      <Map
        ref={mapRef}
        initialViewState={{
          longitude: CAMPUS_COORDINATES.lon,
          latitude: CAMPUS_COORDINATES.lat,
          zoom: 16,
          pitch: 45,
          bearing: 0,
        }}
        mapStyle={mapStyle}
        style={{ width: "100%", height: "100%", minHeight: "inherit", borderRadius: 12 }}
        reuseMaps
        onLoad={onMapLoad}
        onZoom={(e) => setCurrentZoom(e.viewState.zoom)}
        maxPitch={70}
      >
        {/* Generic 3D buildings (gray, surrounding area) */}
        <Layer {...GENERIC_BUILDINGS_LAYER} />

        {/* Building markers */}
        {filteredBuildings.map((building, index) => (
          <BuildingMarker
            key={building.letter}
            building={building}
            index={index}
            isSelected={selectedBuilding === building.letter}
            isHighlighted={highlightedBuilding === building.letter}
            onClick={onSelectBuilding}
          />
        ))}

        {/* POI markers */}
        {allPois.map((poi) => (
          <POIMarker key={poi.id} poi={poi} />
        ))}

        {/* Event markers */}
        {showEvents && mapEvents?.map((event) => (
          <EventMarker key={event.id} event={event} />
        ))}
      </Map>

      {/* Weather particle overlay — above map, below markers */}
      {weatherCondition && (
        <WeatherParticles condition={weatherCondition} isDark={!!isDark} />
      )}

      {/* Premium map controls — bottom right */}
      <div className="absolute bottom-4 right-4 z-10">
        {mapRef && <MapControls mapRef={mapRef} />}
      </div>

      {/* POI controls overlay — bottom left */}
      <div className="absolute bottom-4 left-4 z-[500]">
        <POIControls
          activeCategory={poiCategory}
          onCategoryChange={setPoiCategory}
          onLoadMore={loadMore}
          isLoading={poisLoading}
          hasLoadedMore={hasLoaded}
          showEvents={!!showEvents}
          onToggleEvents={onToggleEvents ?? (() => {})}
        />
      </div>

      {/* Mini-map overview — visible when zoomed in */}
      {mapRef && (
        <MapMiniOverview
          mainMapRef={mapRef}
          isDark={!!isDark}
          visible={currentZoom > 16}
        />
      )}
    </div>
  )
}

export default MapLibreMapComponent
