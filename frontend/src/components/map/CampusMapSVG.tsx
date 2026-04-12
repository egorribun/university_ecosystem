import { useCallback, useMemo, type CSSProperties, type KeyboardEvent } from "react"
import { useTranslation } from "react-i18next"
import { motion } from "framer-motion"
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
  А: { w: 130, d: 85, h: 80 },   // Main building (ГУК, стр. 8) — tallest, largest
  Б: { w: 110, d: 75, h: 55 },   // Lecture halls (стр. 5) — wide
  В: { w: 90, d: 65, h: 55 },    // Lab building (стр. 4)
  Г: { w: 80, d: 55, h: 45 },    // Admin (стр. 1) �� smaller
  Д: { w: 100, d: 70, h: 40 },   // Sports complex (стр. 3) — wide, low
  Е: { w: 70, d: 50, h: 65 },    // Dorm 2 (стр. 2) — tall, narrow
  Ж: { w: 70, d: 50, h: 65 },    // Dorm 6 (к. 6) — tall, narrow
  З: { w: 75, d: 55, h: 45 },    // Graduate institute (стр. 16) — small
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

function isoPointXY(x: number, y: number, z: number): { x: number; y: number } {
  return { x: (x - y) * 0.866, y: (x + y) * 0.5 - z }
}

interface BuildingPolygons {
  topFace: string
  leftFace: string
  rightFace: string
  labelX: number
  labelY: number
}

function buildingPolygons(g: BuildingGeometry): BuildingPolygons {
  const { w, d, h } = g
  const topFace = [
    isoPoint(0, 0, h), isoPoint(w, 0, h),
    isoPoint(w, d, h), isoPoint(0, d, h),
  ].join(" ")

  const leftFace = [
    isoPoint(0, 0, h), isoPoint(0, d, h),
    isoPoint(0, d, 0), isoPoint(0, 0, 0),
  ].join(" ")

  const rightFace = [
    isoPoint(0, d, h), isoPoint(w, d, h),
    isoPoint(w, d, 0), isoPoint(0, d, 0),
  ].join(" ")

  const center = isoPointXY(w / 2, d / 2, h)
  return { topFace, leftFace, rightFace, labelX: center.x, labelY: center.y - 4 }
}

/* ── Window geometry helper ──────────────────── */

interface WindowRect {
  points: string
}

function buildingWindows(g: BuildingGeometry, face: "left" | "right"): WindowRect[] {
  const { w, d, h } = g
  const windowRows = Math.max(1, Math.floor(h / 28))
  const windowCols = face === "left" ? Math.max(2, Math.floor(d / 25)) : Math.max(2, Math.floor(w / 30))
  const windows: WindowRect[] = []

  for (let row = 0; row < windowRows; row++) {
    const z0 = 8 + row * (h - 12) / windowRows
    const z1 = z0 + (h - 12) / windowRows * 0.5
    for (let col = 0; col < windowCols; col++) {
      if (face === "left") {
        const y0 = 6 + col * (d - 12) / windowCols
        const y1 = y0 + (d - 12) / windowCols * 0.5
        windows.push({
          points: [isoPoint(0, y0, z1), isoPoint(0, y1, z1), isoPoint(0, y1, z0), isoPoint(0, y0, z0)].join(" "),
        })
      } else {
        const x0 = 6 + col * (w - 12) / windowCols
        const x1 = x0 + (w - 12) / windowCols * 0.5
        windows.push({
          points: [isoPoint(x0, d, z1), isoPoint(x1, d, z1), isoPoint(x1, d, z0), isoPoint(x0, d, z0)].join(" "),
        })
      }
    }
  }
  return windows
}

/* ── Door helper ─────────────────────────────── */

function buildingDoor(g: BuildingGeometry): string {
  const { d } = g
  const doorW = Math.min(12, d * 0.15)
  const doorH = 18
  const y0 = d * 0.45
  const y1 = y0 + doorW
  return [isoPoint(0, y0, doorH), isoPoint(0, y1, doorH), isoPoint(0, y1, 0), isoPoint(0, y0, 0)].join(" ")
}

