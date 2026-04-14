import { useCallback, useEffect, useRef, useState, type CSSProperties } from "react"
import { useTranslation } from "react-i18next"
import { X, Clock, MapPin, Users, ChevronRight } from "lucide-react"
import type { CampusBuilding, CampusRoom, BuildingFloor } from "@/data/campusBuildings"
import { isOpenNow } from "@/utils/buildingHours"
import { getPrimaryIcon } from "@/utils/buildingCategoryIcons"
import { getRoomStatus } from "@/utils/roomStatus"
import { useAppShell } from "@/contexts/AppShellContext"
import useFocusTrap from "@/hooks/useFocusTrap"

interface TodayLesson {
  room?: string | null
  start_time?: string | null
  end_time?: string | null
}

interface MapSidebarProps {
  building: CampusBuilding | undefined
  floor: BuildingFloor | undefined
  selectedFloor: number
  selectedRoom: string | null
  onFloorChange: (floor: number) => void
  onRoomClick: (roomId: string) => void
  onClose: () => void
  isMobile: boolean
  todayLessons?: TodayLesson[]
}

/**
 * MapSidebar — building/room info panel with integrated floor selector.
 * Desktop: inline panel (no overlay). Mobile: bottom sheet.
 * Wave 101: FloorSelector integrated (was separate component for SVG mode).
 */
