/**
 * MapLibreMap.tsx — Premium geographic map with MapLibre GL + OpenFreeMap.
 *
 * WebGL-powered: 3D buildings (generic + custom campus colors), sky, fog,
 * walking paths, cinematic camera intro, premium markers.
 *
 * Wave 100 — Leaflet → MapLibre; Wave 102-103 — premium visual masterpiece.
 * Wave 107 — reduced-motion, sky dedup, extrusion fix, timeout cleanup, POI perf.
 */

import { useState, useEffect, useMemo, useRef, useCallback } from "react"
import { Map, Layer } from "react-map-gl/maplibre"
import type { MapRef, LayerProps } from "react-map-gl/maplibre"
import { useTranslation } from "react-i18next"
import { CAMPUS_COORDINATES, CAMPUS_DETAIL_ZOOM } from "@/constants/campus"
import { getCampusBuildings, type BuildingId, type MapCategory } from "@/data/campusBuildings"
import { CAMPUS_POIS } from "@/data/campusPOI"
import type { MapViewport } from "@/features/map/schema"
import { BuildingMarker } from "./BuildingMarker"
import { POIMarker } from "./POIMarker"
import { MapControls } from "./MapControls"
import { WeatherParticles } from "./WeatherParticles"
import { EventMarker } from "./EventMarker"
import type { WeatherCondition } from "@/utils/weatherCodes"
import type { MapEvent } from "@/hooks/useMapEvents"
import { isLowPowerDevice } from "@/utils/deviceCapabilities"
import {
  layoutMapMarkerOffsets,
  layoutProjectedMapMarkerOffsets,
  type MapMarkerCollisionItem,
  type ScreenPoint,
} from "@/features/map/markerCollisionLayout"
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
      0,
      "#d1d5db", // --color-gray-300
      50,
      "#9ca3af", // --color-gray-400
      100,
      "#6b7280", // --color-gray-500
    ],
    "fill-extrusion-height": [
      "interpolate",
      ["linear"],
      ["zoom"],
      15,
      0,
      16,
      ["get", "render_height"],
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
  dawn: { sky: "#fbbf24", horizon: "#fca5a5", fog: "#fef3c7" }, // warm amber-pink sunrise
  morning: { sky: "#87ceeb", horizon: "#f0f4ff", fog: "#e8edf5" }, // default bright blue
  afternoon: { sky: "#87ceeb", horizon: "#f0f4ff", fog: "#e8edf5" }, // same as morning
  dusk: { sky: "#f59e0b", horizon: "#a78bfa", fog: "#fde68a" }, // orange-violet sunset
  night: { sky: "#0f172a", horizon: "#1e293b", fog: "#1e293b" }, // deep navy
}

function getSkyConfig(isDark: boolean, period?: TimePeriod) {
  // Dark mode always uses deep navy regardless of period
  const preset = isDark ? SKY_PRESETS.night : SKY_PRESETS[period ?? "afternoon"]
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
  /** Wave 120 SW5 — restored viewport from URL `?z/lat/lng/p/b` (parsed
   *  upstream by MapFeature). When non-null, skips the cinematic intro
   *  and jumps straight to this viewport. */
  urlInitialViewport?: MapViewport | null
  /** Wave 120 SW5 — fires after pan/zoom/rotate/pitch settle. MapFeature
   *  debounces the URL write (~500ms) so rapid panning doesn't spam history. */
  onMapMoveEnd?: (state: {
    zoom: number
    latitude: number
    longitude: number
    pitch: number
    bearing: number
  }) => void
}

