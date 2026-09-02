import { CAMPUS_COORDINATES, CAMPUS_DETAIL_ZOOM } from "@/constants/campus"

export type MapMarkerOffset = [number, number]

export interface MapMarkerCollisionItem {
  id: string
  latitude: number
  longitude: number
  width: number
  height: number
  anchor: "center" | "bottom"
}

export interface ScreenPoint {
  x: number
  y: number
}

export interface MapMarkerCameraState {
  zoom: number
  bearing: number
  pitch: number
}

interface PlacedMarker extends MapMarkerCollisionItem {
  cameraPoints: readonly ScreenPoint[]
  offset: MapMarkerOffset
}

interface MarkerBounds {
  left: number
  top: number
  right: number
  bottom: number
}

const TILE_SIZE = 512
// Axe/WCAG target-size evaluates the safe clickable diameter around transformed
// targets, not only rectangle intersection. Preserve a full 24px exclusion
// zone so clipped pin shapes remain independently operable at every zoom.
export const MAP_MARKER_SAFE_GAP_PX = 24
// All current interactive markers are at most 50px tall. An 80px lattice is
// therefore the smallest rounded step that already includes the 24px safe gap
// for a dense same-coordinate cluster, avoiding dozens of known-bad probes.
const OFFSET_STEP_PX = 80
const SPATIAL_CELL_SIZE_PX = 128
const MIN_CANDIDATE_ATTEMPTS = 64
const MAX_CANDIDATE_ATTEMPTS = 8_192
const ZERO_OFFSET: MapMarkerOffset = [0, 0]

/** The two deterministic views used before and after the campus intro. */
const CANONICAL_CAMERA_STATES: readonly MapMarkerCameraState[] = [
  { zoom: CAMPUS_DETAIL_ZOOM, bearing: -20, pitch: 0 },
  { zoom: CAMPUS_DETAIL_ZOOM, bearing: 0, pitch: 45 },
]

function projectToWorldPixels(latitude: number, longitude: number, zoom: number): ScreenPoint {
  const worldSize = TILE_SIZE * 2 ** zoom
  const latitudeRadians = (latitude * Math.PI) / 180
  return {
    x: ((longitude + 180) / 360) * worldSize,
    y: ((1 - Math.asinh(Math.tan(latitudeRadians)) / Math.PI) / 2) * worldSize,
  }
}

function toCameraPoint(item: MapMarkerCollisionItem, camera: MapMarkerCameraState): ScreenPoint {
  const projected = projectToWorldPixels(item.latitude, item.longitude, camera.zoom)
  const campusWorldPoint = projectToWorldPixels(
    CAMPUS_COORDINATES.lat,
    CAMPUS_COORDINATES.lon,
    camera.zoom
  )
  const worldX = projected.x - campusWorldPoint.x
  const worldY = projected.y - campusWorldPoint.y
  const bearingRadians = (camera.bearing * Math.PI) / 180
  const pitchRadians = (camera.pitch * Math.PI) / 180
  const cosBearing = Math.cos(bearingRadians)
  const sinBearing = Math.sin(bearingRadians)
  const rotatedX = worldX * cosBearing - worldY * sinBearing
  const rotatedY = worldX * sinBearing + worldY * cosBearing

  return {
    x: rotatedX,
    y: rotatedY * Math.cos(pitchRadians) - (item.anchor === "bottom" ? item.height / 2 : 0),
  }
}

function overlaps(
  item: MapMarkerCollisionItem,
  cameraPoint: ScreenPoint,
  offset: MapMarkerOffset,
  placed: PlacedMarker,
  cameraIndex: number
): boolean {
  const placedPoint = placed.cameraPoints[cameraIndex]!
  const horizontalClearance = (item.width + placed.width) / 2 + MAP_MARKER_SAFE_GAP_PX
  const verticalClearance = (item.height + placed.height) / 2 + MAP_MARKER_SAFE_GAP_PX
  const deltaX = cameraPoint.x + offset[0] - (placedPoint.x + placed.offset[0])
  const deltaY = cameraPoint.y + offset[1] - (placedPoint.y + placed.offset[1])
  return Math.abs(deltaX) < horizontalClearance && Math.abs(deltaY) < verticalClearance
}