/* ── Ground decorations ──────────────────────── */

const GROUND_PATHS = [
  "M 100,380 Q 350,370 600,380 T 1100,390",
  "M 200,300 Q 400,350 600,330",
  "M 700,400 Q 850,410 950,380",
]

const GROUND_AREAS = [
  { cx: 450, cy: 350, rx: 80, ry: 40, color: "var(--color-emerald-200)" },
  { cx: 150, cy: 420, rx: 50, ry: 30, color: "var(--color-emerald-200)" },
  { cx: 800, cy: 300, rx: 60, ry: 35, color: "var(--color-emerald-200)" },
]

/* ── Decorative trees & benches ──────────────── */

interface TreeDeco { cx: number; cy: number; size: number }
interface BenchDeco { x: number; y: number; angle: number }

const TREES: TreeDeco[] = [
  { cx: 180, cy: 340, size: 18 }, { cx: 220, cy: 360, size: 14 },
  { cx: 500, cy: 310, size: 16 }, { cx: 530, cy: 330, size: 12 },
  { cx: 380, cy: 400, size: 15 }, { cx: 750, cy: 350, size: 17 },
  { cx: 900, cy: 370, size: 13 }, { cx: 650, cy: 420, size: 15 },
]

const BENCHES: BenchDeco[] = [
  { x: 330, y: 385, angle: 0 }, { x: 580, y: 370, angle: 15 },
  { x: 850, y: 340, angle: -10 },
]

/* ── Entrance animation variants ─────────────── */

