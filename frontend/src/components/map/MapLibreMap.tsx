/**
 * MapLibreMap.tsx — Premium geographic map with MapLibre GL + OpenFreeMap.
 *
 * WebGL-powered: 3D buildings (generic + custom campus colors), sky, fog,
 * walking paths, cinematic camera intro, premium markers.
 *
 * Wave 100 — Leaflet → MapLibre; Wave 102-103 — premium visual masterpiece.
 * Wave 107 — reduced-motion, sky dedup, extrusion fix, timeout cleanup, POI perf.
 */

import { useState, useEffect, useMemo, useRef } from "react"
import { Map, Layer } from "react-map-gl/maplibre"
import type { MapRef, LayerProps } from "react-map-gl/maplibre"
import { useTranslation } from "react-i18next"
import { CAMPUS_COORDINATES } from "@/constants/campus"
import { getCampusBuildings, type BuildingId, type MapCategory } from "@/data/campusBuildings"
import { CAMPUS_POIS } from "@/data/campusPOI"
import { BuildingMarker } from "./BuildingMarker"
import { POIMarker } from "./POIMarker"
import { MapControls } from "./MapControls"
import { WeatherParticles } from "./WeatherParticles"
import { EventMarker } from "./EventMarker"
import type { WeatherCondition } from "@/utils/weatherCodes"
import type { MapEvent } from "@/hooks/useMapEvents"
import "maplibre-gl/dist/maplibre-gl.css"

/* ── Tile styles ── */
const STYLE_LIGHT = "https://tiles.openfreemap.org/styles/bright"
const STYLE_DARK = "https://tiles.openfreemap.org/styles/dark"

/**
 * Generic 3D buildings from vector tiles (gray, surrounding).
 * NOTE: MapLibre GL paint properties are WebGL-based — they cannot read CSS
 * custom properties. Hex values here are intentional, with token equivalents
 * documented in comments for design system traceability.
 */
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
      0, "#d1d5db",   // --color-gray-300
      50, "#9ca3af",  // --color-gray-400
      100, "#6b7280", // --color-gray-500
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
  onDeselectBuilding: () => void
  mapRef?: React.MutableRefObject<MapRef | null>
  isDark?: boolean
  timePeriod?: TimePeriod
  weatherCondition?: WeatherCondition
  mapEvents?: MapEvent[]
}

