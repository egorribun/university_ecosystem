/**
 * campusWalkways.ts — GeoJSON walking paths connecting campus buildings.
 * Used by MapLibre line layer for dashed walkway visualization.
 * Wave 103 — campus walking paths.
 */

import type { FeatureCollection, Feature, LineString } from "geojson"

interface WalkwayProperties {
  id: string
  /** Approximate walking time in minutes */
  walkMinutes: number
}

function walkway(
  id: string,
  coords: [number, number][],
  walkMinutes: number,
): Feature<LineString, WalkwayProperties> {
  return {
    type: "Feature",
    properties: { id, walkMinutes },
    geometry: {
      type: "LineString",
      // coords as [lng, lat] for GeoJSON/MapLibre
      coordinates: coords,
    },
  }
}

/**
 * Main campus walkway routes connecting key buildings.
 * Coordinates in [lng, lat] format (GeoJSON standard).
 */
export const CAMPUS_WALKWAYS: FeatureCollection<LineString, WalkwayProperties> = {
  type: "FeatureCollection",
  features: [
    // Main axis: ГУК (А) → Лабораторный (В) → Поточные (Б)
    walkway("main-axis", [
      [37.81165, 55.71405], // А — ГУК
      [37.81350, 55.71370], // junction
      [37.81537, 55.71342], // В — Лабораторный
      [37.81669, 55.71350], // Б — Поточные
    ], 5),

    // ГУК (А) → Спорткомплекс (Д) via north path
    walkway("north-route", [
      [37.81165, 55.71405], // А — ГУК
      [37.81180, 55.71490], // north turn
      [37.81193, 55.71572], // Д — Спорткомплекс
    ], 3),

    // Junction → Общежитие №2 (Е) → Общежитие №6 (Ж)
    walkway("dorm-route", [
      [37.81537, 55.71342], // В — Лабораторный
      [37.81560, 55.71380], // turn
      [37.81577, 55.71384], // Е — Общ. №2
      [37.81560, 55.71440], // north
      [37.81547, 55.71495], // Ж — Общ. №6
    ], 4),

    // ГУК (А) → ПНПК (З) via northwest path
    walkway("nw-route", [
      [37.81165, 55.71405], // А — ГУК
      [37.81260, 55.71490], // turn
      [37.81355, 55.71569], // З — ПНПК
    ], 3),

    // Поточные (Б) → Административный (Г) east path
    walkway("east-route", [
      [37.81669, 55.71350], // Б — Поточные
      [37.81720, 55.71370], // turn
      [37.81778, 55.71401], // Г — Административный
    ], 2),

    // Main entrance → bus stop → ГУК
    walkway("entrance-route", [
      [37.81550, 55.71480], // bus stop area
      [37.81400, 55.71440], // campus entrance
      [37.81165, 55.71405], // А — ГУК
    ], 4),
  ],
}
