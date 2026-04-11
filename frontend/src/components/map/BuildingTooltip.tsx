import { useTranslation } from "react-i18next"
import type { CampusBuilding } from "@/data/campusBuildings"

interface BuildingTooltipProps {
  building: CampusBuilding
  position: { x: number; y: number }
}

/**
 * Hover tooltip for isometric buildings — shows name + floor count.
 * Positioned near cursor via absolute positioning on the map container.
 */
export function BuildingTooltip({ building, position }: BuildingTooltipProps) {
  const { t } = useTranslation("map")

  return (
    <div
      className="absolute pointer-events-none z-20"
      style={{
        left: `${position.x}px`,
        top: `${position.y - 60}px`,
        transform: "translateX(-50%)",
      }}
    >
      <div
        className="px-3 py-2 rounded-lg text-xs whitespace-nowrap"
        style={{
          backgroundColor: "var(--map-tooltip-bg)",
          boxShadow: "var(--map-tooltip-shadow)",
        }}
      >
        <p className="font-bold text-text-primary">{building.name}</p>
        <p className="text-[var(--text-tertiary)] mt-0.5">
          {t("tooltip.floors", { count: building.floorCount })} · {t("tooltip.clickToExplore")}
        </p>
      </div>
    </div>
  )
}