function markerBounds(
  item: MapMarkerCollisionItem,
  cameraPoint: ScreenPoint,
  offset: MapMarkerOffset
): MarkerBounds {
  const halfGap = MAP_MARKER_SAFE_GAP_PX / 2
  const centerX = cameraPoint.x + offset[0]
  const centerY = cameraPoint.y + offset[1]
  return {
    left: centerX - item.width / 2 - halfGap,
    top: centerY - item.height / 2 - halfGap,
    right: centerX + item.width / 2 + halfGap,
    bottom: centerY + item.height / 2 + halfGap,
  }
}

function cellRange(bounds: MarkerBounds): readonly [number, number, number, number] {
  return [
    Math.floor(bounds.left / SPATIAL_CELL_SIZE_PX),
    Math.floor(bounds.top / SPATIAL_CELL_SIZE_PX),
    Math.floor(bounds.right / SPATIAL_CELL_SIZE_PX),
    Math.floor(bounds.bottom / SPATIAL_CELL_SIZE_PX),
  ]
}

class MarkerSpatialIndex {
  private readonly cells = new Map<string, number[]>()

  insert(markerIndex: number, bounds: MarkerBounds): void {
    const [minX, minY, maxX, maxY] = cellRange(bounds)
    for (let x = minX; x <= maxX; x += 1) {
      for (let y = minY; y <= maxY; y += 1) {
        const key = `${x}:${y}`
        const cell = this.cells.get(key)
        if (cell) cell.push(markerIndex)
        else this.cells.set(key, [markerIndex])
      }
    }
  }

  hasCollision(bounds: MarkerBounds, test: (markerIndex: number) => boolean): boolean {
    const [minX, minY, maxX, maxY] = cellRange(bounds)
    for (let x = minX; x <= maxX; x += 1) {
      for (let y = minY; y <= maxY; y += 1) {
        for (const markerIndex of this.cells.get(`${x}:${y}`) ?? []) {
          // A marker can occupy more than one cell. Rechecking it is cheaper
          // than allocating a Set for every candidate probe, and preserves
          // the exact collision predicate.
          if (test(markerIndex)) return true
        }
      }
    }
    return false
  }
}

function isAvailable(
  item: MapMarkerCollisionItem,
  cameraPoints: readonly ScreenPoint[],
  offset: MapMarkerOffset,
  placedMarkers: readonly PlacedMarker[],
  spatialIndexes: readonly MarkerSpatialIndex[]
): boolean {
  for (let cameraIndex = 0; cameraIndex < cameraPoints.length; cameraIndex += 1) {
    const cameraPoint = cameraPoints[cameraIndex]!
    if (
      spatialIndexes[cameraIndex]!.hasCollision(
        markerBounds(item, cameraPoint, offset),
        (markerIndex) =>
          overlaps(item, cameraPoint, offset, placedMarkers[markerIndex]!, cameraIndex)
      )
    )
      return false
  }
  return true
}

function* candidateOffsets(): Generator<MapMarkerOffset> {
  yield ZERO_OFFSET
  for (let ring = 1; ; ring += 1) {
    const radius = ring * OFFSET_STEP_PX
    for (let x = -radius; x <= radius; x += OFFSET_STEP_PX) yield [x, -radius]
    for (let y = -radius + OFFSET_STEP_PX; y <= radius; y += OFFSET_STEP_PX) {
      yield [radius, y]
    }
    for (let x = radius - OFFSET_STEP_PX; x >= -radius; x -= OFFSET_STEP_PX) {
      yield [x, radius]
    }
    for (let y = radius - OFFSET_STEP_PX; y > -radius; y -= OFFSET_STEP_PX) {
      yield [-radius, y]
    }
  }
}

