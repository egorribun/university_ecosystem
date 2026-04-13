import { useState, useCallback, useEffect, useMemo, useRef, useSyncExternalStore, lazy, Suspense } from "react"
import { useTranslation } from "react-i18next"
import useMediaQuery from "@/hooks/useMediaQuery"
import { breakpoints } from "@/theme/tokens"
import { MapBackdrop } from "@/components/map/MapBackdrop"
import { MapHeader } from "@/components/map/MapHeader"
import { MapSidebar } from "@/components/map/MapSidebar"
import { MapSearchBar } from "@/components/map/MapSearchBar"
import { MapCategoryFilter } from "@/components/map/MapCategoryFilter"
import { useNextLesson } from "@/hooks/useNextLesson"
import { useMapWeather } from "@/hooks/useMapWeather"
import { MapWeatherBadge } from "@/components/map/MapWeatherBadge"
import {
  getCampusBuildings,
  type BuildingLetter,
  type MapCategory,
  type CampusBuilding,
} from "@/data/campusBuildings"
import FadeSection from "@/components/motion/FadeSection"
import type { MapRef } from "react-map-gl/maplibre"

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

/** Lazy-load MapLibre GL — CSS + JS only loaded when map page is activated */
const MapLibreMapComponent = lazy(() => import("@/components/map/MapLibreMap"))

/**
 * MapFeature — central orchestrator for the campus map page.
 * Single view mode: MapLibre GL 3D map.
 * Wave 101: removed isometric SVG + floor plan modes.
 */
export function MapFeature() {
  const { i18n } = useTranslation("map")
  const isNarrow = useMediaQuery(`(max-width: ${breakpoints.content})`)
  const isDark = useSyncExternalStore(subscribeToDarkMode, getIsDark, () => SERVER_SNAPSHOT)

  /* ── Campus data ── */
  const buildings = useMemo(
    () => getCampusBuildings(i18n.resolvedLanguage ?? i18n.language),
    [i18n.resolvedLanguage, i18n.language],
  )

  /* ── View state ── */
  const [selectedBuilding, setSelectedBuilding] = useState<BuildingLetter | null>(null)
  const [selectedFloor, setSelectedFloor] = useState<number>(1)
  const [selectedRoom, setSelectedRoom] = useState<string | null>(null)
  const [activeCategory, setActiveCategory] = useState<MapCategory>("all")
  const [hoveredBuilding] = useState<BuildingLetter | null>(null)

  /* ── Schedule integration ── */
  const nextLessonInfo = useNextLesson()

  /* ── Weather ── */
  const { data: weatherData } = useMapWeather()

  /* ── MapLibre GL map ref ── */
  const mapLibreRef = useRef<MapRef | null>(null)

  /* ── Building selection ── */
  const handleBuildingClick = useCallback((letter: BuildingLetter) => {
    setSelectedBuilding(letter)
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

  const handleCloseSidebar = useCallback(() => {
    setSelectedBuilding(null)
    setSelectedFloor(1)
    setSelectedRoom(null)
  }, [])

  /* ── Navigate to a specific room (from search or schedule) ── */
  const navigateToRoom = useCallback(
    (letter: BuildingLetter, floor: number, roomId: string) => {
      setSelectedBuilding(letter)
      setSelectedFloor(floor)
      setSelectedRoom(roomId)
    },
    [],
  )

  /* ── Escape key → close sidebar ── */
  useEffect(() => {
    const onKeyDown = (e: globalThis.KeyboardEvent) => {
      if (e.key === "Escape" && selectedBuilding) {
        handleCloseSidebar()
      }
    }
    window.addEventListener("keydown", onKeyDown)
    return () => window.removeEventListener("keydown", onKeyDown)
  }, [selectedBuilding, handleCloseSidebar])

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
    <div className="map-theme aurora-mesh relative w-full text-text-primary py-6 sm:py-8 md:py-10 px-4 sm:px-6 md:px-10 lg:px-14 overflow-x-clip" data-weather={weatherData?.condition}>
      <MapBackdrop isNarrow={isNarrow} prefersReducedMotion={false} />

      <div className="relative z-[1]">
        <MapHeader />
        <MapWeatherBadge />

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

        {/* Map viewport + sidebar layout */}
        <FadeSection delay="140ms">
          <div className={`flex gap-4 ${!isNarrow && currentBuilding ? "flex-row" : "flex-col"}`}>
            <div
              className="map-card-matte flex-1 min-w-0 overflow-hidden relative"
              style={{ minHeight: isNarrow ? "400px" : "560px" }}
            >
              <Suspense fallback={
                <div className="h-full min-h-[inherit] flex items-center justify-center">
                  <div className="map-poi-chip animate-pulse">Loading map...</div>
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
            </div>

            {/* Sidebar — desktop: inline panel, mobile: bottom sheet */}
            {currentBuilding && (
              <MapSidebar
                building={currentBuilding}
                floor={currentFloor}
                selectedFloor={selectedFloor}
                selectedRoom={selectedRoom}
                onFloorChange={handleFloorChange}
                onRoomClick={handleRoomClick}
                onClose={handleCloseSidebar}
                isMobile={isNarrow}
              />
            )}
          </div>
        </FadeSection>
      </div>
    </div>
  )
}
