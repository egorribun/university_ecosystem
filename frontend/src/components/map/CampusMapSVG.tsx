import { useCallback, type CSSProperties, type KeyboardEvent } from "react"
import { useTranslation } from "react-i18next"
import type { CampusBuilding, BuildingLetter } from "@/data/campusBuildings"

/* ── Isometric building geometry ──────────────────
   Each building is a simple box: 3 faces (top, left, right).
   Width/depth/height vary by building for visual variety.
   Coordinates are local to the building <g> group.
   ─────────────────────────────────────────────── */

interface BuildingGeometry {
  w: number  // width (iso X axis)
  d: number  // depth (iso Y axis)
  h: number  // height (iso Z axis)
}

const BUILDING_GEOMETRY: Record<BuildingLetter, BuildingGeometry> = {
  А: { w: 120, d: 80, h: 70 },   // Main — largest
  Б: { w: 100, d: 70, h: 60 },   // Engineering
  В: { w: 90, d: 65, h: 55 },    // Humanities
  Г: { w: 100, d: 70, h: 65 },   // Science
  Д: { w: 110, d: 75, h: 50 },   // Arts & Sports — wide, short
}

/**
 * Convert 3D isometric coordinates to 2D screen points.
 * Standard dimetric: x_screen = (x - y) * cos30, y_screen = (x + y) * sin30 - z
 */
function isoPoint(x: number, y: number, z: number): string {
  const sx = (x - y) * 0.866
  const sy = (x + y) * 0.5 - z
  return `${sx.toFixed(1)},${sy.toFixed(1)}`
}

function buildingPolygons(g: BuildingGeometry) {
  const { w, d, h } = g
  // 8 corners of the box
  // Top face (roof)
  const topFace = [
    isoPoint(0, 0, h),
    isoPoint(w, 0, h),
    isoPoint(w, d, h),
    isoPoint(0, d, h),
  ].join(" ")

  // Left face (front-left wall)
  const leftFace = [
    isoPoint(0, 0, h),
    isoPoint(0, d, h),
    isoPoint(0, d, 0),
    isoPoint(0, 0, 0),
  ].join(" ")

  // Right face (front-right wall)
  const rightFace = [
    isoPoint(0, d, h),
    isoPoint(w, d, h),
    isoPoint(w, d, 0),
    isoPoint(0, d, 0),
  ].join(" ")

  // Label position — center of top face
  const labelX = parseFloat(isoPoint(w / 2, d / 2, h).split(",")[0])
  const labelY = parseFloat(isoPoint(w / 2, d / 2, h).split(",")[1]) - 4

  return { topFace, leftFace, rightFace, labelX, labelY }
}

/* ── Ground features ─────────────────────────── */

const GROUND_PATHS = [
  // Main walkway — horizontal
  "M 100,380 Q 350,370 600,380 T 1100,390",
  // Secondary path — diagonal
  "M 200,300 Q 400,350 600,330",
  // Path to building E
  "M 700,400 Q 850,410 950,380",
]

const GROUND_AREAS = [
  // Green lawn areas
  { cx: 450, cy: 350, rx: 80, ry: 40, color: "var(--color-emerald-200)" },
  { cx: 150, cy: 420, rx: 50, ry: 30, color: "var(--color-emerald-200)" },
  { cx: 800, cy: 300, rx: 60, ry: 35, color: "var(--color-emerald-200)" },
]

/* ── Component ────────────────────────────────── */

interface CampusMapSVGProps {
  buildings: CampusBuilding[]
  selectedBuilding: BuildingLetter | null
  highlightedBuilding?: BuildingLetter | null
  onBuildingClick: (letter: BuildingLetter) => void
  onBuildingHover?: (letter: BuildingLetter | null) => void
  prefersReducedMotion: boolean
}

