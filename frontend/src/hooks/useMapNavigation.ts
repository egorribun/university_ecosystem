import { useCallback, useEffect, useMemo, useRef, useState } from "react"

/**
 * useMapNavigation — zoom/pan state for the campus map.
 *
 * - Wheel zoom: 1x → 3x (passive: false to prevent page scroll)
 * - Pointer drag pan when zoom > 1
 * - Pinch-zoom via two-finger touch gesture
 * - Double-click to reset
 * - Boundary clamping prevents over-scroll
 * - 0 new dependencies — pure DOM events + CSS transforms
 *
 * Wave 91
 */

const MIN_ZOOM = 1
const MAX_ZOOM = 3
const ZOOM_STEP = 0.15
const PAN_BOUNDARY_FACTOR = 0.4 // how far beyond center can we pan (fraction of container)

interface MapNavigationState {
  zoom: number
  pan: { x: number; y: number }
}

export function useMapNavigation() {
  const containerRef = useRef<HTMLDivElement>(null)
  const [state, setState] = useState<MapNavigationState>({
    zoom: MIN_ZOOM,
    pan: { x: 0, y: 0 },
  })

  // activeDrag as state (not ref) — React Compiler forbids ref access during render
  const [activeDrag, setActiveDrag] = useState(false)

  // Track drag state in refs to avoid re-renders during drag
  const isDragging = useRef(false)
  const dragStart = useRef({ x: 0, y: 0 })
  const panStart = useRef({ x: 0, y: 0 })
  // Pinch zoom
  const pinchStartDist = useRef<number | null>(null)
  const pinchStartZoom = useRef(MIN_ZOOM)

  /** Clamp pan within boundaries based on current zoom */
  const clampPan = useCallback(
    (x: number, y: number, zoom: number): { x: number; y: number } => {
      if (zoom <= 1) return { x: 0, y: 0 }
      const el = containerRef.current
      if (!el) return { x, y }
      const { width, height } = el.getBoundingClientRect()
      const maxPanX = width * PAN_BOUNDARY_FACTOR * (zoom - 1)
      const maxPanY = height * PAN_BOUNDARY_FACTOR * (zoom - 1)
      return {
        x: Math.max(-maxPanX, Math.min(maxPanX, x)),
        y: Math.max(-maxPanY, Math.min(maxPanY, y)),
      }
    },
    [],
  )

  /** Zoom in by one step */
  const zoomIn = useCallback(() => {
    setState((prev) => {
      const next = Math.min(MAX_ZOOM, prev.zoom + ZOOM_STEP)
      return { zoom: next, pan: clampPan(prev.pan.x, prev.pan.y, next) }
    })
  }, [clampPan])

  /** Zoom out by one step */
  const zoomOut = useCallback(() => {
    setState((prev) => {
      const next = Math.max(MIN_ZOOM, prev.zoom - ZOOM_STEP)
      return { zoom: next, pan: clampPan(prev.pan.x, prev.pan.y, next) }
    })
  }, [clampPan])

  /** Reset to default view */
  const resetView = useCallback(() => {
    setState({ zoom: MIN_ZOOM, pan: { x: 0, y: 0 } })
  }, [])

  /* ── Wheel zoom ── */
  useEffect(() => {
    const el = containerRef.current
    if (!el) return

    const onWheel = (e: WheelEvent) => {
      e.preventDefault()
      const delta = e.deltaY > 0 ? -ZOOM_STEP : ZOOM_STEP
      setState((prev) => {
        const next = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, prev.zoom + delta))
        return { zoom: next, pan: clampPan(prev.pan.x, prev.pan.y, next) }
      })
    }

    el.addEventListener("wheel", onWheel, { passive: false })
    return () => el.removeEventListener("wheel", onWheel)
  }, [clampPan])

  /* ── Pointer drag pan ── */
  useEffect(() => {
    const el = containerRef.current
    if (!el) return

    const onPointerDown = (e: PointerEvent) => {
      // Only pan when zoomed in, and only with primary button
      if (state.zoom <= 1 || e.button !== 0) return
      // Don't intercept clicks on buildings (they have role="button")
      const target = e.target as HTMLElement
      if (target.closest("[role='button']")) return

      isDragging.current = true
      setActiveDrag(true)
      dragStart.current = { x: e.clientX, y: e.clientY }
      panStart.current = { ...state.pan }
      el.setPointerCapture(e.pointerId)
      el.style.cursor = "grabbing"
    }

    const onPointerMove = (e: PointerEvent) => {
      if (!isDragging.current) return
      const dx = (e.clientX - dragStart.current.x) / state.zoom
      const dy = (e.clientY - dragStart.current.y) / state.zoom
      setState((prev) => ({
        ...prev,
        pan: clampPan(panStart.current.x + dx, panStart.current.y + dy, prev.zoom),
      }))
    }

    const onPointerUp = (e: PointerEvent) => {
      if (isDragging.current) {
        isDragging.current = false
        setActiveDrag(false)
        el.releasePointerCapture(e.pointerId)
        el.style.cursor = state.zoom > 1 ? "grab" : ""
      }
    }

    el.addEventListener("pointerdown", onPointerDown)
    el.addEventListener("pointermove", onPointerMove)
    el.addEventListener("pointerup", onPointerUp)
    el.addEventListener("pointercancel", onPointerUp)

    return () => {
      el.removeEventListener("pointerdown", onPointerDown)
      el.removeEventListener("pointermove", onPointerMove)
      el.removeEventListener("pointerup", onPointerUp)
      el.removeEventListener("pointercancel", onPointerUp)
    }
  }, [state.zoom, state.pan, clampPan])

  /* ── Pinch zoom (touch) ── */
  useEffect(() => {
    const el = containerRef.current
    if (!el) return

    const getTouchDist = (touches: TouchList): number => {
      if (touches.length < 2) return 0
      const dx = touches[1].clientX - touches[0].clientX
      const dy = touches[1].clientY - touches[0].clientY
      return Math.hypot(dx, dy)
    }

    const onTouchStart = (e: TouchEvent) => {
      if (e.touches.length === 2) {
        e.preventDefault()
        pinchStartDist.current = getTouchDist(e.touches)
        pinchStartZoom.current = state.zoom
      }
    }

    const onTouchMove = (e: TouchEvent) => {
      if (e.touches.length === 2 && pinchStartDist.current !== null) {
        e.preventDefault()
        const currentDist = getTouchDist(e.touches)
        const scale = currentDist / pinchStartDist.current
        const newZoom = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, pinchStartZoom.current * scale))
        setState((prev) => ({
          zoom: newZoom,
          pan: clampPan(prev.pan.x, prev.pan.y, newZoom),
        }))
      }
    }

    const onTouchEnd = () => {
      pinchStartDist.current = null
    }

    el.addEventListener("touchstart", onTouchStart, { passive: false })
    el.addEventListener("touchmove", onTouchMove, { passive: false })
    el.addEventListener("touchend", onTouchEnd)

    return () => {
      el.removeEventListener("touchstart", onTouchStart)
      el.removeEventListener("touchmove", onTouchMove)
      el.removeEventListener("touchend", onTouchEnd)
    }
  }, [state.zoom, clampPan])

  /* ── Double-click to reset ── */
  useEffect(() => {
    const el = containerRef.current
    if (!el) return

    const onDblClick = (e: MouseEvent) => {
      // Don't reset if clicking a building
      const target = e.target as HTMLElement
      if (target.closest("[role='button']")) return
      resetView()
    }

    el.addEventListener("dblclick", onDblClick)
    return () => el.removeEventListener("dblclick", onDblClick)
  }, [resetView])

  /** CSS transform style for the SVG container */
  const transformStyle = useMemo(
    () => ({
      transform: `scale(${state.zoom}) translate(${state.pan.x}px, ${state.pan.y}px)`,
      transformOrigin: "center center",
      transition: activeDrag ? "none" : "transform 0.15s var(--ease-premium, ease-out)",
      willChange: "transform" as const,
      cursor: state.zoom > 1 ? "grab" : undefined,
    }),
    [state.zoom, state.pan, activeDrag],
  )

  return {
    containerRef,
    zoom: state.zoom,
    pan: state.pan,
    zoomIn,
    zoomOut,
    resetView,
    transformStyle,
    canZoomIn: state.zoom < MAX_ZOOM,
    canZoomOut: state.zoom > MIN_ZOOM,
    isZoomed: state.zoom > MIN_ZOOM,
  }
}
