/**
 * POIControls.tsx — POI category filter + "Load more" button.
 *
 * Overlays the MapLibre GL map at bottom-left.
 * "Load more" triggers Overpass API fetch via useOverpassPOI.
 *
 * Wave 99 — campus map integration; Wave 107 — stale comment fix.
 */

import { useTranslation } from "react-i18next"
import { MapPin, Loader2, CalendarDays } from "lucide-react"

interface POIControlsProps {
  activeCategory: string
  onCategoryChange: (category: string) => void
  onLoadMore: () => void
  isLoading: boolean
  hasLoadedMore: boolean
  showEvents: boolean
  onToggleEvents: () => void
}

const POI_CATEGORIES = ["all", "transport", "food", "shop", "service", "campus"] as const

export function POIControls({
  activeCategory,
  onCategoryChange,
  onLoadMore,
  isLoading,
  hasLoadedMore,
  showEvents,
  onToggleEvents,
}: POIControlsProps) {
  const { t } = useTranslation("map")

  return (
    <div className="map-poi-controls flex flex-col gap-2">
      {/* Category filter */}
      <div
        role="radiogroup"
        aria-label={t("poi.filterLabel")}
        className="flex flex-wrap gap-1"
      >
        {POI_CATEGORIES.map((cat) => (
          <button
            key={cat}
            type="button"
            role="radio"
            aria-checked={activeCategory === cat}
            onClick={() => onCategoryChange(cat)}
            className="map-poi-chip"
            data-active={activeCategory === cat || undefined}
          >
            {t(`poi.categories.${cat}`)}
          </button>
        ))}
      </div>

      {/* Load more button */}
      {!hasLoadedMore && (
        <button
          type="button"
          onClick={onLoadMore}
          disabled={isLoading}
          aria-busy={isLoading}
          className="map-poi-load-more"
        >
          {isLoading ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <MapPin className="h-3.5 w-3.5" />
          )}
          <span>{isLoading ? t("poi.loading") : t("poi.loadMore")}</span>
        </button>
      )}

      {/* Events toggle — compact matte chip (FIX-109-02, FIX-109-06) */}
      <button
        type="button"
        onClick={onToggleEvents}
        className="map-events-toggle"
        data-active={showEvents || undefined}
        aria-pressed={showEvents}
      >
        <CalendarDays className="h-3 w-3" />
        <span>{showEvents ? t("events.hideOnMap") : t("events.showOnMap")}</span>
      </button>
    </div>
  )
}
