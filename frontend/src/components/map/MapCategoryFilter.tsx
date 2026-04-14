import { useTranslation } from "react-i18next"
import { MAP_CATEGORIES, type MapCategory } from "@/data/campusBuildings"

interface MapCategoryFilterProps {
  active: MapCategory | "all"
  onChange: (cat: MapCategory | "all") => void
}

/**
 * Category chip row — role="radiogroup" + aria-checked.
 * Matches events page category filter pattern.
 */
export function MapCategoryFilter({ active, onChange }: MapCategoryFilterProps) {
  const { t } = useTranslation("map")

  const allCategories: Array<MapCategory | "all"> = ["all", ...MAP_CATEGORIES]

  return (
    <div
      role="radiogroup"
      aria-label={t("categories.all")}
      className="flex flex-wrap gap-2"
    >
      {allCategories.map((cat) => {
        const isActive = active === cat
        return (
          <button
            key={cat}
            type="button"
            role="radio"
            aria-checked={isActive}
            onClick={() => onChange(cat)}
            className="map-category-chip text-xs"
            data-active={isActive || undefined}
          >
            {t(`categories.${cat}`)}
          </button>
        )
      })}
    </div>
  )
}