const buildingVariants = {
  hidden: { y: 30, opacity: 0 },
  visible: (i: number) => ({
    y: 0,
    opacity: 1,
    transition: { delay: i * 0.08, type: "spring" as const, stiffness: 300, damping: 25 },
  }),
}

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
  const sortedBuildings = useMemo(
    () => [...buildings].sort((a, b) => a.isoPosition.y - b.isoPosition.y),
    [buildings],
  )

  return (
    <svg
      viewBox="0 0 1400 750"
      role="img"
      aria-label={t("campusMap.ariaLabel")}
      className="w-full h-full select-none"
      style={{ minHeight: "100%" }}
    >
      {/* Ground plane */}
      <rect
        x="0" y="0" width="1400" height="750" rx="12"
        fill="var(--map-svg-ground)"
      />

      {/* Ground accent (subtle teal tint) */}
      <ellipse
        cx="600" cy="400" rx="500" ry="250"
        fill="var(--map-svg-ground-accent)" opacity="0.5"
      />

      {/* Green areas */}
      {GROUND_AREAS.map((area, i) => (
        <ellipse
          key={i} cx={area.cx} cy={area.cy} rx={area.rx} ry={area.ry}
          fill={area.color} opacity="0.3"
        />
      ))}

      {/* Decorative trees */}
      <g aria-hidden="true" style={{ pointerEvents: "none" }}>
        {TREES.map((tree, i) => (
          <g key={`tree-${i}`}>
            {/* Trunk */}
            <rect
              x={tree.cx - 2} y={tree.cy - tree.size * 0.3}
              width={4} height={tree.size * 0.4}
              rx={1} fill="var(--map-svg-bench)" opacity="0.5"
            />
            {/* Canopy */}
            <circle
              cx={tree.cx} cy={tree.cy - tree.size * 0.5}
              r={tree.size * 0.5}
              fill="var(--map-svg-tree)" opacity="0.5"
            />
          </g>
        ))}
        {BENCHES.map((bench, i) => (
          <g key={`bench-${i}`} transform={`translate(${bench.x},${bench.y}) rotate(${bench.angle})`}>
            <rect x={-10} y={-2} width={20} height={4} rx={1}
              fill="var(--map-svg-bench)" opacity="0.4" />
            <rect x={-8} y={-4} width={16} height={2} rx={0.5}
              fill="var(--map-svg-bench)" opacity="0.3" />
          </g>
        ))}
      </g>

      {/* Walkway paths */}
      <g aria-label={t("campusMap.groundLabel")}>
        {GROUND_PATHS.map((d, i) => (
          <path
            key={i} d={d} fill="none"
            stroke="var(--map-svg-path-stroke)" strokeWidth="3"
            strokeDasharray="8 5" opacity="0.5"
          />
        ))}
      </g>

      {/* Buildings — rendered back-to-front for z-order */}
      {sortedBuildings.map((bldg, idx) => {
        const geom = BUILDING_GEOMETRY[bldg.letter]
        const polys = buildingPolygons(geom)
        const isActive = selectedBuilding === bldg.letter
        const isSchedule = highlightedBuilding === bldg.letter
        const leftWindows = buildingWindows(geom, "left")
        const rightWindows = buildingWindows(geom, "right")
        const doorPoints = buildingDoor(geom)

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
            {/* Animated entrance — motion.g inside positioned <g> */}
            <motion.g
              variants={buildingVariants}
              initial={prefersReducedMotion ? false : "hidden"}
              animate="visible"
              custom={idx}
            >
              {/* Drop shadow on ground */}
              <ellipse
                cx={geom.w * 0.35} cy={geom.d * 0.6 + 8}
                rx={geom.w * 0.5} ry={geom.d * 0.2}
                fill="var(--map-svg-shadow)" opacity="0.4"
              />

              {/* Left wall (lighter) */}
              <polygon points={polys.leftFace} fill={bldg.colorHex} opacity="0.75" />

              {/* Left wall windows */}
              <g aria-hidden="true" style={{ pointerEvents: "none" }}>
                {leftWindows.map((win, wi) => (
                  <polygon key={`lw-${wi}`} points={win.points}
                    fill="var(--map-svg-label)" opacity="var(--map-svg-window-opacity)" />
                ))}
              </g>

              {/* Door indicator on left wall */}
              <polygon
                points={doorPoints} fill="var(--map-svg-label)" opacity="0.25"
                aria-hidden="true" style={{ pointerEvents: "none" }}
              />

              {/* Right wall (darker) */}
              <polygon points={polys.rightFace} fill={bldg.colorHex} opacity="0.6" />

              {/* Right wall windows */}
              <g aria-hidden="true" style={{ pointerEvents: "none" }}>
                {rightWindows.map((win, wi) => (
                  <polygon key={`rw-${wi}`} points={win.points}
                    fill="var(--map-svg-label)" opacity="var(--map-svg-window-opacity)" />
                ))}
              </g>

              {/* Roof (brightest) */}
              <polygon points={polys.topFace} fill={bldg.colorHex} opacity="var(--map-svg-roof-opacity)" />

              {/* Building letter label */}
              <text
                x={polys.labelX} y={polys.labelY}
                textAnchor="middle" dominantBaseline="central"
                fill="var(--map-svg-label)" fontSize="22" fontWeight="800"
                style={{ pointerEvents: "none" }}
              >
                {bldg.letter}
              </text>

              {/* Floor count badge */}
              <text
                x={polys.labelX} y={polys.labelY + 18}
                textAnchor="middle" dominantBaseline="central"
                fill="var(--map-svg-label)" fontSize="10" fontWeight="600" opacity="0.7"
                style={{ pointerEvents: "none" }}
              >
                {t("tooltip.floors", { count: bldg.floorCount })}
              </text>

              {/* Schedule indicator pulse ring */}
              {isSchedule && !prefersReducedMotion && (
                <circle
                  cx={polys.labelX} cy={polys.labelY + 6}
                  r={Math.max(geom.w, geom.d) * 0.45}
                  fill="none" stroke={bldg.colorHex} strokeWidth="2" opacity="0.5"
                  className="map-building-pulse-ring"
                />
              )}
            </motion.g>
          </g>
        )
      })}
    </svg>
  )
}
