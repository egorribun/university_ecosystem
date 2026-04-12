/**
 * campusBuildingFootprints.ts — GeoJSON building footprints for campus buildings.
 * Used by MapLibre fill-extrusion layer to render campus buildings in custom colors
 * (matching А-З palette) over the generic gray OpenFreeMap buildings.
 *
 * Approximate rectangular footprints centered on verified building coordinates.
 * Wave 103 — custom 3D campus buildings.
 */

import type { FeatureCollection, Feature, Polygon } from "geojson"

interface BuildingProperties {
  letter: string
  color: string
  height: number
  name: string
}

/**
 * Creates a rectangular polygon centered at [lng, lat] with given dimensions in meters.
 * Approximate conversion: 1° latitude ≈ 111,320m, 1° longitude ≈ cos(lat) × 111,320m.
 */
function buildingRect(
  lat: number,
  lng: number,
  widthMeters: number,
  depthMeters: number,
): [number, number][] {
  const latDelta = depthMeters / 111320 / 2
  const lngDelta = widthMeters / (111320 * Math.cos(lat * (Math.PI / 180))) / 2

  return [
    [lng - lngDelta, lat - latDelta],
    [lng + lngDelta, lat - latDelta],
    [lng + lngDelta, lat + latDelta],
    [lng - lngDelta, lat + latDelta],
    [lng - lngDelta, lat - latDelta], // close ring
  ]
}

function buildingFeature(
  letter: string,
  lat: number,
  lng: number,
  widthM: number,
  depthM: number,
  heightM: number,
  color: string,
  name: string,
): Feature<Polygon, BuildingProperties> {
  return {
    type: "Feature",
    properties: { letter, color, height: heightM, name },
    geometry: {
      type: "Polygon",
      coordinates: [buildingRect(lat, lng, widthM, depthM)],
    },
  }
}

/**
 * GeoJSON FeatureCollection of campus building footprints.
 * Heights are approximate based on floor counts (≈3.5m per floor).
 */
export const CAMPUS_BUILDING_FOOTPRINTS: FeatureCollection<Polygon, BuildingProperties> = {
  type: "FeatureCollection",
  features: [
    // А — ГУК (8 floors ≈ 28m) — largest building
    buildingFeature("А", 55.71405, 37.81165, 70, 45, 28, "#3b82f6", "ГУК"),
    // Б — Поточные (5 floors ≈ 17.5m)
    buildingFeature("Б", 55.71350, 37.81669, 55, 35, 17.5, "#f59e0b", "Поточные"),
    // В — Лабораторный (6 floors ≈ 21m)
    buildingFeature("В", 55.71342, 37.81537, 50, 30, 21, "#10b981", "Лабораторный"),
    // Г — Административный (5 floors ≈ 17.5m)
    buildingFeature("Г", 55.71401, 37.81778, 45, 30, 17.5, "#64748b", "Административный"),
    // Д — Спорткомплекс (2 floors ≈ 8m, but tall pool ceiling)
    buildingFeature("Д", 55.71572, 37.81193, 50, 35, 10, "#f43f5e", "Спорткомплекс"),
    // Е — Общежитие №2 (16 floors ≈ 48m) — tall tower
    buildingFeature("Е", 55.71384, 37.81577, 30, 25, 48, "#6366f1", "Общ. №2"),
    // Ж — Общежитие №6 (18 floors ≈ 54m) — tallest building
    buildingFeature("Ж", 55.71495, 37.81547, 30, 25, 54, "#0ea5e9", "Общ. №6"),
    // З — ПНПК (2 floors ≈ 7m)
    buildingFeature("З", 55.71569, 37.81355, 35, 25, 7, "#8b5cf6", "ПНПК"),
  ],
}
