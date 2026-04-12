/**
 * MapLibreMap.tsx — Geographic map mode using react-map-gl + MapLibre GL + OpenFreeMap.
 *
 * WebGL-powered: 3D buildings via fill-extrusion, vector tiles, native dark theme.
 * Lazy-loaded via React.lazy() in MapFeature.
 *
 * Wave 100 — Leaflet → MapLibre GL migration.
 */

import { useState, useEffect, useMemo } from "react"
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
import "maplibre-gl/dist/maplibre-gl.css"

/* ── Tile styles ── */
const STYLE_LIGHT = "https://tiles.openfreemap.org/styles/bright"
const STYLE_DARK = "https://tiles.openfreemap.org/styles/dark"

/* ── 3D buildings fill-extrusion ── */
const BUILDINGS_3D_LAYER: LayerProps = {
  id: "3d-buildings",
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
    "fill-extrusion-opacity": 0.7,
  },
}

interface MapLibreMapProps {
  selectedBuilding: BuildingLetter | null
  activeCategory: MapCategory
  highlightedBuilding: BuildingLetter | null
  onSelectBuilding: (letter: BuildingLetter) => void
  /** Forwarded ref for external zoom control */
  mapRef?: React.MutableRefObject<MapRef | null>
  /** Whether dark theme is active */
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

  const buildings = useMemo(
    () => getCampusBuildings(i18n.resolvedLanguage ?? i18n.language),
    [i18n.resolvedLanguage, i18n.language],
  )

  const filteredBuildings = useMemo(() => {
    if (activeCategory === "all") return buildings
    return buildings.filter((b) => b.tags.includes(activeCategory))
  }, [buildings, activeCategory])

  /* ── Fly to selected building ── */
  useEffect(() => {
    if (!selectedBuilding || !mapRef?.current) return
    const building = buildings.find((b) => b.letter === selectedBuilding)
    if (!building) return
    mapRef.current.flyTo({
      center: [building.geoCoords[1], building.geoCoords[0]],
      zoom: 17,
      pitch: 45,
      duration: 800,
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
      >
        {/* 3D building extrusion layer */}
        <Layer {...BUILDINGS_3D_LAYER} />

        {/* Building markers */}
        {filteredBuildings.map((building) => (
          <BuildingMarker
            key={building.letter}
            building={building}
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
