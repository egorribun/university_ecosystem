import { describe, expect, it } from "vitest"
import {
  layoutProjectedMapMarkerOffsets,
  type MapMarkerCollisionItem,
  type MapMarkerOffset,
  type ScreenPoint,
} from "@/features/map/markerCollisionLayout"

function marker(id: string, width = 44, height = 44): MapMarkerCollisionItem {
  return { id, latitude: 55.7144, longitude: 37.81478, width, height, anchor: "center" }
}

// Independent brute-force oracle: enumerate each clockwise square perimeter,
// then compare actual clickable rectangles directly, without a spatial index.
function referenceOffsets(
  markers: readonly MapMarkerCollisionItem[],
  points: ReadonlyMap<string, ScreenPoint>
): Map<string, MapMarkerOffset> {
  const candidates: MapMarkerOffset[] = [[0, 0]]
  const limit = Math.min(8192, Math.max(64, markers.length * 16))
  for (let ring = 1; candidates.length < limit; ring += 1) {
    const radius = ring * 80
    for (let x = -radius; x <= radius; x += 80) candidates.push([x, -radius])
    for (let y = -radius + 80; y <= radius; y += 80) candidates.push([radius, y])
    for (let x = radius - 80; x >= -radius; x -= 80) candidates.push([x, radius])
    for (let y = radius - 80; y > -radius; y -= 80) candidates.push([-radius, y])
  }
  const placed: { marker: MapMarkerCollisionItem; center: ScreenPoint }[] = []
  const offsets = new Map<string, MapMarkerOffset>()
  for (const item of markers) {
    const point = points.get(item.id)!
    const center = { x: point.x, y: point.y - (item.anchor === "bottom" ? item.height / 2 : 0) }
    const available = candidates
      .slice(0, limit)
      .find(([x, y]) =>
        placed.every(
          (previous) =>
            Math.abs(center.x + x - previous.center.x) >=
              (item.width + previous.marker.width) / 2 + 24 ||
            Math.abs(center.y + y - previous.center.y) >=
              (item.height + previous.marker.height) / 2 + 24
        )
      )
    const rightmost = Math.max(
      ...placed.map((previous) => previous.center.x + previous.marker.width / 2)
    )
    const offset: MapMarkerOffset = available ?? [
      Math.ceil(Math.max(80, rightmost + 24 + item.width / 2 - center.x) / 80) * 80,
      0,
    ]
    offsets.set(item.id, offset)
    placed.push({ marker: item, center: { x: center.x + offset[0], y: center.y + offset[1] } })
  }
  return offsets
}

describe("projected marker collision boundaries", () => {
  it.each(["x", "y"] as const)(
    "allows exact %s clearance but moves targets one pixel inside it",
    (axis) => {
      const markers = [marker("first", 44, 50), marker("second", 60, 40)]
      const clearance = axis === "x" ? 76 : 69
      for (const direction of [-1, 1]) {
        for (const inset of [0, 1]) {
          const points = new Map([
            ["first", { x: -128, y: 128 }],
            [
              "second",
              {
                x: -128 + (axis === "x" ? direction * (clearance - inset) : 0),
                y: 128 + (axis === "y" ? direction * (clearance - inset) : 0),
              },
            ],
          ])
          const offset = layoutProjectedMapMarkerOffsets(markers, points).get("second")
          if (inset === 0) expect(offset).toEqual([0, 0])
          else expect(offset).not.toEqual([0, 0])
        }
      }
    }
  )

  it.each([0, 64, 127, 128, -128, -257])(
    "matches direct packing across cell boundaries at origin %s",
    (origin) => {
      const markers = Array.from({ length: 24 }, (_, index) => ({
        ...marker(`mixed-${index}`, [10, 44, 250, 400][index % 4]!, [400, 50, 10, 250][index % 4]!),
        anchor: index % 3 === 0 ? ("bottom" as const) : ("center" as const),
      }))
      const points = new Map(
        markers.map((item, index) => [
          item.id,
          {
            x: origin + (index % 4) * 68,
            y: -origin + Math.floor(index / 4) * 74,
          },
        ])
      )
      const before = structuredClone({ markers, points })
      const actual = layoutProjectedMapMarkerOffsets(markers, points)
      expect([...actual]).toEqual([...referenceOffsets(markers, points)])
      expect({ markers, points }).toEqual(before)
    }
  )

  it.each([-320, 320])("keeps the bounded fallback translation invariant at x=%s", (x) => {
    const markers = [marker("wide-first", 1000, 1000), marker("wide-second", 1000, 1000)]
    const points = new Map(markers.map((item) => [item.id, { x, y: 512 }]))
    expect([...layoutProjectedMapMarkerOffsets(markers, points)]).toEqual([
      ["wide-first", [0, 0]],
      ["wide-second", [1040, 0]],
    ])
  })
})