export function MapLibreMapComponent({
  selectedBuilding,
  activeCategory,
  highlightedBuilding,
  onSelectBuilding,
  onDeselectBuilding,
  mapRef,
  isDark = false,
  timePeriod,
  weatherCondition,
  mapEvents,
  urlInitialViewport,
  onMapMoveEnd,
}: MapLibreMapProps) {
  const { t, i18n } = useTranslation("map")
  // The cinematic intro is decorative work on top of MapLibre's already
  // expensive WebGL/style bootstrap. Respect the same explicit constrained
  // device signals used by weather particles so low-power/Save-Data clients
  // get an immediate usable viewport instead of a long-running camera tween.
  const lowPowerDevice = isLowPowerDevice()
  const hasAnimatedIntro = useRef(false)
  const introTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  /** Single active popup — only one marker popup open at a time (FIX-109-07). */
  const [activePopupId, setActivePopupId] = useState<string | null>(null)
  /** Wave 120 SW5: latches when URL sync should fire. Programmatic moves
   *  during cinematic intro (or building easeTo before any user input) must
   *  NOT write to URL — only user-initiated panning/zooming should. After
   *  the first user-initiated move, all subsequent moves (including
   *  programmatic easeTo for building selection) sync to URL since they
   *  represent user intent. */
  const enableUrlSyncRef = useRef(!!urlInitialViewport)
  const [projectedMarkerLayout, setProjectedMarkerLayout] = useState<{
    markers: readonly MapMarkerCollisionItem[]
    points: ReadonlyMap<string, ScreenPoint>
  } | null>(null)

  const buildings = useMemo(
    () => getCampusBuildings(i18n.resolvedLanguage ?? i18n.language),
    [i18n.resolvedLanguage, i18n.language]
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
    if (mapEvents) {
      for (const evt of mapEvents) {
        counts[evt.buildingId] = (counts[evt.buildingId] ?? 0) + 1
      }
    }
    return counts
  }, [mapEvents])

  const collisionMarkers = useMemo<readonly MapMarkerCollisionItem[]>(
    () => [
      ...buildings.map((building) => ({
        id: `building-${building.letter}`,
        latitude: building.geoCoords[0],
        longitude: building.geoCoords[1],
        width: 44,
        height: 50,
        anchor: "bottom" as const,
      })),
      ...CAMPUS_POIS.map((poi) => ({
        id: `poi-${poi.id}`,
        latitude: poi.coords[0],
        longitude: poi.coords[1],
        width: 44,
        height: 44,
        anchor: "center" as const,
      })),
      ...(mapEvents ?? []).map((event) => ({
        id: `event-${event.id}`,
        latitude: event.geoCoords[0],
        longitude: event.geoCoords[1],
        width: 44,
        height: 45,
        anchor: "bottom" as const,
      })),
    ],
    [buildings, mapEvents]
  )

  const markerOffsets = useMemo(
    () =>
      projectedMarkerLayout?.markers === collisionMarkers
        ? layoutProjectedMapMarkerOffsets(collisionMarkers, projectedMarkerLayout.points)
        : layoutMapMarkerOffsets(collisionMarkers),
    [collisionMarkers, projectedMarkerLayout]
  )

  const updateCollisionProjection = useCallback(
    (map: ReturnType<MapRef["getMap"]>) => {
      const nextPoints = new globalThis.Map<string, ScreenPoint>()
      for (const marker of collisionMarkers) {
        const point = map.project([marker.longitude, marker.latitude])
        nextPoints.set(marker.id, { x: point.x, y: point.y })
      }
      setProjectedMarkerLayout({ markers: collisionMarkers, points: nextPoints })
    },
    [collisionMarkers]
  )

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
   * - Navigation back: a fresh, fully-owned instance restores the URL viewport
   *
   * The map is intentionally not placed in react-map-gl's global reuse pool:
   * unmount must release WebGL workers/listeners instead of retaining them.
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
      updateCollisionProjection(map)

      // Sky/fog atmosphere
      map.setSky(getSkyConfig(isDark, timePeriod))

      // Cinematic intro — only once per component lifetime.
      // Wave 120 SW5: if URL provided a saved viewport, jumpTo it instead
      // of running the cinematic intro (the URL viewport already matches
      // what we set in initialViewState; jumpTo guarantees parity even if
      // tiles loaded slowly). Otherwise, run the intro as before.
      if (!hasAnimatedIntro.current) {
        hasAnimatedIntro.current = true
        const prefersReduced =
          lowPowerDevice || window.matchMedia("(prefers-reduced-motion: reduce)").matches

        if (urlInitialViewport) {
          map.jumpTo({
            center: [urlInitialViewport.longitude, urlInitialViewport.latitude],
            zoom: urlInitialViewport.zoom,
            pitch: urlInitialViewport.pitch,
            bearing: urlInitialViewport.bearing,
          })
        } else if (prefersReduced) {
          map.jumpTo({
            center: [CAMPUS_COORDINATES.lon, CAMPUS_COORDINATES.lat],
            zoom: CAMPUS_DETAIL_ZOOM,
            pitch: 45,
            bearing: 0,
          })
        } else {
          introTimeoutRef.current = setTimeout(() => {
            if (cancelled) return
            map.flyTo({
              center: [CAMPUS_COORDINATES.lon, CAMPUS_COORDINATES.lat],
              zoom: CAMPUS_DETAIL_ZOOM,
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
  }, [mapRef, isDark, lowPowerDevice, timePeriod, urlInitialViewport, updateCollisionProjection])

  useEffect(() => {
    const map = mapRef?.current?.getMap()
    if (map?.loaded()) updateCollisionProjection(map)
  }, [mapRef, updateCollisionProjection])

  /* ── URL-sync onMoveEnd handler (Wave 120 SW5) ── */
  const handleMoveEnd = useCallback(
    (evt: { originalEvent?: unknown }) => {
      const map = mapRef?.current?.getMap()
      if (!map) return
      const nextCamera = {
        zoom: map.getZoom(),
        pitch: map.getPitch(),
        bearing: map.getBearing(),
      }
      updateCollisionProjection(map)

      // Skip programmatic moves until first user interaction (intro / sky setup).
      // After first user-initiated move, originalEvent is set on subsequent
      // user events; we latch enableUrlSyncRef so even programmatic easeTo
      // (e.g. building click) fires URL sync afterward.
      if (!enableUrlSyncRef.current) {
        if (evt.originalEvent) {
          enableUrlSyncRef.current = true
        } else {
          return
        }
      }
      const center = map.getCenter()
      onMapMoveEnd?.({
        zoom: nextCamera.zoom,
        latitude: center.lat,
        longitude: center.lng,
        pitch: nextCamera.pitch,
        bearing: nextCamera.bearing,
      })
    },
    [mapRef, onMapMoveEnd, updateCollisionProjection]
  )

  /* ── Update sky on theme/time-of-day change ── */
  useEffect(() => {
    const map = mapRef?.current?.getMap()
    if (!map || !map.loaded()) return
    map.setSky(getSkyConfig(isDark, timePeriod))
  }, [isDark, timePeriod, mapRef])

  return (
    <div
      className="maplibre-map-wrapper relative h-full min-h-[inherit]"
      style={{ overscrollBehavior: "contain" }}
      role="application"
      aria-label={t("a11y.mapContainer")}
      aria-roledescription={t("a11y.mapRoleDescription")}
    >
      {/*
        Wave 112 SW4 — sr-only keyboard instructions. WCAG 2.1.1 +
        SC 4.1.2: the application role removes implicit interaction model,
        so we MUST surface available keys to screen reader users. Visible
        in DOM only for AT; sighted users see the dedicated `?` overlay.
      */}
      <p className="sr-only">{t("a11y.mapKeyboardHint")}</p>
      <Map
        ref={mapRef}
        initialViewState={
          urlInitialViewport
            ? {
                longitude: urlInitialViewport.longitude,
                latitude: urlInitialViewport.latitude,
                zoom: urlInitialViewport.zoom,
                pitch: urlInitialViewport.pitch,
                bearing: urlInitialViewport.bearing,
              }
            : {
                longitude: CAMPUS_COORDINATES.lon,
                latitude: CAMPUS_COORDINATES.lat,
                zoom: CAMPUS_DETAIL_ZOOM,
                pitch: 0,
                bearing: -20,
              }
        }
        mapStyle={mapStyle}
        style={{ width: "100%", height: "100%", minHeight: "inherit", borderRadius: 12 }}
        attributionControl={false}
        onClick={() => {
          onDeselectBuilding()
          setActivePopupId(null)
        }}
        onMoveEnd={handleMoveEnd}
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
            offset={markerOffsets.get(`building-${building.letter}`)}
          />
        ))}

        {/* POI markers */}
        {CAMPUS_POIS.map((poi) => (
          <POIMarker
            key={poi.id}
            poi={poi}
            isPopupOpen={activePopupId === `poi-${poi.id}`}
            onPopupOpen={() => {
              setActivePopupId(`poi-${poi.id}`)
              onDeselectBuilding()
            }}
            onPopupClose={() => setActivePopupId(null)}
            offset={markerOffsets.get(`poi-${poi.id}`)}
          />
        ))}

        {/* Event markers — always visible (FIX-109-11) */}
        {mapEvents?.map((event) => (
          <EventMarker
            key={event.id}
            event={event}
            isPopupOpen={activePopupId === `evt-${event.id}`}
            onPopupOpen={() => {
              setActivePopupId(`evt-${event.id}`)
              onDeselectBuilding()
            }}
            onPopupClose={() => setActivePopupId(null)}
            offset={markerOffsets.get(`event-${event.id}`)}
          />
        ))}
      </Map>

      {/* Weather particle overlay — above map, below markers */}
      {weatherCondition && <WeatherParticles condition={weatherCondition} isDark={isDark} />}

      {/* Premium map controls — mobile: centered bottom strip, desktop: right column.
          Controls stay at bottom:12px — mobile bottom sheet (fixed z-50) overlays them naturally. */}
      <div className="absolute z-10 map-controls-positioner" style={{ bottom: 12 }}>
        {mapRef && <MapControls mapRef={mapRef} />}
      </div>

      {/* Minimal OSM attribution — replaces built-in widget */}
      <div className="absolute bottom-1 left-1 text-[9px] leading-none opacity-40 pointer-events-auto z-[1]">
        <a
          href="https://www.openstreetmap.org/copyright"
          target="_blank"
          rel="noopener noreferrer"
          className="hover:opacity-80"
          style={{ color: "var(--text-tertiary)" }}
        >
          © OpenStreetMap
        </a>
      </div>
    </div>
  )
}

export default MapLibreMapComponent
