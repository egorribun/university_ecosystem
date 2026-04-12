import { useState, useCallback, useEffect, useMemo, useRef, useSyncExternalStore, lazy, Suspense } from "react"
import { AnimatePresence, motion, useReducedMotion } from "framer-motion"
import { useTranslation } from "react-i18next"
import useMediaQuery from "@/hooks/useMediaQuery"
import { breakpoints } from "@/theme/tokens"
import { MapBackdrop } from "@/components/map/MapBackdrop"
import { MapHeader } from "@/components/map/MapHeader"
import { CampusMapSVG } from "@/components/map/CampusMapSVG"
import { FloorPlanSVG } from "@/components/map/FloorPlanSVG"
import { FloorSelector } from "@/components/map/FloorSelector"
import { MapSidebar } from "@/components/map/MapSidebar"
import { MapSearchBar } from "@/components/map/MapSearchBar"
import { MapCategoryFilter } from "@/components/map/MapCategoryFilter"
import { MapLayerToggle } from "@/components/map/MapLayerToggle"
import { MapZoomControls } from "@/components/map/MapZoomControls"
import { useNextLesson } from "@/hooks/useNextLesson"
import { useMapNavigation } from "@/hooks/useMapNavigation"
import { useTimeOfDay } from "@/hooks/useTimeOfDay"
import { ArrowLeft } from "lucide-react"
import {
  getCampusBuildings,
  type BuildingLetter,
  type MapCategory,
  type CampusBuilding,
} from "@/data/campusBuildings"
import FadeSection from "@/components/motion/FadeSection"
import { CAMPUS_COORDINATES } from "@/constants/campus"
import type { MapRef } from "react-map-gl/maplibre"

export type MapViewMode = "campus" | "floorplan" | "map"

/* ── Reactive dark mode detection ── */
function subscribeToDarkMode(cb: () => void) {
  const mq = window.matchMedia("(prefers-color-scheme: dark)")
  mq.addEventListener("change", cb)
  const observer = new MutationObserver(cb)
  observer.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] })
  return () => { mq.removeEventListener("change", cb); observer.disconnect() }
}
function getIsDark() {
  return document.documentElement.classList.contains("dark")
}
const SERVER_SNAPSHOT = false

/** Lazy-load MapLibre GL — CSS + JS only loaded when map mode is activated */
const MapLibreMapComponent = lazy(() => import("@/components/map/MapLibreMap"))

/**
 * MapFeature — central orchestrator for the campus map page.
 * Three view modes: map (MapLibre GL), campus (isometric SVG), floorplan.
 */