export function MapSidebar({
  building,
  floor,
  selectedFloor,
  selectedRoom,
  onFloorChange,
  onRoomClick,
  onClose,
  isMobile,
  todayLessons,
}: MapSidebarProps) {
  const { t } = useTranslation("map")
  const { setOverlayState } = useAppShell()
  const isOpen = !!building

  /* ── Bottom sheet drag state (mobile only) ── */
  const [sheetHeight, setSheetHeight] = useState(280)
  const [activeDrag, setActiveDrag] = useState(false)
  const dragStartY = useRef(0)
  const dragStartH = useRef(0)
  const isDragging = useRef(false)

  const SNAP_PEEK = 160
  const getViewH = () => (typeof window !== "undefined" ? window.innerHeight : 800)
  const SNAP_HALF = getViewH() * 0.5
  const SNAP_FULL = getViewH() * 0.85

  /* ── Body scroll lock for mobile sheet ── */
  useEffect(() => {
    if (!isMobile || !isOpen) return
    setOverlayState("map-sidebar", { scrollLocked: true, blurred: false })
    return () => setOverlayState("map-sidebar", null)
  }, [isMobile, isOpen, setOverlayState])

  /* ── Focus trap for mobile sheet ── */
  const sheetRef = useFocusTrap<HTMLDivElement>({
    active: isMobile && isOpen,
    onDeactivate: onClose,
  })

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
    const viewH = typeof window !== "undefined" ? window.innerHeight : 800
    const newH = Math.max(100, Math.min(dragStartH.current + dy, viewH * 0.9))
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

  const BuildingIcon = getPrimaryIcon(building.tags)

  /* ── Content ── */
  const content = (
    <div className="flex flex-col gap-4 p-4 sm:p-5">
      {/* Building photo / placeholder */}
      {building.photo ? (
        <img src={building.photo} alt={building.name} className="map-sidebar-photo" loading="lazy" />
      ) : (
        <div
          className="map-sidebar-photo-placeholder"
          style={{ background: `linear-gradient(135deg, ${building.colorHex}, color-mix(in srgb, ${building.colorHex} 60%, black))` }}
        >
          <BuildingIcon size={40} strokeWidth={1.5} />
        </div>
      )}

      {/* Building header */}
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-3">
          <div
            className="flex items-center justify-center h-10 w-10 rounded-lg font-black text-lg"
            style={{ backgroundColor: building.colorHex, color: "var(--map-on-accent)" }}
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
            className="map-control-btn min-h-[44px] min-w-[44px] flex items-center justify-center rounded-lg"
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

      {/* Hours — structured Пн-Пт / Сб / Вс */}
      <div className="flex flex-col gap-1 text-xs">
        <div className="flex items-center gap-1.5 mb-1">
          <Clock className="h-3.5 w-3.5 text-[var(--color-teal-500)]" />
          <span
            className="font-bold text-[10px] px-1.5 py-0.5 rounded-full"
            style={{
              backgroundColor: isOpenNow(building.hours)
                ? "color-mix(in srgb, var(--color-emerald-500) 15%, transparent)"
                : "color-mix(in srgb, var(--color-rose-500) 15%, transparent)",
              color: isOpenNow(building.hours)
                ? "var(--color-emerald-500)"
                : "var(--color-rose-500)",
            }}
          >
            {isOpenNow(building.hours) ? t("hours.openNow") : t("hours.closedNow")}
          </span>
        </div>
        <div className="flex flex-wrap gap-x-3 gap-y-0.5 text-[var(--text-secondary)]">
          <span><span className="font-semibold">{t("hours.weekday")}:</span> {building.hours.weekday}</span>
          <span><span className="font-semibold">{t("hours.saturday")}:</span> {building.hours.saturday}</span>
          <span><span className="font-semibold">{t("hours.sunday")}:</span> {building.hours.sunday}</span>
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

      {/* Floor selector — replaces deleted FloorSelector.tsx (Wave 101) */}
      {building.floors.length > 1 && (
        <div>
          <p className="text-[10px] font-bold uppercase tracking-wider text-[var(--text-tertiary)] mb-2">
            {t("sidebar.floor")}
          </p>
          <div
            role="radiogroup"
            aria-label={t("floorPlan.selectFloor")}
            className="flex flex-wrap gap-1.5"
          >
            {building.floors.map(({ floor: flNum }) => {
              const isActive = selectedFloor === flNum
              return (
                <button
                  key={flNum}
                  type="button"
                  role="radio"
                  aria-checked={isActive}
                  onClick={() => onFloorChange(flNum)}
                  className="min-h-[44px] min-w-[44px] flex items-center justify-center rounded-lg text-xs font-bold transition-colors"
                  style={{
                    backgroundColor: isActive
                      ? `color-mix(in srgb, ${building.colorHex} 15%, var(--bg-surface))`
                      : "var(--bg-surface-hover)",
                    color: isActive ? building.colorHex : "var(--text-secondary)",
                  }}
                >
                  {flNum}
                </button>
              )
            })}
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
              const status = todayLessons ? getRoomStatus(room.id, todayLessons) : null
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
                  <div className="flex items-center gap-1.5 min-w-0">
                    <span className="font-bold" style={isActive ? { color: building.colorHex } : undefined}>
                      {room.id}
                    </span>
                    {room.name && (
                      <span className="text-[var(--text-tertiary)] truncate">{room.name}</span>
                    )}
                  </div>
                  <div className="flex items-center gap-1.5 shrink-0">
                    {status && (
                      <span
                        className="text-[9px] font-bold px-1.5 py-0.5 rounded-full whitespace-nowrap"
                        style={{
                          backgroundColor: status.status === "free"
                            ? "color-mix(in srgb, var(--color-emerald-500) 15%, transparent)"
                            : "color-mix(in srgb, var(--color-rose-500) 15%, transparent)",
                          color: status.status === "free"
                            ? "var(--color-emerald-500)"
                            : "var(--color-rose-500)",
                        }}
                      >
                        {status.status === "free"
                          ? t("sidebar.roomFree")
                          : t("sidebar.roomBusy", { time: status.busyUntil })}
                      </span>
                    )}
                    <ChevronRight className="h-3 w-3 text-[var(--text-tertiary)] opacity-50" />
                  </div>
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
        ref={sheetRef}
        role="dialog"
        aria-modal="true"
        aria-label={building.name}
        className="fixed inset-x-0 bottom-0 z-50 bg-[var(--map-sidebar-bg)] rounded-t-2xl"
        style={{
          height: `${sheetHeight}px`,
          boxShadow: "var(--map-sidebar-shadow)",
          transition: activeDrag ? "none" : "height 0.3s var(--ease-premium, ease-out)",
        }}
      >
        {/* Drag handle */}
        <div
          aria-roledescription="drag handle"
          aria-label={t("sidebar.dragToResize")}
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
