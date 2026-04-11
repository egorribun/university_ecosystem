import { useCallback, useEffect, useRef, useState, type CSSProperties } from "react"
import { useTranslation } from "react-i18next"
import { X, Clock, MapPin, Users, ChevronRight } from "lucide-react"
import type { CampusBuilding, CampusRoom, BuildingFloor } from "@/data/campusBuildings"

interface MapSidebarProps {
  building: CampusBuilding | undefined
  floor: BuildingFloor | undefined
  selectedRoom: string | null
  onRoomClick: (roomId: string) => void
  onClose: () => void
  isMobile: boolean
}

/**
 * MapSidebar — building/room info panel.
 * Desktop: inline panel (no overlay). Mobile: bottom sheet.
 */
export function MapSidebar({
  building,
  floor,
  selectedRoom,
  onRoomClick,
  onClose,
  isMobile,
}: MapSidebarProps) {
  const { t } = useTranslation("map")
  const isOpen = !!building

  /* ── Bottom sheet drag state (mobile only) ── */
  const [sheetHeight, setSheetHeight] = useState(280)
  const [activeDrag, setActiveDrag] = useState(false)
  const dragStartY = useRef(0)
  const dragStartH = useRef(0)
  const isDragging = useRef(false)

  const SNAP_PEEK = 160
  const SNAP_HALF = typeof window !== "undefined" ? window.innerHeight * 0.5 : 400
  const SNAP_FULL = typeof window !== "undefined" ? window.innerHeight * 0.85 : 700

  const snapToNearest = useCallback(
    (h: number) => {
      const snaps = [SNAP_PEEK, SNAP_HALF, SNAP_FULL]
      const closest = snaps.reduce((prev, curr) =>
        Math.abs(curr - h) < Math.abs(prev - h) ? curr : prev,
      )
      setSheetHeight(closest)
    },
    [SNAP_PEEK, SNAP_HALF, SNAP_FULL],
  )

  const handleDragStart = useCallback(
    (clientY: number) => {
      isDragging.current = true
      setActiveDrag(true)
      dragStartY.current = clientY
      dragStartH.current = sheetHeight
    },
    [sheetHeight],
  )

  const handleDragMove = useCallback((clientY: number) => {
    if (!isDragging.current) return
    const dy = dragStartY.current - clientY
    const newH = Math.max(100, Math.min(dragStartH.current + dy, window.innerHeight * 0.9))
    setSheetHeight(newH)
  }, [])

  const handleDragEnd = useCallback(() => {
    if (!isDragging.current) return
    isDragging.current = false
    setActiveDrag(false)
    snapToNearest(sheetHeight)
  }, [sheetHeight, snapToNearest])

  // Reset sheet height when building changes
  useEffect(() => {
    if (building && isMobile) setSheetHeight(SNAP_HALF)
  }, [building, isMobile, SNAP_HALF])

  const selectedRoomData: CampusRoom | undefined = floor?.rooms.find(
    (r) => r.id === selectedRoom,
  )

  if (!isOpen) return null

  /* ── Content ── */
  const content = (
    <div className="flex flex-col gap-4 p-4 sm:p-5">
      {/* Building header */}
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-3">
          <div
            className="flex items-center justify-center h-10 w-10 rounded-lg text-white font-black text-lg"
            style={{ backgroundColor: building.colorHex }}
          >
            {building.letter}
          </div>
          <div>
            <h3 className="font-bold text-sm text-text-primary">{building.name}</h3>
            <p className="text-xs text-[var(--text-tertiary)] flex items-center gap-1 mt-0.5">
              <MapPin className="h-3 w-3 shrink-0" />
              {building.address}
            </p>
          </div>
        </div>
        {!isMobile && (
          <button
            type="button"
            onClick={onClose}
            className="map-zoom-btn h-8 w-8 flex items-center justify-center rounded-lg"
            aria-label={t("sidebar.close")}
          >
            <X className="h-4 w-4" />
          </button>
        )}
      </div>

      {/* Description */}
      <p className="text-xs text-[var(--text-secondary)] leading-relaxed">
        {building.description}
      </p>

      {/* Hours + amenities */}
      <div className="flex flex-wrap gap-3 text-xs">
        <div className="flex items-center gap-1.5 text-[var(--text-secondary)]">
          <Clock className="h-3.5 w-3.5 text-[var(--color-teal-500)]" />
          <span className="font-semibold">{building.hours}</span>
        </div>
      </div>

      {/* Amenities */}
      {building.amenities.length > 0 && (
        <div className="map-amenities">
          <p className="text-[10px] font-bold uppercase tracking-wider text-[var(--text-tertiary)] mb-1.5">
            {t("sidebar.amenities")}
          </p>
          <div className="flex flex-wrap gap-1.5">
            {building.amenities.map((a) => (
              <span
                key={a}
                className="map-category-chip text-[10px] px-2 py-0.5"
              >
                {a}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Selected room detail */}
      {selectedRoomData && (
        <div
          className="map-card-matte p-3"
          style={{ "--_accent": building.colorVar } as CSSProperties}
        >
          <div className="flex items-center justify-between">
            <div>
              <p className="font-bold text-sm" style={{ color: building.colorHex }}>
                {selectedRoomData.id}
              </p>
              {selectedRoomData.name && (
                <p className="text-xs text-[var(--text-secondary)] mt-0.5">
                  {selectedRoomData.name}
                </p>
              )}
            </div>
            <div className="text-right text-xs text-[var(--text-tertiary)]">
              <p>{t(`roomTypes.${selectedRoomData.type}`)}</p>
              {selectedRoomData.capacity && (
                <p className="flex items-center gap-1 mt-0.5">
                  <Users className="h-3 w-3" />
                  {selectedRoomData.capacity}
                </p>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Room list */}
      {floor && (
        <div>
          <p className="text-[10px] font-bold uppercase tracking-wider text-[var(--text-tertiary)] mb-2">
            {t("sidebar.rooms")} — {t("sidebar.roomCount", { count: floor.rooms.length })}
          </p>
          <div className="flex flex-col gap-1">
            {floor.rooms.map((room) => {
              const isActive = selectedRoom === room.id
              return (
                <button
                  key={room.id}
                  type="button"
                  onClick={() => onRoomClick(room.id)}
                  className="flex items-center justify-between gap-2 px-3 py-2 rounded-lg text-left transition-colors text-xs"
                  style={{
                    backgroundColor: isActive
                      ? `color-mix(in srgb, ${building.colorHex} 12%, var(--bg-surface))`
                      : undefined,
                  }}
                >
                  <div>
                    <span className="font-bold" style={isActive ? { color: building.colorHex } : undefined}>
                      {room.id}
                    </span>
                    {room.name && (
                      <span className="text-[var(--text-tertiary)] ml-1.5">{room.name}</span>
                    )}
                  </div>
                  <ChevronRight className="h-3 w-3 text-[var(--text-tertiary)] opacity-50" />
                </button>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )

  /* ── Mobile bottom sheet ── */
  if (isMobile) {
    return (
      <div
        className="fixed inset-x-0 bottom-0 z-50 bg-[var(--map-sidebar-bg)] rounded-t-2xl"
        style={{
          height: `${sheetHeight}px`,
          boxShadow: "var(--map-sidebar-shadow)",
          transition: activeDrag ? "none" : "height 0.3s var(--ease-premium, ease-out)",
        }}
      >
        {/* Drag handle */}
        <div
          className="flex justify-center py-3 cursor-grab active:cursor-grabbing touch-none"
          onPointerDown={(e) => handleDragStart(e.clientY)}
          onPointerMove={(e) => handleDragMove(e.clientY)}
          onPointerUp={handleDragEnd}
          onPointerCancel={handleDragEnd}
        >
          <div className="w-10 h-1 rounded-full bg-[var(--text-tertiary)] opacity-30" />
        </div>
        <div className="overflow-y-auto" style={{ height: `${sheetHeight - 40}px` }}>
          {content}
        </div>
      </div>
    )
  }

  /* ── Desktop slide-over ── */
  return (
    <div
      className="map-sidebar-container w-80 lg:w-96 shrink-0 overflow-y-auto rounded-xl"
      style={{
        backgroundColor: "var(--map-sidebar-bg)",
        boxShadow: "var(--map-sidebar-shadow)",
        maxHeight: "calc(100vh - 200px)",
      }}
    >
      {content}
    </div>
  )
}
