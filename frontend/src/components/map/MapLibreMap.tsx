/**
 * MapLibreMap.tsx — Premium geographic map with MapLibre GL + OpenFreeMap.
 *
 * WebGL-powered: 3D buildings (generic + custom campus colors), sky, fog,
 * walking paths, cinematic camera intro, premium markers.
 *
 * Wave 100 — Leaflet → MapLibre; Wave 102-103 — premium visual masterpiece.
 */

import { useState, useEffect, useMemo, useCallback, useRef } from "react"
import { Map, Layer } from "react-map-gl/maplibre"
import type { MapRef, LayerProps } from "react-map-gl/maplibre"
import { useTranslation } from "react-i18next"
import { CAMPUS_COORDINATES } from "@/constants/campus"
import { getCampusBuildings, type BuildingLetter, type MapCategory } from "@/data/campusBuildings"
import { CAMPUS_POIS, type CampusPOI } from "@/data/campusPOI"
import { useOverpassPOI } from "@/hooks/useOverpassPOI"
import { BuildingMarker } from "./BuildingMarker"
import { POIMarker } from "./POIMarker"
import { POIControls } from "./POIControls"
import { MapControls } from "./MapControls"
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
      0, "#d1d5db",
      50, "#9ca3af",
      100, "#6b7280",
    ],
    "fill-extrusion-height": [
      "interpolate",
      ["linear"],
      ["zoom"],
      15, 0,
      16, ["get", "render_height"],
    ],
    "fill-extrusion-base": [
      "case",
      [">=", ["get", "zoom"], 16],
      ["get", "render_min_height"],
      0,
    ],
    "fill-extrusion-opacity": 0.5,
  },
}

interface MapLibreMapProps {
  selectedBuilding: BuildingLetter | null
  activeCategory: MapCategory
  highlightedBuilding: BuildingLetter | null
  onSelectBuilding: (letter: BuildingLetter) => void
  mapRef?: React.MutableRefObject<MapRef | null>
  isDark?: boolean
}

export function MapLibreMapComponent({
  selectedBuilding,
  activeCategory,
  highlightedBuilding,
  onSelectBuilding,
  mapRef,
  isDark,
}: MapLibreMapProps) {
  const { i18n } = useTranslation("map")
  const hasAnimatedIntro = useRef(false)

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

  const allPois = useMemo(() => {
    const base: CampusPOI[] = [...CAMPUS_POIS]
    if (hasLoaded) {
      for (const op of overpassPois) {
        const isDuplicate = base.some((bp) => {
          const dlat = Math.abs(bp.coords[0] - op.coords[0])
          const dlng = Math.abs(bp.coords[1] - op.coords[1])
          return dlat < 0.0005 && dlng < 0.0005
        })
        if (!isDuplicate) base.push(op)
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

    // Sky — atmospheric gradient
    map.setSky({
      "sky-color": isDark ? "#0f172a" : "#87ceeb",
      "sky-horizon-blend": 0.3,
      "horizon-color": isDark ? "#1e293b" : "#f0f4ff",
      "horizon-fog-blend": 0.8,
      "fog-color": isDark ? "#1e293b" : "#e8edf5",
      "fog-ground-blend": 0.5,
    })

    // Cinematic intro — fly from high altitude
    if (!hasAnimatedIntro.current) {
      hasAnimatedIntro.current = true
      map.jumpTo({
        center: [CAMPUS_COORDINATES.lon, CAMPUS_COORDINATES.lat],
        zoom: 13,
        pitch: 0,
        bearing: -20,
      })
      setTimeout(() => {
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
  }, [mapRef, isDark])

  /* ── Update sky on theme change ── */
  useEffect(() => {
    const map = mapRef?.current?.getMap()
    if (!map || !map.loaded()) return

    map.setSky({
      "sky-color": isDark ? "#0f172a" : "#87ceeb",
      "sky-horizon-blend": 0.3,
      "horizon-color": isDark ? "#1e293b" : "#f0f4ff",
      "horizon-fog-blend": 0.8,
      "fog-color": isDark ? "#1e293b" : "#e8edf5",
      "fog-ground-blend": 0.5,
    })
  }, [isDark, mapRef])

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
      </Map>

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
        />
      </div>
    </div>
  )
}

export default MapLibreMapComponent
