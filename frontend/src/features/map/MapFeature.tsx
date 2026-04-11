import { useState, useCallback, useEffect, useMemo } from "react"
import { useReducedMotion } from "framer-motion"
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
import { MapScheduleWidget } from "@/components/map/MapScheduleWidget"
import { MapLayerToggle } from "@/components/map/MapLayerToggle"
import { MapZoomControls } from "@/components/map/MapZoomControls"
import { useNextLesson } from "@/hooks/useNextLesson"
import { useMapNavigation } from "@/hooks/useMapNavigation"
import { ArrowLeft } from "lucide-react"
import {
  getCampusBuildings,
  type BuildingLetter,
  type MapCategory,
  type CampusBuilding,
} from "@/data/campusBuildings"
import FadeSection from "@/components/motion/FadeSection"

export type MapViewMode = "campus" | "floorplan"

/**
 * MapFeature — central orchestrator for the campus map page.
 * Mirrors EventsFeature pattern: .map-theme, backdrop, z-stacking.
 */
export function MapFeature() {
  const { t, i18n } = useTranslation("map")
  const prefersReducedMotion = useReducedMotion() ?? false
  const isNarrow = useMediaQuery(`(max-width: ${breakpoints.content})`)

  /* ── Campus data ── */
  const buildings = useMemo(
    () => getCampusBuildings(i18n.resolvedLanguage ?? i18n.language),
    [i18n.resolvedLanguage, i18n.language],
  )

  /* ── View state ── */
  const [viewMode, setViewMode] = useState<MapViewMode>("campus")
  const [selectedBuilding, setSelectedBuilding] = useState<BuildingLetter | null>(null)
  const [selectedFloor, setSelectedFloor] = useState<number>(1)
  const [selectedRoom, setSelectedRoom] = useState<string | null>(null)
  const [activeCategory, setActiveCategory] = useState<MapCategory>("all")
  const [hoveredBuilding, setHoveredBuilding] = useState<BuildingLetter | null>(null)

  /* ── Schedule integration ── */
  const nextLessonInfo = useNextLesson()

  /* ── Zoom/Pan ── */
  const {
    containerRef: mapContainerRef,
    zoomIn, zoomOut, resetView,
    transformStyle,
    canZoomIn, canZoomOut, isZoomed,
  } = useMapNavigation()

  /* ── Building selection ── */
  const handleBuildingClick = useCallback((letter: BuildingLetter) => {
    setSelectedBuilding(letter)
    setSelectedFloor(1)
    setSelectedRoom(null)
    setViewMode("floorplan")
  }, [])

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

  /* ── Escape key → back to campus ── */
  useEffect(() => {
    if (viewMode !== "floorplan") return
    const onKeyDown = (e: globalThis.KeyboardEvent) => {
      if (e.key === "Escape") handleBackToCampus()
    }
    window.addEventListener("keydown", onKeyDown)
    return () => window.removeEventListener("keydown", onKeyDown)
  }, [viewMode, handleBackToCampus])

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

  return (
    <div className="map-theme aurora-mesh relative w-full text-text-primary py-6 sm:py-8 md:py-10 px-4 sm:px-6 md:px-10 lg:px-14 overflow-x-clip">
      <MapBackdrop isNarrow={isNarrow} prefersReducedMotion={prefersReducedMotion} />

      <div className="relative z-[1]">
        <MapHeader buildingCount={buildings.length} />

        {/* Schedule widget + Search + category filters */}
        <FadeSection delay="100ms" className="mb-4">
          <MapScheduleWidget
            nextLesson={nextLessonInfo}
            onNavigate={navigateToRoom}
          />
        </FadeSection>

        <FadeSection delay="140ms" className="flex flex-col sm:flex-row gap-3 mb-4">
          <div className="flex-1 max-w-md">
            <MapSearchBar
              buildings={buildings}
              onSelectBuilding={handleBuildingClick}
              onSelectRoom={navigateToRoom}
            />
          </div>
          <MapCategoryFilter
            active={activeCategory}
            onChange={setActiveCategory}
          />
        </FadeSection>

        {/* Layer toggle */}
        {currentBuilding && (
          <FadeSection delay="160ms" className="mb-4 flex items-center gap-3">
            <MapLayerToggle
              viewMode={viewMode}
              onToggle={(mode) => {
                if (mode === "campus") handleBackToCampus()
                else if (selectedBuilding) setViewMode("floorplan")
              }}
              buildingName={currentBuilding.name}
            />
          </FadeSection>
        )}

        {/* Map viewport + sidebar layout */}
        <FadeSection delay="180ms">
          <div className={`flex gap-4 ${!isNarrow && currentBuilding ? "flex-row" : "flex-col"}`}>
          <div
            className="map-card-matte flex-1 min-w-0 overflow-hidden relative"
            style={{ minHeight: isNarrow ? "400px" : "560px" }}
          >
            {/* Zoom controls — bottom right */}
            {viewMode === "campus" && (
              <div className="absolute bottom-4 right-4 z-10">
                <MapZoomControls
                  onZoomIn={zoomIn}
                  onZoomOut={zoomOut}
                  onReset={resetView}
                  canZoomIn={canZoomIn}
                  canZoomOut={canZoomOut}
                  isZoomed={isZoomed}
                />
              </div>
            )}

            {viewMode === "campus" ? (
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
            ) : currentBuilding ? (
              <div className="flex flex-col h-full min-h-[inherit]">
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
              </div>
            ) : null}
          </div>

          {/* Sidebar — desktop: inline panel, mobile: bottom sheet */}
          {currentBuilding && (
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
          </div>
        </FadeSection>
      </div>
    </div>
  )
}