export function MapFeature() {
  const { t, i18n } = useTranslation("map")
  const prefersReducedMotion = useReducedMotion() ?? false
  const isNarrow = useMediaQuery(`(max-width: ${breakpoints.content})`)
  const timePeriod = useTimeOfDay()
  const isDark = useSyncExternalStore(subscribeToDarkMode, getIsDark, () => SERVER_SNAPSHOT)

  /* ── Campus data ── */
  const buildings = useMemo(
    () => getCampusBuildings(i18n.resolvedLanguage ?? i18n.language),
    [i18n.resolvedLanguage, i18n.language],
  )

  /* ── View state ── */
  const [viewMode, setViewMode] = useState<MapViewMode>("map")
  const [selectedBuilding, setSelectedBuilding] = useState<BuildingLetter | null>(null)
  const [selectedFloor, setSelectedFloor] = useState<number>(1)
  const [selectedRoom, setSelectedRoom] = useState<string | null>(null)
  const [activeCategory, setActiveCategory] = useState<MapCategory>("all")
  const [hoveredBuilding, setHoveredBuilding] = useState<BuildingLetter | null>(null)

  /* ── Schedule integration ── */
  const nextLessonInfo = useNextLesson()

  /* ── Zoom/Pan (isometric SVG mode) ── */
  const {
    containerRef: mapContainerRef,
    zoomIn, zoomOut, resetView,
    transformStyle,
    canZoomIn, canZoomOut, isZoomed,
  } = useMapNavigation()

  /* ── MapLibre GL map ref (map mode) ── */
  const mapLibreRef = useRef<MapRef | null>(null)

  /* ── Building selection ── */
  const handleBuildingClick = useCallback((letter: BuildingLetter) => {
    setSelectedBuilding(letter)
    setSelectedFloor(1)
    setSelectedRoom(null)
    // In map mode, just select — don't switch to floorplan
    if (viewMode !== "map") {
      setViewMode("floorplan")
    }
  }, [viewMode])

  const handleBackToCampus = useCallback(() => {
    setViewMode("campus")
    setSelectedBuilding(null)
    setSelectedFloor(1)
    setSelectedRoom(null)
  }, [])

  const handleFloorChange = useCallback((floor: number) => {
    setSelectedFloor(floor)
    setSelectedRoom(null)
  }, [])

  const handleRoomClick = useCallback((roomId: string) => {
    setSelectedRoom(roomId)
  }, [])

  /* ── Navigate to a specific room (from search or schedule) ── */
  const navigateToRoom = useCallback(
    (letter: BuildingLetter, floor: number, roomId: string) => {
      setSelectedBuilding(letter)
      setSelectedFloor(floor)
      setSelectedRoom(roomId)
      setViewMode("floorplan")
    },
    [],
  )

  /* ── Mode switching ── */
  const handleModeToggle = useCallback((mode: MapViewMode) => {
    if (mode === "campus") {
      setViewMode("campus")
      // Keep selectedBuilding if coming from floorplan
    } else if (mode === "floorplan" && selectedBuilding) {
      setViewMode("floorplan")
    } else if (mode === "map") {
      setViewMode("map")
    }
  }, [selectedBuilding])

  /* ── Escape key → back ── */
  useEffect(() => {
    const onKeyDown = (e: globalThis.KeyboardEvent) => {
      if (e.key === "Escape") {
        if (viewMode === "floorplan") {
          setViewMode("campus")
          setSelectedBuilding(null)
          setSelectedFloor(1)
          setSelectedRoom(null)
        }
      }
    }
    window.addEventListener("keydown", onKeyDown)
    return () => window.removeEventListener("keydown", onKeyDown)
  }, [viewMode])

  /* ── Category filtering ── */
  const filteredBuildings = useMemo(() => {
    if (activeCategory === "all") return buildings
    return buildings.filter((b) => b.tags.includes(activeCategory))
  }, [buildings, activeCategory])

  /* ── Selected building/floor data ── */
  const currentBuilding: CampusBuilding | undefined = useMemo(
    () => buildings.find((b) => b.letter === selectedBuilding),
    [buildings, selectedBuilding],
  )

  const currentFloor = useMemo(
    () => currentBuilding?.floors.find((f) => f.floor === selectedFloor),
    [currentBuilding, selectedFloor],
  )

  /* ── Zoom controls bridging ── */
  const handleZoomIn = useCallback(() => {
    if (viewMode === "map" && mapLibreRef.current) {
      mapLibreRef.current.getMap().zoomIn()
    } else {
      zoomIn()
    }
  }, [viewMode, zoomIn])

  const handleZoomOut = useCallback(() => {
    if (viewMode === "map" && mapLibreRef.current) {
      mapLibreRef.current.getMap().zoomOut()
    } else {
      zoomOut()
    }
  }, [viewMode, zoomOut])

  const handleResetView = useCallback(() => {
    if (viewMode === "map" && mapLibreRef.current) {
      mapLibreRef.current.flyTo({ center: [CAMPUS_COORDINATES.lon, CAMPUS_COORDINATES.lat], zoom: 16, pitch: 45, bearing: 0, duration: 600 })
    } else {
      resetView()
    }
  }, [viewMode, resetView])

  return (
    <div className="map-theme aurora-mesh relative w-full text-text-primary py-6 sm:py-8 md:py-10 px-4 sm:px-6 md:px-10 lg:px-14 overflow-x-clip" data-time-period={timePeriod}>
      <MapBackdrop isNarrow={isNarrow} prefersReducedMotion={prefersReducedMotion} />

      <div className="relative z-[1]">
        <MapHeader />

        <FadeSection delay="100ms" className="flex flex-col sm:flex-row gap-3 mb-4">
          <div className="flex-1 min-w-0 sm:min-w-[240px] sm:max-w-md">
            <MapSearchBar
              buildings={buildings}
              onSelectBuilding={handleBuildingClick}
              onSelectRoom={navigateToRoom}
            />
          </div>
          <div className="flex-1 min-w-0 overflow-x-auto">
            <MapCategoryFilter
              active={activeCategory}
              onChange={setActiveCategory}
            />
          </div>
        </FadeSection>

        {/* Layer toggle — always visible now (3 modes) */}
        <FadeSection delay="160ms" className="mb-4 flex items-center gap-3">
          <MapLayerToggle
            viewMode={viewMode}
            onToggle={handleModeToggle}
            buildingName={currentBuilding?.name}
            showFloorplan={!!currentBuilding}
          />
        </FadeSection>

        {/* Map viewport + sidebar layout */}
        <FadeSection delay="180ms">
          <div className={`flex gap-4 ${!isNarrow && currentBuilding && viewMode !== "map" ? "flex-row" : "flex-col"}`}>
          <div
            className="map-card-matte flex-1 min-w-0 overflow-hidden relative"
            style={{ minHeight: isNarrow ? "400px" : "560px" }}
          >
            {/* Zoom controls — bottom right */}
            <div className="absolute bottom-4 right-4 z-10">
              <MapZoomControls
                onZoomIn={handleZoomIn}
                onZoomOut={handleZoomOut}
                onReset={handleResetView}
                canZoomIn={viewMode === "map" ? true : canZoomIn}
                canZoomOut={viewMode === "map" ? true : canZoomOut}
                isZoomed={viewMode === "map" ? true : isZoomed}
              />
            </div>

            <AnimatePresence mode="wait" initial={false}>
              {viewMode === "map" ? (
                <motion.div
                  key="maplibre-map"
                  initial={prefersReducedMotion ? false : { opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={prefersReducedMotion ? undefined : { opacity: 0 }}
                  transition={prefersReducedMotion ? { duration: 0 } : { duration: 0.2 }}
                  className="h-full min-h-[inherit]"
                >
                  <Suspense fallback={
                    <div className="h-full min-h-[inherit] flex items-center justify-center">
                      <div className="map-poi-chip animate-pulse">{t("poi.loading")}</div>
                    </div>
                  }>
                    <MapLibreMapComponent
                      selectedBuilding={selectedBuilding}
                      activeCategory={activeCategory}
                      highlightedBuilding={nextLessonInfo?.building ?? hoveredBuilding}
                      onSelectBuilding={handleBuildingClick}
                      mapRef={mapLibreRef}
                      isDark={isDark}
                    />
                  </Suspense>
                </motion.div>
              ) : viewMode === "campus" ? (
                <motion.div
                  key="campus"
                  initial={prefersReducedMotion ? false : { scale: 0.98, opacity: 0 }}
                  animate={{ scale: 1, opacity: 1 }}
                  exit={prefersReducedMotion ? undefined : { scale: 1.05, opacity: 0 }}
                  transition={prefersReducedMotion ? { duration: 0 } : { duration: 0.25, ease: "easeInOut" }}
                >
                  <div ref={mapContainerRef} style={transformStyle}>
                    <CampusMapSVG
                      buildings={filteredBuildings}
                      selectedBuilding={selectedBuilding}
                      highlightedBuilding={nextLessonInfo?.building ?? hoveredBuilding}
                      onBuildingClick={handleBuildingClick}
                      onBuildingHover={setHoveredBuilding}
                      prefersReducedMotion={prefersReducedMotion}
                    />
                  </div>
                </motion.div>
              ) : currentBuilding ? (
                <motion.div
                  key="floorplan"
                  initial={prefersReducedMotion ? false : { scale: 0.95, opacity: 0 }}
                  animate={{ scale: 1, opacity: 1 }}
                  exit={prefersReducedMotion ? undefined : { scale: 0.95, opacity: 0 }}
                  transition={prefersReducedMotion ? { duration: 0 } : { type: "spring", stiffness: 300, damping: 30 }}
                  className="flex flex-col h-full min-h-[inherit]"
                >
                  {/* Floor plan header */}
                  <div className="flex items-center justify-between gap-4 px-4 py-3 sm:px-6">
                    <button
                      type="button"
                      onClick={handleBackToCampus}
                      className="map-category-chip flex items-center gap-2"
                    >
                      <ArrowLeft className="h-4 w-4" />
                      <span className="hidden sm:inline">{t("floorPlan.backToCampus")}</span>
                    </button>

                    <div className="flex items-center gap-3">
                      <span
                        className="text-lg font-black"
                        style={{ color: currentBuilding.colorHex }}
                      >
                        {currentBuilding.letter}
                      </span>
                      <span className="text-sm font-semibold text-[var(--text-secondary)]">
                        {currentBuilding.name}
                      </span>
                    </div>

                    <FloorSelector
                      floors={currentBuilding.floors}
                      activeFloor={selectedFloor}
                      onFloorChange={handleFloorChange}
                      accentColor={currentBuilding.colorHex}
                    />
                  </div>

                  {/* Floor plan SVG */}
                  <div className="flex-1">
                    {currentFloor && (
                      <FloorPlanSVG
                        building={currentBuilding}
                        floor={currentFloor}
                        selectedRoom={selectedRoom}
                        scheduledRoom={nextLessonInfo?.roomId}
                        onRoomClick={handleRoomClick}
                      />
                    )}
                  </div>
                </motion.div>
              ) : null}
            </AnimatePresence>
          </div>

          {/* Sidebar — desktop: inline panel, mobile: bottom sheet */}
          {currentBuilding && viewMode !== "map" && (
            isNarrow ? (
              <MapSidebar
                building={currentBuilding}
                floor={currentFloor}
                selectedRoom={selectedRoom}
                onRoomClick={handleRoomClick}
                onClose={handleBackToCampus}
                isMobile
              />
            ) : (
              <MapSidebar
                building={currentBuilding}
                floor={currentFloor}
                selectedRoom={selectedRoom}
                onRoomClick={handleRoomClick}
                onClose={handleBackToCampus}
                isMobile={false}
              />
            )
          )}

          {/* Sidebar in map mode — show building info when selected */}
          {currentBuilding && viewMode === "map" && !isNarrow && (
            <MapSidebar
              building={currentBuilding}
              floor={currentFloor}
              selectedRoom={selectedRoom}
              onRoomClick={handleRoomClick}
              onClose={() => setSelectedBuilding(null)}
              isMobile={false}
            />
          )}
          </div>
        </FadeSection>
      </div>
    </div>
  )
}
