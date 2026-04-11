import { useTranslation } from "react-i18next"
import type { BuildingFloor } from "@/data/campusBuildings"

interface FloorSelectorProps {
  floors: BuildingFloor[]
  activeFloor: number
  onFloorChange: (floor: number) => void
  accentColor: string
}

/**
 * Floor tab row — role="tablist" with aria-selected.
 * Mirrors WeekSelector pattern from schedule page.
 */
export function FloorSelector({
  floors,
  activeFloor,
  onFloorChange,
  accentColor,
}: FloorSelectorProps) {
  const { t } = useTranslation("map")

  return (
    <div
      role="tablist"
      aria-label={t("floorPlan.selectFloor")}
      className="map-layer-toggle inline-flex items-center gap-0.5"
    >
      {floors.map((f) => {
        const isActive = f.floor === activeFloor
        return (
          <button
            key={f.floor}
            type="button"
            role="tab"
            aria-selected={isActive}
            tabIndex={isActive ? 0 : -1}
            onClick={() => onFloorChange(f.floor)}
            className="relative px-4 py-2 text-sm font-bold rounded-full transition-colors"
            style={{
              backgroundColor: isActive ? accentColor : undefined,
              color: isActive ? "white" : "var(--text-secondary)",
              opacity: isActive ? 1 : 0.7,
            }}
          >
            {t("floorPlan.floorLabel", { number: f.floor })}
          </button>
        )
      })}
    </div>
  )
}