export function MapLibreMapComponent({
  selectedBuilding,
  activeCategory,
  highlightedBuilding,
  onSelectBuilding,
  onDeselectBuilding,
  mapRef,
  isDark,
  timePeriod,
  weatherCondition,
  mapEvents,
}: MapLibreMapProps) {
  const { t, i18n } = useTranslation("map")
  const hasAnimatedIntro = useRef(false)
  const introTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  /** Single active popup — only one marker popup open at a time (FIX-109-07). */
  const [activePopupId, setActivePopupId] = useState<string | null>(null)

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

  /* ── POI data — hardcoded campus POIs (Overpass integration removed Wave 110) ── */

  /** Event counts per building — used for indicator badges on markers. */
  const eventCountByBuilding = useMemo(() => {
    const counts: Record<string, number> = {}
    for (const evt of mapEvents ?? []) {
      counts[evt.buildingId] = (counts[evt.buildingId] ?? 0) + 1
    }
    return counts
  }, [mapEvents])

  const mapStyle = isDark ? STYLE_DARK : STYLE_LIGHT

  /**
   * Cinematic intro + sky/fog + canvas resize — all in one rAF polling loop.
   *
   * WHY NOT onLoad: MapLibre GL's `load` is a one-shot event. In React 18
   * StrictMode, the component mounts twice: the `load` event can fire during
   * the brief unmount gap between mounts, and the second mount's onLoad prop
   * never receives it. Polling via rAF avoids this entirely — it checks
   * map.loaded() every frame until true, regardless of event timing.
   *
   * Handles all cases:
   * - Fresh load: polls ~1-3s until tiles ready → intro animation
   * - StrictMode remount: map already loaded from first mount → runs on first frame
   * - Navigation back (reuseMaps): map at final position → flyTo is a no-op
   */
  useEffect(() => {
    let raf: number
    let cancelled = false

    const check = () => {
      if (cancelled) return
      const map = mapRef?.current?.getMap()

      if (!map || !map.loaded()) {
        // Map not ready yet — keep polling
        raf = requestAnimationFrame(check)
        return
      }

      // ── Map is ready ──

      // Canvas resize (FIX-109-01: fixes stale drag handlers after View Transition)
      map.resize()

      // Sky/fog atmosphere
      map.setSky(getSkyConfig(!!isDark, timePeriod))

      // Cinematic intro — only once per component lifetime
      if (!hasAnimatedIntro.current) {
        hasAnimatedIntro.current = true
        const prefersReduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches

        if (prefersReduced) {
          map.jumpTo({
            center: [CAMPUS_COORDINATES.lon, CAMPUS_COORDINATES.lat],
            zoom: 16,
            pitch: 45,
            bearing: 0,
          })
        } else {
          introTimeoutRef.current = setTimeout(() => {
            if (cancelled) return
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
    }

    raf = requestAnimationFrame(check)

    return () => {
      cancelled = true
      cancelAnimationFrame(raf)
      if (introTimeoutRef.current) {
        clearTimeout(introTimeoutRef.current)
        introTimeoutRef.current = null
      }
    }
  }, [mapRef, isDark, timePeriod])

  /* ── Update sky on theme/time-of-day change ── */
  useEffect(() => {
    const map = mapRef?.current?.getMap()
    if (!map || !map.loaded()) return
    map.setSky(getSkyConfig(!!isDark, timePeriod))
  }, [isDark, timePeriod, mapRef])

  return (
    <div
      className="maplibre-map-wrapper relative h-full min-h-[inherit]"
      role="application"
      aria-label={t("a11y.mapContainer")}
    >
      <Map
        ref={mapRef}
        initialViewState={{
          longitude: CAMPUS_COORDINATES.lon,
          latitude: CAMPUS_COORDINATES.lat,
          zoom: 13,
          pitch: 0,
          bearing: -20,
        }}
        mapStyle={mapStyle}
        style={{ width: "100%", height: "100%", minHeight: "inherit", borderRadius: 12 }}
        reuseMaps
        attributionControl={false}
        onClick={() => { onDeselectBuilding(); setActivePopupId(null) }}
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
            isPopupOpen={activePopupId === `bldg-${building.letter}`}
            onPopupOpen={() => setActivePopupId(`bldg-${building.letter}`)}
            onPopupClose={() => setActivePopupId(null)}
            eventCount={eventCountByBuilding[building.letter] ?? 0}
          />
        ))}

        {/* POI markers */}
        {CAMPUS_POIS.map((poi) => (
          <POIMarker
            key={poi.id}
            poi={poi}
            isPopupOpen={activePopupId === `poi-${poi.id}`}
            onPopupOpen={() => { setActivePopupId(`poi-${poi.id}`); onDeselectBuilding() }}
            onPopupClose={() => setActivePopupId(null)}
          />
        ))}

        {/* Event markers — always visible (FIX-109-11) */}
        {mapEvents?.map((event) => (
          <EventMarker
            key={event.id}
            event={event}
            isPopupOpen={activePopupId === `evt-${event.id}`}
            onPopupOpen={() => { setActivePopupId(`evt-${event.id}`); onDeselectBuilding() }}
            onPopupClose={() => setActivePopupId(null)}
          />
        ))}
      </Map>

      {/* Weather particle overlay — above map, below markers */}
      {weatherCondition && (
        <WeatherParticles condition={weatherCondition} isDark={!!isDark} />
      )}

      {/* Premium map controls — mobile: centered bottom strip, desktop: right column.
          Controls stay at bottom:12px — mobile bottom sheet (fixed z-50) overlays them naturally. */}
      <div
        className="absolute z-10 map-controls-positioner"
        style={{ bottom: 12 }}
      >
        {mapRef && <MapControls mapRef={mapRef} />}
      </div>

      {/* Minimal OSM attribution — replaces built-in widget */}
      <div className="absolute bottom-1 left-1 text-[9px] leading-none opacity-40 pointer-events-auto z-[1]">
        <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer" className="hover:opacity-80" style={{ color: "var(--text-tertiary)" }}>
          © OpenStreetMap
        </a>
      </div>
    </div>
  )
}

export default MapLibreMapComponent
