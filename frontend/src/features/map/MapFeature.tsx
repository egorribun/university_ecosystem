import { useState, useCallback, useEffect, useMemo, useRef, useSyncExternalStore, lazy, Suspense } from "react"
import { useTranslation } from "react-i18next"
import { useReducedMotion } from "framer-motion"
import useMediaQuery from "@/hooks/useMediaQuery"
import { breakpoints } from "@/theme/tokens"
import { MapBackdrop } from "@/components/map/MapBackdrop"
import { MapHeader } from "@/components/map/MapHeader"
import { MapSidebar } from "@/components/map/MapSidebar"
import { MapSearchBar } from "@/components/map/MapSearchBar"
import { MapCategoryFilter } from "@/components/map/MapCategoryFilter"
import { useNextLesson } from "@/hooks/useNextLesson"
import { useScheduleData } from "@/hooks/useScheduleData"
import { useMapWeather } from "@/hooks/useMapWeather"
import { useTimeOfDay } from "@/hooks/useTimeOfDay"
import { useSeason } from "@/hooks/useSeason"
import { useMapEvents } from "@/hooks/useMapEvents"
import { useMapKeyboardShortcuts } from "@/hooks/useMapKeyboardShortcuts"
import { MapShortcutsOverlay } from "@/components/map/MapShortcutsOverlay"
import { MapWeatherBadge } from "@/components/map/MapWeatherBadge"
import {
  getCampusBuildings,
  type BuildingId,
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
  const { t, i18n } = useTranslation("map")
  const isNarrow = useMediaQuery(`(max-width: ${breakpoints.content})`)
  const isDark = useSyncExternalStore(subscribeToDarkMode, getIsDark, () => SERVER_SNAPSHOT)
  const prefersReducedMotion = useReducedMotion() ?? false
  const timePeriod = useTimeOfDay()
  const season = useSeason()

  /* ── Campus data ── */
  const buildings = useMemo(
    () => getCampusBuildings(i18n.resolvedLanguage ?? i18n.language),
    [i18n.resolvedLanguage, i18n.language],
  )

  /* ── View state ── */
  const [selectedBuilding, setSelectedBuilding] = useState<BuildingId | null>(null)
  const [selectedFloor, setSelectedFloor] = useState<number>(1)
  const [selectedRoom, setSelectedRoom] = useState<string | null>(null)
  const [activeCategory, setActiveCategory] = useState<MapCategory>("all")
  const [showEvents, setShowEvents] = useState(true)
  const [showShortcuts, setShowShortcuts] = useState(false)
  const searchInputRef = useRef<HTMLInputElement>(null)

  /* ── Schedule integration ── */
  const nextLessonInfo = useNextLesson()
  const { todayLessons } = useScheduleData()

  /* ── Events on map ── */
  const { events: mapEvents } = useMapEvents()

  /* ── Weather ── */
  const { data: weatherData } = useMapWeather()

  /* ── MapLibre GL map ref ── */
  const mapLibreRef = useRef<MapRef | null>(null)

  /* ── Building selection ── */
  const handleBuildingClick = useCallback((letter: BuildingId) => {
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
    (letter: BuildingId, floor: number, roomId: string) => {
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

  /* ── Keyboard shortcuts ── */
  const handleToggleFullscreen = useCallback(() => {
    const container = document.querySelector(".map-card-matte")
    if (!container) return
    if (!document.fullscreenElement) {
      container.requestFullscreen().catch(() => {})
    } else {
      document.exitFullscreen().catch(() => {})
    }
  }, [])

  useMapKeyboardShortcuts({
    onSelectBuilding: handleBuildingClick,
    onToggleFullscreen: handleToggleFullscreen,
    onFocusSearch: () => searchInputRef.current?.focus(),
    onToggleShortcuts: () => setShowShortcuts((prev) => !prev),
  })

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
    <div className="map-theme aurora-mesh relative w-full text-text-primary py-6 sm:py-8 md:py-10 px-4 sm:px-6 md:px-10 lg:px-14 overflow-x-clip" data-weather={weatherData?.condition} data-time-period={timePeriod} data-season={season}>
      <MapBackdrop isNarrow={isNarrow} prefersReducedMotion={prefersReducedMotion} />

      <div className="relative z-[1]">
        <MapHeader />
        <MapWeatherBadge />

        <FadeSection delay="100ms" className="flex flex-col sm:flex-row gap-3 mb-4">
          <div className="flex-1 min-w-0 sm:min-w-[240px] sm:max-w-md">
            <MapSearchBar
              buildings={buildings}
              onSelectBuilding={handleBuildingClick}
              onSelectRoom={navigateToRoom}
              searchInputRef={searchInputRef}
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
                  <div className="map-poi-chip animate-pulse">{t("campusMap.loading")}</div>
                </div>
              }>
                <MapLibreMapComponent
                  selectedBuilding={selectedBuilding}
                  activeCategory={activeCategory}
                  highlightedBuilding={nextLessonInfo?.building ?? null}
                  onSelectBuilding={handleBuildingClick}
                  mapRef={mapLibreRef}
                  isDark={isDark}
                  timePeriod={timePeriod}
                  weatherCondition={weatherData?.condition}
                  showEvents={showEvents}
                  mapEvents={mapEvents}
                  onToggleEvents={() => setShowEvents((prev) => !prev)}
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
                todayLessons={todayLessons}
              />
            )}
          </div>
        </FadeSection>
      </div>

      {/* Keyboard shortcuts overlay */}
      <MapShortcutsOverlay
        open={showShortcuts}
        onClose={() => setShowShortcuts(false)}
      />
    </div>
  )
}