function fallbackOffset(
  item: MapMarkerCollisionItem,
  cameraPoints: readonly ScreenPoint[],
  rightmostEdges: readonly number[]
): MapMarkerOffset {
  let requiredX = OFFSET_STEP_PX
  for (let cameraIndex = 0; cameraIndex < cameraPoints.length; cameraIndex += 1) {
    const rightmostEdge = rightmostEdges[cameraIndex]!
    // Reaching the fallback requires every bounded candidate to collide, which
    // proves at least one marker has already populated every camera index.
    requiredX = Math.max(
      requiredX,
      rightmostEdge + MAP_MARKER_SAFE_GAP_PX + item.width / 2 - cameraPoints[cameraIndex]!.x
    )
  }
  return [Math.ceil(requiredX / OFFSET_STEP_PX) * OFFSET_STEP_PX, 0]
}

function layoutOffsets(
  markers: readonly MapMarkerCollisionItem[],
  getCameraPoints: (marker: MapMarkerCollisionItem) => readonly ScreenPoint[],
  cameraCount: number
): ReadonlyMap<string, MapMarkerOffset> {
  const placedMarkers: PlacedMarker[] = []
  const offsets = new Map<string, MapMarkerOffset>()
  const spatialIndexes = Array.from({ length: cameraCount }, () => new MarkerSpatialIndex())
  const rightmostEdges = Array.from({ length: cameraCount }, () => Number.NEGATIVE_INFINITY)
  const candidateAttemptLimit = Math.min(
    MAX_CANDIDATE_ATTEMPTS,
    Math.max(MIN_CANDIDATE_ATTEMPTS, markers.length * 16)
  )

  for (const marker of markers) {
    const cameraPoints = getCameraPoints(marker)
    let offset: MapMarkerOffset | undefined
    let attempts = 0
    for (const candidate of candidateOffsets()) {
      attempts += 1
      if (isAvailable(marker, cameraPoints, candidate, placedMarkers, spatialIndexes)) {
        offset = candidate
        break
      }
      if (attempts >= candidateAttemptLimit) break
    }
    offset ??= fallbackOffset(marker, cameraPoints, rightmostEdges)

    const markerIndex = placedMarkers.length
    placedMarkers.push({ ...marker, cameraPoints, offset })
    offsets.set(marker.id, offset)
    for (let cameraIndex = 0; cameraIndex < cameraPoints.length; cameraIndex += 1) {
      const point = cameraPoints[cameraIndex]!
      spatialIndexes[cameraIndex]!.insert(markerIndex, markerBounds(marker, point, offset))
      rightmostEdges[cameraIndex] = Math.max(
        rightmostEdges[cameraIndex]!,
        point.x + offset[0] + marker.width / 2
      )
    }
  }

  return offsets
}

/**
 * Assign stable screen-space offsets that keep keyboard targets disjoint in
 * both canonical z17 camera states. Input order is the deterministic priority:
 * buildings remain closest to their coordinates, followed by POIs and events.
 */
export function layoutMapMarkerOffsets(
  markers: readonly MapMarkerCollisionItem[],
  cameras: readonly MapMarkerCameraState[] = CANONICAL_CAMERA_STATES
): ReadonlyMap<string, MapMarkerOffset> {
  return layoutOffsets(
    markers,
    (marker) => cameras.map((camera) => toCameraPoint(marker, camera)),
    cameras.length
  )
}

/**
 * Pack markers from MapLibre's own projection. The camera approximation above
 * is useful before the client map exists (including SSR), but pitched maps use
 * perspective transforms that cannot be reproduced by a simple cosine. Once
 * MapLibre is ready, its `project()` output is the authoritative screen-space
 * input and guarantees the packing contract for the actual rendered camera.
 */
export function layoutProjectedMapMarkerOffsets(
  markers: readonly MapMarkerCollisionItem[],
  projectedPoints: ReadonlyMap<string, ScreenPoint>
): ReadonlyMap<string, MapMarkerOffset> {
  return layoutOffsets(
    markers,
    (marker) => {
      const projected = projectedPoints.get(marker.id)
      if (!projected) {
        throw new Error(`Missing projected point for map marker: ${marker.id}`)
      }
      return [
        {
          x: projected.x,
          y: projected.y - (marker.anchor === "bottom" ? marker.height / 2 : 0),
        },
      ]
    },
    1
  )
}
