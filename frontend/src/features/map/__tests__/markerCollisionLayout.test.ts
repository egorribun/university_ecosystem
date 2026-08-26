import { describe, expect, it } from "vitest"
import { CAMPUS_COORDINATES, CAMPUS_DETAIL_ZOOM } from "@/constants/campus"
import { getCampusBuildings } from "@/data/campusBuildings"
import { CAMPUS_POIS } from "@/data/campusPOI"
import {
  layoutMapMarkerOffsets,
  layoutProjectedMapMarkerOffsets,
  MAP_MARKER_SAFE_GAP_PX,
  type MapMarkerCollisionItem,
} from "@/features/map/markerCollisionLayout"

const CAMERAS = [
  { zoom: CAMPUS_DETAIL_ZOOM, bearing: -20, pitch: 0 },
  { zoom: CAMPUS_DETAIL_ZOOM, bearing: 0, pitch: 45 },
  { zoom: CAMPUS_DETAIL_ZOOM - 2, bearing: 73, pitch: 62 },
  { zoom: CAMPUS_DETAIL_ZOOM - 4, bearing: -137, pitch: 28 },
] as const

function project(latitude: number, longitude: number, zoom: number) {
  const size = 512 * 2 ** zoom
  const latRadians = (latitude * Math.PI) / 180
  return {
    x: ((longitude + 180) / 360) * size,
    y: ((1 - Math.asinh(Math.tan(latRadians)) / Math.PI) / 2) * size,
  }
}

function screenPoint(item: MapMarkerCollisionItem, zoom: number, bearing: number, pitch: number) {
  const point = project(item.latitude, item.longitude, zoom)
  const campus = project(CAMPUS_COORDINATES.lat, CAMPUS_COORDINATES.lon, zoom)
  const x = point.x - campus.x
  const y = point.y - campus.y
  const bearingRadians = (bearing * Math.PI) / 180
  return {
    x: x * Math.cos(bearingRadians) - y * Math.sin(bearingRadians),
    y:
      (x * Math.sin(bearingRadians) + y * Math.cos(bearingRadians)) *
        Math.cos((pitch * Math.PI) / 180) -
      (item.anchor === "bottom" ? item.height / 2 : 0),
  }
}

function expectDisjointTargets(items: readonly MapMarkerCollisionItem[]) {
  for (const camera of CAMERAS) {
    const offsets = layoutMapMarkerOffsets(items, [camera])
    for (let leftIndex = 0; leftIndex < items.length; leftIndex += 1) {
      const left = items[leftIndex]
      if (!left) continue
      const leftPoint = screenPoint(left, camera.zoom, camera.bearing, camera.pitch)
      const leftOffset = offsets.get(left.id) ?? [0, 0]
      for (let rightIndex = leftIndex + 1; rightIndex < items.length; rightIndex += 1) {
        const right = items[rightIndex]
        if (!right) continue
        const rightPoint = screenPoint(right, camera.zoom, camera.bearing, camera.pitch)
        const rightOffset = offsets.get(right.id) ?? [0, 0]
        const overlapsHorizontally =
          Math.abs(leftPoint.x + leftOffset[0] - rightPoint.x - rightOffset[0]) <
          (left.width + right.width) / 2 + MAP_MARKER_SAFE_GAP_PX
        const overlapsVertically =
          Math.abs(leftPoint.y + leftOffset[1] - rightPoint.y - rightOffset[1]) <
          (left.height + right.height) / 2 + MAP_MARKER_SAFE_GAP_PX
        expect(overlapsHorizontally && overlapsVertically, `${left.id} overlaps ${right.id}`).toBe(
          false
        )
      }
    }
  }
}

function campusMarkerFixtures(): MapMarkerCollisionItem[] {
  const buildings = getCampusBuildings("en").map((building) => ({
    id: `building-${building.letter}`,
    latitude: building.geoCoords[0],
    longitude: building.geoCoords[1],
    width: 60,
    height: 60,
    anchor: "bottom" as const,
  }))
  const pois = CAMPUS_POIS.map((poi) => ({
    id: `poi-${poi.id}`,
    latitude: poi.coords[0],
    longitude: poi.coords[1],
    width: 44,
    height: 44,
    anchor: "center" as const,
  }))
  const events = ["one", "two", "three"].map((id) => ({
    id: `event-${id}`,
    latitude: buildings[0]!.latitude,
    longitude: buildings[0]!.longitude,
    width: 44,
    height: 45,
    anchor: "bottom" as const,
  }))
  return [...buildings, ...pois, ...events]
}

