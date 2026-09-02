import { useCallback, useEffect, useId, useMemo, useRef, useState, type CSSProperties } from "react"
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

type OverlaySetter = (id: string, state: { scrollLocked: boolean; blurred: boolean } | null) => void

export function getViewportHeight(): number {
  return typeof window === "undefined" ? 800 : window.innerHeight
}

/** Safe-area fallback used by the mobile sheet on notched devices. */
export function getMobileSheetSafeAreaPadding(): string {
  return "env(safe-area-inset-bottom, 0px)"
}

/** Public alias retained for consumers that use the CSS contract directly. */
export const MOBILE_SHEET_SAFE_AREA_PADDING = getMobileSheetSafeAreaPadding()

/** Stable dependency contracts are named so they can be audited independently. */
export function getSnapPointMemoDeps(): readonly unknown[] {
  return []
}

export function getOverlayEffectDeps(
  isMobile: boolean,
  isOpen: boolean,
  setOverlayState: OverlaySetter
): readonly unknown[] {
  return [isMobile, isOpen, setOverlayState]
}

export function getSnapToNearestDeps(
  snapPeek: number,
  snapHalf: number,
  snapFull: number
): readonly unknown[] {
  return [snapPeek, snapHalf, snapFull]
}

export function getDragMoveDeps(): readonly unknown[] {
  return []
}

export function getInitialSheetReadyState(): boolean {
  return false
}

export function getSheetResetHeight(isMobile: boolean, snapHalf: number): number | undefined {
  return isMobile ? snapHalf : undefined
}

export function shouldApplySheetResetHeight(
  resetHeight: number | undefined
): resetHeight is number {
  return resetHeight !== undefined
}

/** Apply a mobile sheet reset only when the responsive height was derived. */
export function applySheetResetHeight(
  resetHeight: number | undefined,
  setSheetHeight: (height: number) => void
): void {
  if (shouldApplySheetResetHeight(resetHeight)) setSheetHeight(resetHeight)
}

export function getScrollKey(building: CampusBuilding | undefined): string {
  return building?.letter ?? ""
}

/**
 * Keep the initial mobile sheet geometry as a named, SSR-safe contract.  The
 * entrance effect may reset the height when a building changes, but the first
 * render still needs a deterministic viewport-relative value for hydration and
 * for consumers that render the sheet outside the browser.
 */