export function CampusMapSVG({
  buildings,
  selectedBuilding,
  highlightedBuilding,
  onBuildingClick,
  onBuildingHover,
  prefersReducedMotion,
}: CampusMapSVGProps) {
  const { t } = useTranslation("map")

  const handleKeyDown = useCallback(
    (letter: BuildingLetter) => (e: KeyboardEvent) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault()
        onBuildingClick(letter)
      }
    },
    [onBuildingClick],
  )

  // Sort buildings by Y position (back to front) for correct z-order
  const sortedBuildings = [...buildings].sort(
    (a, b) => a.isoPosition.y - b.isoPosition.y,
  )

  return (
    <svg
      viewBox="0 0 1200 700"
      role="img"
      aria-label={t("campusMap.ariaLabel")}
      className="w-full h-full select-none"
      style={{ minHeight: "100%" }}
    >
      {/* Ground plane */}
      <rect
        x="0"
        y="0"
        width="1200"
        height="700"
        rx="12"
        fill="var(--map-svg-ground)"
      />

      {/* Ground accent (subtle teal tint) */}
      <ellipse
        cx="600"
        cy="400"
        rx="500"
        ry="250"
        fill="var(--map-svg-ground-accent)"
        opacity="0.5"
      />

      {/* Green areas */}
      {GROUND_AREAS.map((area, i) => (
        <ellipse
          key={i}
          cx={area.cx}
          cy={area.cy}
          rx={area.rx}
          ry={area.ry}
          fill={area.color}
          opacity="0.3"
        />
      ))}

      {/* Walkway paths */}
      <g aria-label={t("campusMap.groundLabel")}>
        {GROUND_PATHS.map((d, i) => (
          <path
            key={i}
            d={d}
            fill="none"
            stroke="var(--map-svg-path-stroke)"
            strokeWidth="3"
            strokeDasharray="8 5"
            opacity="0.5"
          />
        ))}
      </g>

      {/* Buildings — rendered back-to-front for z-order */}
      {sortedBuildings.map((bldg) => {
        const geom = BUILDING_GEOMETRY[bldg.letter]
        const polys = buildingPolygons(geom)
        const isActive = selectedBuilding === bldg.letter
        const isSchedule = highlightedBuilding === bldg.letter

        return (
          <g
            key={bldg.letter}
            role="button"
            tabIndex={0}
            aria-label={`${bldg.name}. ${t("tooltip.floors", { count: bldg.floorCount })}. ${t("tooltip.clickToExplore")}`}
            data-building={bldg.letter}
            data-active={isActive || undefined}
            data-schedule={isSchedule || undefined}
            transform={`translate(${bldg.isoPosition.x}, ${bldg.isoPosition.y})`}
            className="map-building-group"
            style={{ "--_bldg-color": bldg.colorVar } as CSSProperties}
            onClick={() => onBuildingClick(bldg.letter)}
            onKeyDown={handleKeyDown(bldg.letter)}
            onPointerEnter={() => onBuildingHover?.(bldg.letter)}
            onPointerLeave={() => onBuildingHover?.(null)}
          >
            {/* Drop shadow on ground */}
            <ellipse
              cx={geom.w * 0.35}
              cy={geom.d * 0.6 + 8}
              rx={geom.w * 0.5}
              ry={geom.d * 0.2}
              fill="var(--map-svg-shadow)"
              opacity="0.4"
            />

            {/* Left wall (lighter) */}
            <polygon
              points={polys.leftFace}
              fill={bldg.colorHex}
              opacity="0.75"
            />

            {/* Right wall (darker) */}
            <polygon
              points={polys.rightFace}
              fill={bldg.colorHex}
              opacity="0.6"
            />

            {/* Roof (brightest) */}
            <polygon
              points={polys.topFace}
              fill={bldg.colorHex}
              opacity="var(--map-svg-roof-opacity)"
            />

            {/* Building letter label */}
            <text
              x={polys.labelX}
              y={polys.labelY}
              textAnchor="middle"
              dominantBaseline="central"
              fill="var(--map-svg-label)"
              fontSize="22"
              fontWeight="800"
              style={{ pointerEvents: "none" }}
            >
              {bldg.letter}
            </text>

            {/* Floor count badge */}
            <text
              x={polys.labelX}
              y={polys.labelY + 18}
              textAnchor="middle"
              dominantBaseline="central"
              fill="var(--map-svg-label)"
              fontSize="10"
              fontWeight="600"
              opacity="0.7"
              style={{ pointerEvents: "none" }}
            >
              {bldg.floorCount}F
            </text>

            {/* Schedule indicator pulse ring */}
            {isSchedule && !prefersReducedMotion && (
              <circle
                cx={polys.labelX}
                cy={polys.labelY + 6}
                r={Math.max(geom.w, geom.d) * 0.45}
                fill="none"
                stroke={bldg.colorHex}
                strokeWidth="2"
                opacity="0.5"
                className="map-building-pulse-ring"
              />
            )}
          </g>
        )
      })}
    </svg>
  )
}
