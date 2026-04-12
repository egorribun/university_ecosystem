import { useCallback, useMemo, type CSSProperties, type KeyboardEvent } from "react"
import { useTranslation } from "react-i18next"
import type { BuildingFloor, CampusBuilding, CampusRoom } from "@/data/campusBuildings"

/* ── Room layout generator ────────────────────────
   Each floor is rendered as a 2D plan with rooms laid out
   in a grid. Room dimensions scale with capacity.
   ────────────────────────────────────────────────── */

interface RoomRect {
  room: CampusRoom
  x: number
  y: number
  w: number
  h: number
}

const PLAN_WIDTH = 800
const PLAN_HEIGHT = 500
const PADDING = 40
const CORRIDOR_HEIGHT = 60
const ROOM_GAP = 6
const ROOM_MIN_W = 80
const ROOM_MIN_H = 70

function layoutRooms(rooms: CampusRoom[]): RoomRect[] {
  if (rooms.length === 0) return []

  const usableWidth = PLAN_WIDTH - PADDING * 2
  const corridorY = PADDING + (PLAN_HEIGHT - PADDING * 2 - CORRIDOR_HEIGHT) / 2

  // Split rooms into two rows (above and below corridor)
  const topRooms = rooms.slice(0, Math.ceil(rooms.length / 2))
  const bottomRooms = rooms.slice(Math.ceil(rooms.length / 2))

  const result: RoomRect[] = []

  // Layout a row of rooms
  const layoutRow = (rowRooms: CampusRoom[], yStart: number, rowHeight: number) => {
    const totalGaps = (rowRooms.length - 1) * ROOM_GAP
    const roomWidth = Math.max(ROOM_MIN_W, (usableWidth - totalGaps) / rowRooms.length)

    rowRooms.forEach((room, i) => {
      result.push({
        room,
        x: PADDING + i * (roomWidth + ROOM_GAP),
        y: yStart,
        w: roomWidth,
        h: Math.max(ROOM_MIN_H, rowHeight),
      })
    })
  }

  // Top row — above corridor
  const topRowHeight = (corridorY - PADDING - ROOM_GAP)
  layoutRow(topRooms, PADDING, topRowHeight)

  // Bottom row — below corridor
  const bottomY = corridorY + CORRIDOR_HEIGHT + ROOM_GAP
  const bottomRowHeight = PLAN_HEIGHT - PADDING - bottomY
  if (bottomRooms.length > 0) {
    layoutRow(bottomRooms, bottomY, bottomRowHeight)
  }

  return result
}

/* ── Component ────────────────────────────────── */

interface FloorPlanSVGProps {
  building: CampusBuilding
  floor: BuildingFloor
  selectedRoom: string | null
  scheduledRoom?: string | null
  onRoomClick: (roomId: string) => void
}

export function FloorPlanSVG({
  building,
  floor,
  selectedRoom,
  scheduledRoom,
  onRoomClick,
}: FloorPlanSVGProps) {
  const { t } = useTranslation("map")

  const roomRects = useMemo(() => layoutRooms(floor.rooms), [floor.rooms])

  const corridorY = PADDING + (PLAN_HEIGHT - PADDING * 2 - CORRIDOR_HEIGHT) / 2

  const handleKeyDown = useCallback(
    (roomId: string) => (e: KeyboardEvent) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault()
        onRoomClick(roomId)
      }
    },
    [onRoomClick],
  )

  return (
    <svg
      viewBox={`0 0 ${PLAN_WIDTH} ${PLAN_HEIGHT}`}
      role="img"
      aria-label={t("floorPlan.ariaLabel", { building: building.name, floor: floor.floor })}
      className="w-full h-full select-none"
      style={{ minHeight: "100%" }}
    >
      {/* Floor background */}
      <rect
        x="0" y="0"
        width={PLAN_WIDTH} height={PLAN_HEIGHT}
        rx="12"
        fill="var(--map-svg-ground)"
      />

      {/* Building outline */}
      <rect
        x={PADDING - 8} y={PADDING - 8}
        width={PLAN_WIDTH - PADDING * 2 + 16}
        height={PLAN_HEIGHT - PADDING * 2 + 16}
        rx="8"
        fill="none"
        stroke={building.colorHex}
        strokeWidth="2"
        opacity="0.3"
      />

      {/* Corridor */}
      <rect
        x={PADDING}
        y={corridorY}
        width={PLAN_WIDTH - PADDING * 2}
        height={CORRIDOR_HEIGHT}
        rx="4"
        fill="var(--map-svg-path)"
        opacity="0.5"
      />
      <text
        x={PLAN_WIDTH / 2}
        y={corridorY + CORRIDOR_HEIGHT / 2}
        textAnchor="middle"
        dominantBaseline="central"
        fill="var(--map-room-label)"
        fontSize="11"
        fontWeight="600"
        opacity="0.5"
        aria-hidden="true"
      >
        ───── ─────
      </text>

      {/* Rooms */}
      {roomRects.map(({ room, x, y, w, h }) => {
        const isActive = selectedRoom === room.id
        const isScheduled = scheduledRoom === room.id

        return (
          <g
            key={room.id}
            role="button"
            tabIndex={0}
            aria-label={`${room.id}${room.name ? ` — ${room.name}` : ""}. ${t(`roomTypes.${room.type}`)}`}
            onClick={() => onRoomClick(room.id)}
            onKeyDown={handleKeyDown(room.id)}
            className="cursor-pointer"
          >
            {/* Room rect */}
            <rect
              x={x} y={y}
              width={w} height={h}
              rx="6"
              className="map-room"
              data-active={isActive || undefined}
              data-schedule={isScheduled || undefined}
              style={{ "--_bldg-color": building.colorVar } as CSSProperties}
            />

            {/* Room ID label */}
            <text
              x={x + w / 2}
              y={y + h / 2 - 8}
              textAnchor="middle"
              dominantBaseline="central"
              fill={isActive || isScheduled ? building.colorHex : "var(--map-room-label)"}
              fontSize="13"
              fontWeight="700"
            >
              {room.id}
            </text>

            {/* Room name (if fits) */}
            {room.name && w > 100 && (
              <text
                x={x + w / 2}
                y={y + h / 2 + 10}
                textAnchor="middle"
                dominantBaseline="central"
                fill="var(--map-room-label)"
                fontSize="9"
                fontWeight="500"
                opacity="0.7"
              >
                {room.name.length > 18 ? room.name.slice(0, 16) + "…" : room.name}
              </text>
            )}

            {/* Capacity badge */}
            {room.capacity && (
              <text
                x={x + w - 8}
                y={y + 14}
                textAnchor="end"
                fill="var(--map-room-label)"
                fontSize="8"
                fontWeight="600"
                opacity="0.4"
              >
                {room.capacity}
              </text>
            )}

            {/* Focus ring (rendered via CSS focus-visible) */}
          </g>
        )
      })}

      {/* Floor label */}
      <text
        x={PLAN_WIDTH / 2}
        y={PLAN_HEIGHT - 12}
        textAnchor="middle"
        fill={building.colorHex}
        fontSize="12"
        fontWeight="700"
        opacity="0.6"
      >
        {building.letter} — {t("floorPlan.floorLabel", { number: floor.floor })}
      </text>
    </svg>
  )
}
