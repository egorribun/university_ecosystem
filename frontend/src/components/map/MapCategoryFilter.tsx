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
  const handleKeyDown = (event: React.KeyboardEvent<HTMLButtonElement>) => {
    const forward = event.key === "ArrowRight" || event.key === "ArrowDown"
    const backward = event.key === "ArrowLeft" || event.key === "ArrowUp"
    const group = event.currentTarget.closest('[role="radiogroup"]')
    if (!group) return

    const radios = Array.from(group.querySelectorAll<HTMLButtonElement>('[role="radio"]'))
    const focusedIndex = radios.indexOf(event.currentTarget)

    if (focusedIndex < 0 || radios.length === 0) return

    let nextIndex: number
    if (event.key === "Home") {
      nextIndex = 0
    } else if (event.key === "End") {
      nextIndex = radios.length - 1
    } else if (forward) {
      nextIndex = (focusedIndex + 1) % radios.length
    } else if (backward) {
      nextIndex = (focusedIndex - 1 + radios.length) % radios.length
    } else {
      return
    }

    event.preventDefault()
    radios[nextIndex]?.focus()
    const nextCategory = allCategories[nextIndex]
    if (nextCategory !== undefined) onChange(nextCategory)
  }

  return (
    <div
      role="radiogroup"
      aria-label={t("categories.filterLabel")}
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
            tabIndex={isActive ? 0 : -1}
            onKeyDown={handleKeyDown}
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