describe("layoutMapMarkerOffsets", () => {
  it("keeps all canonical campus targets disjoint, including identical coordinates", () => {
    expectDisjointTargets(campusMarkerFixtures())
  })

  it("is deterministic and leaves an isolated marker at its real coordinate", () => {
    const fixtures = campusMarkerFixtures()
    expect([...layoutMapMarkerOffsets([])]).toEqual([])
    expect([...layoutMapMarkerOffsets(fixtures)]).toEqual([...layoutMapMarkerOffsets(fixtures)])
    expect(layoutMapMarkerOffsets([fixtures[0]!]).get(fixtures[0]!.id)).toEqual([0, 0])
  })

  it("packs targets from MapLibre's authoritative projected screen points", () => {
    const fixtures = campusMarkerFixtures().slice(0, 3)
    const projected = new Map(fixtures.map(({ id }) => [id, { x: 400, y: 300 }]))
    const offsets = layoutProjectedMapMarkerOffsets(fixtures, projected)

    expect([...layoutProjectedMapMarkerOffsets([], new Map())]).toEqual([])
    expect(offsets.get(fixtures[0]!.id)).toEqual([0, 0])
    expect(offsets.get(fixtures[1]!.id)).not.toEqual([0, 0])
    expect([...offsets]).toEqual([...layoutProjectedMapMarkerOffsets(fixtures, projected)])

    for (let leftIndex = 0; leftIndex < fixtures.length; leftIndex += 1) {
      const left = fixtures[leftIndex]!
      const leftOffset = offsets.get(left.id)!
      for (let rightIndex = leftIndex + 1; rightIndex < fixtures.length; rightIndex += 1) {
        const right = fixtures[rightIndex]!
        const rightOffset = offsets.get(right.id)!
        const overlapsHorizontally =
          Math.abs(leftOffset[0] - rightOffset[0]) <
          (left.width + right.width) / 2 + MAP_MARKER_SAFE_GAP_PX
        const overlapsVertically =
          Math.abs(-left.height / 2 + leftOffset[1] - (-right.height / 2 + rightOffset[1])) <
          (left.height + right.height) / 2 + MAP_MARKER_SAFE_GAP_PX
        expect(overlapsHorizontally && overlapsVertically).toBe(false)
      }
    }
  })

  it("fails closed when a live projection omits a marker", () => {
    const marker = campusMarkerFixtures()[0]!
    expect(() => layoutProjectedMapMarkerOffsets([marker], new Map())).toThrow(
      `Missing projected point for map marker: ${marker.id}`
    )
  })

  it("falls back to a guaranteed disjoint offset after the bounded nearest search", () => {
    const fixtures = ["first", "second"].map((id) => ({
      id,
      latitude: CAMPUS_COORDINATES.lat,
      longitude: CAMPUS_COORDINATES.lon,
      width: 1_000,
      height: 1_000,
      anchor: "center" as const,
    }))
    const projected = new Map(fixtures.map(({ id }) => [id, { x: 0, y: 0 }]))

    const offsets = layoutProjectedMapMarkerOffsets(fixtures, projected)
    const firstOffset = offsets.get("first")!
    const secondOffset = offsets.get("second")!

    expect(Math.abs(secondOffset[0] - firstOffset[0])).toBeGreaterThanOrEqual(
      fixtures[0]!.width + MAP_MARKER_SAFE_GAP_PX
    )
  })

  it("packs a dense production-scale projection within the main-thread budget", () => {
    const fixtures = Array.from({ length: 400 }, (_, index) => ({
      id: `dense-${index}`,
      latitude: CAMPUS_COORDINATES.lat,
      longitude: CAMPUS_COORDINATES.lon,
      width: 44,
      height: 44,
      anchor: "center" as const,
    }))
    const projected = new Map(fixtures.map(({ id }) => [id, { x: 400, y: 300 }]))

    const startedAt = performance.now()
    const offsets = layoutProjectedMapMarkerOffsets(fixtures, projected)
    const elapsedMs = performance.now() - startedAt

    // This is deliberately generous for shared CI runners while still
    // rejecting the former unbounded scan (roughly 20 seconds for 400 items).
    expect(elapsedMs).toBeLessThan(1_500)
    expect(offsets).toHaveLength(fixtures.length)
    expect([...offsets]).toEqual([...layoutProjectedMapMarkerOffsets(fixtures, projected)])

    for (let leftIndex = 0; leftIndex < fixtures.length; leftIndex += 1) {
      const leftOffset = offsets.get(fixtures[leftIndex]!.id)!
      for (let rightIndex = leftIndex + 1; rightIndex < fixtures.length; rightIndex += 1) {
        const rightOffset = offsets.get(fixtures[rightIndex]!.id)!
        const clearance = 44 + MAP_MARKER_SAFE_GAP_PX
        expect(
          Math.abs(leftOffset[0] - rightOffset[0]) < clearance &&
            Math.abs(leftOffset[1] - rightOffset[1]) < clearance
        ).toBe(false)
      }
    }
  })
})