export function getInitialSheetHeight(): number {
  return getViewportHeight() * 0.5
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
  const sidebarTitleId = useId()
  const sidebarDescriptionId = useId()

  /* ── Bottom sheet drag state (mobile only) ── */
  const [sheetHeight, setSheetHeight] = useState(getInitialSheetHeight)
  /** Scroll locked during entrance animation — prevents focus-trap auto-scroll */
  const [sheetReady, setSheetReady] = useState(getInitialSheetReadyState)
  const dragStartY = useRef(0)
  const dragStartH = useRef(0)
  const isDragging = useRef(false)

  // Stabilize snap points — prevents snapToNearest recreation every render (CQ-110-01)
  const [{ SNAP_PEEK, SNAP_HALF, SNAP_FULL }] = useState(() => {
    const vh = getViewportHeight()
    return { SNAP_PEEK: 160, SNAP_HALF: vh * 0.5, SNAP_FULL: vh * 0.85 }
  })

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
    // FIX-110-sidebar: `false` prevents auto-focus on the first tabbable element,
    // which would cause the browser to scroll the overflow container to bring a
    // deep floor/room button into view — hiding the top content (photo, header).
    initialFocus: false,
  })

  const snapToNearest = useCallback(() => {
    const h = sheetHeight
    const snaps = [SNAP_PEEK, SNAP_HALF, SNAP_FULL]
    const closest = snaps.reduce((prev, curr) =>
      Math.abs(curr - h) < Math.abs(prev - h) ? curr : prev
    )
    setSheetHeight(closest)
  }, [SNAP_PEEK, SNAP_HALF, SNAP_FULL, sheetHeight])

  /** setPointerCapture ensures reliable tracking even when pointer escapes the handle (CQ-110-02) */
  const handleDragStart = useCallback(
    (e: React.PointerEvent) => {
      isDragging.current = true
      dragStartY.current = e.clientY
      dragStartH.current = sheetHeight
      ;(e.target as HTMLElement).setPointerCapture(e.pointerId)
    },
    [sheetHeight]
  )

  /** Keyboard equivalent of the touch drag handle for WCAG 2.2 Target Size/Keyboard access. */
  const handleResizeKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLDivElement>) => {
      const snaps = [SNAP_PEEK, SNAP_HALF, SNAP_FULL]
      const nearestIndex = snaps.reduce(
        (best, current, index) =>
          Math.abs(current - sheetHeight) < Math.abs(snaps[best]! - sheetHeight) ? index : best,
        0
      )

      let nextIndex: number | undefined
      if (e.key === "ArrowUp" || e.key === "ArrowRight" || e.key === "PageUp") {
        nextIndex = Math.min(nearestIndex + 1, snaps.length - 1)
      } else if (e.key === "ArrowDown" || e.key === "ArrowLeft" || e.key === "PageDown") {
        nextIndex = Math.max(nearestIndex - 1, 0)
      } else if (e.key === "Home") {
        nextIndex = 0
      } else if (e.key === "End") {
        nextIndex = snaps.length - 1
      }

      if (nextIndex === undefined || nextIndex === nearestIndex) return
      e.preventDefault()
      setSheetHeight(snaps[nextIndex]!)
    },
    [SNAP_FULL, SNAP_HALF, SNAP_PEEK, sheetHeight]
  )

  const handleDragMove = useCallback(
    (clientY: number) => {
      if (!isMobile || !isDragging.current) return
      const dy = dragStartY.current - clientY
      const viewH = getViewportHeight()
      const newH = Math.max(100, Math.min(dragStartH.current + dy, viewH * 0.9))
      setSheetHeight(newH)
    },
    [isMobile]
  )

  const handleDragEnd = useCallback(
    (e: React.PointerEvent) => {
      if (!isDragging.current) return
      isDragging.current = false
      ;(e.target as HTMLElement).releasePointerCapture(e.pointerId)
      snapToNearest()
    },
    [snapToNearest]
  )

  /**
   * FIX-109-10: Fresh scroll key forces React to remount the scroll container
   * when building changes. This guarantees scrollTop=0 on the new DOM element,
   * regardless of focus trap, browser scroll restoration, or content layout.
   * A `key` change is the only approach that reliably beats all timing issues.
   */
  const scrollKey = getScrollKey(building)

  // Reset height + unlock scroll after CSS animation completes
  useEffect(() => {
    if (!building) {
      setSheetReady(getInitialSheetReadyState())
      return
    }
    const resetHeight = getSheetResetHeight(isMobile, SNAP_HALF)
    applySheetResetHeight(resetHeight, setSheetHeight)
    setSheetReady(getInitialSheetReadyState())
    // Enable scroll AFTER CSS @keyframes entrance (350ms)
    // Enable scroll AFTER CSS map-sheet-enter animation (250ms) + paint buffer
    function enableSheetScrolling() {
      setSheetReady(true)
    }
    const id = setTimeout(enableSheetScrolling, 260)
    function cancelSheetEntranceTimer() {
      clearTimeout(id)
    }
    return cancelSheetEntranceTimer
  }, [building, isMobile, SNAP_HALF])

  const selectedRoomData: CampusRoom | undefined = floor?.rooms.find((r) => r.id === selectedRoom)

  /** Memoized room list items — avoids re-rendering all buttons on unrelated state changes (PERF-109-03). */
  const roomListItems = useMemo(() => {
    if (!floor || !building) return null
    return floor.rooms.map((room) => {
      const isActive = selectedRoom === room.id
      const status = todayLessons ? getRoomStatus(room.id, todayLessons) : null
      return (
        <button
          key={room.id}
          type="button"
          onClick={() => onRoomClick(room.id)}
          className={`flex items-center justify-between gap-2 px-3 py-2 rounded-lg text-left transition-colors text-xs${isActive ? " map-accent-tint-light" : ""}`}
        >
          <div className="flex items-center gap-1.5 min-w-0">
            <span
              className="font-bold"
              style={isActive ? { color: "var(--_bldg-color)" } : undefined}
            >
              {room.id}
            </span>
            {room.name && <span className="text-[var(--text-tertiary)] truncate">{room.name}</span>}
          </div>
          <div className="flex items-center gap-1.5 shrink-0">
            {status && (
              <span
                className="text-[9px] font-bold px-1.5 py-0.5 rounded-full whitespace-nowrap"
                style={{
                  backgroundColor:
                    status.status === "free"
                      ? "color-mix(in srgb, var(--color-emerald-500) 15%, transparent)"
                      : "color-mix(in srgb, var(--color-rose-500) 15%, transparent)",
                  color:
                    status.status === "free" ? "var(--color-emerald-500)" : "var(--color-rose-500)",
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
    })
  }, [floor, building, selectedRoom, todayLessons, t, onRoomClick])

  if (!isOpen) return null

  const BuildingIcon = getPrimaryIcon(building.tags)

  /* ── Content ── */
  const content = (
    <div
      className="flex flex-col gap-4 p-4 sm:p-5"
      style={{ "--_bldg-color": building.colorHex } as CSSProperties}
    >
      {/* Building photo / placeholder */}
      {building.photo ? (
        <img
          src={building.photo}
          alt={building.name}
          className="map-sidebar-photo"
          loading="lazy"
        />
      ) : (
        <div
          className="map-sidebar-photo-placeholder"
          style={{
            background: `linear-gradient(135deg, ${building.colorHex}, color-mix(in srgb, ${building.colorHex} 60%, black))`,
          }}
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
            {/* Wave 121 polish: h3 → h2 — sidebar is a page sub-region under the
                /map h1, no intermediate h2 exists. Lighthouse 13 heading-order
                audit catches the h1 → h3 skip; chrome-devtools live-axe didn't.
                Page heading sequence is now h1 (MapHeader) → h2 (this) →
                downstream h3 in InstallPrompt (when visible). */}
            <h2 id={sidebarTitleId} className="font-bold text-sm text-text-primary">
              {building.name}
            </h2>
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
      <p id={sidebarDescriptionId} className="text-xs text-[var(--text-secondary)] leading-relaxed">
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
          <span>
            <span className="font-semibold">{t("hours.weekday")}:</span> {building.hours.weekday}
          </span>
          <span>
            <span className="font-semibold">{t("hours.saturday")}:</span> {building.hours.saturday}
          </span>
          <span>
            <span className="font-semibold">{t("hours.sunday")}:</span> {building.hours.sunday}
          </span>
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
              <span key={a} className="map-category-chip text-[10px] px-2 py-0.5">
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
                  className={`min-h-[44px] min-w-[44px] flex items-center justify-center rounded-lg text-xs font-bold transition-colors${isActive ? " map-accent-tint-medium" : ""}`}
                  style={{
                    backgroundColor: isActive ? undefined : "var(--bg-surface-hover)",
                    color: isActive ? "var(--_bldg-color)" : "var(--text-secondary)",
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
                <p
                  data-testid="selected-room-name"
                  className="text-xs text-[var(--text-secondary)] mt-0.5"
                >
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

      {/* Room list — memoized via roomListItems (PERF-109-03) */}
      {roomListItems ? (
        <div>
          <p className="text-[10px] font-bold uppercase tracking-wider text-[var(--text-tertiary)] mb-2">
            {t("sidebar.rooms")} — {t("sidebar.roomCount", { count: floor!.rooms.length })}
          </p>
          <div className="flex flex-col gap-1">{roomListItems}</div>
        </div>
      ) : null}
    </div>
  )

  /* ── Mobile bottom sheet ── */
  if (isMobile) {
    return (
      <div
        key={scrollKey}
        ref={sheetRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={sidebarTitleId}
        aria-describedby={sidebarDescriptionId}
        className="fixed inset-x-0 bottom-0 z-50 bg-[var(--map-sidebar-bg)] rounded-t-2xl map-sheet-slide-up"
        style={{
          height: `${sheetHeight}px`,
          paddingBottom: getMobileSheetSafeAreaPadding(),
          boxShadow: "var(--map-sidebar-shadow)",
        }}
      >
        {/* Drag handle */}
        <div
          aria-roledescription="drag handle"
          aria-label={t("sidebar.dragToResize")}
          role="slider"
          tabIndex={0}
          aria-orientation="vertical"
          aria-valuemin={100}
          aria-valuemax={Math.round(getViewportHeight() * 0.9)}
          aria-valuenow={Math.round(sheetHeight)}
          className="flex min-h-[44px] justify-center py-3 cursor-grab active:cursor-grabbing touch-none"
          onPointerDown={handleDragStart}
          onPointerMove={(e) => handleDragMove(e.clientY)}
          onPointerUp={handleDragEnd}
          onPointerCancel={handleDragEnd}
          onKeyDown={handleResizeKeyDown}
        >
          <div className="w-10 h-1 rounded-full bg-[var(--text-tertiary)] opacity-30" />
        </div>
        <div
          className={`${sheetReady ? "overflow-y-auto" : "overflow-hidden"} scrollbar-hide`}
          style={{ height: `${sheetHeight - 40}px` }}
        >
          {content}
        </div>
      </div>
    )
  }

  /* ── Desktop slide-over ── */
  return (
    <div
      key={scrollKey}
      className="map-sidebar-container w-80 lg:w-96 shrink-0 overflow-y-auto rounded-xl scrollbar-hide map-sidebar-fade-in"
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
