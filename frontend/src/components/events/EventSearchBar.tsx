import { useTranslation } from "react-i18next"
import { Search as SearchIcon, Filter as FilterListIcon, X as ClearIcon } from "lucide-react"
import { cn } from "@/utils/cn"
import { useEventFilterPopover } from "./EventFilterPopover"
import type { EventDateRange } from "@/features/events/types"

type EventSearchBarProps = {
  search: string
  onSearchChange: (value: string) => void
  dateRange: EventDateRange
  onDateRangeChange: (value: EventDateRange) => void
  location: string
  onLocationChange: (value: string) => void
}

export function EventSearchBar({
  search,
  onSearchChange,
  dateRange,
  onDateRangeChange,
  location,
  onLocationChange,
}: EventSearchBarProps) {
  const { t } = useTranslation(["events"])

  const filter = useEventFilterPopover({
    dateRange,
    onDateRangeChange,
    location,
    onLocationChange,
  })

  return (
    <div className="relative">
      <SearchIcon className="absolute left-4 top-1/2 h-5 w-5 -translate-y-1/2 text-(--text-secondary) pointer-events-none opacity-strong" />
      <input
        id="events-search-input"
        type="text"
        value={search}
        onChange={(event) => onSearchChange(event.target.value)}
        placeholder={t("events:filters.search")}
        className={cn(
          "w-full rounded-md px-4 py-3.5 pl-11 pr-20 text-base text-text-primary",
          "bg-(--bg-surface)/(--opacity-medium) border border-glass-border shadow-glass backdrop-blur-md",
          "placeholder:text-(--text-secondary)/(--opacity-medium)",
          "outline-none transition-all duration-fast",
          "focus:border-brand/(--opacity-medium) focus:ring-4 focus:ring-brand/(--opacity-subtle)"
        )}
      />
      <div className="absolute right-2 top-1/2 flex -translate-y-1/2 items-center gap-1">
        {search && (
          <button
            type="button"
            onClick={() => onSearchChange("")}
            className="rounded-full p-2 text-(--text-secondary) transition-all duration-rapid hover:bg-(--bg-surface)/(--opacity-dim) active:scale-95"
            aria-label={t("events:aria.clearSearch")}
          >
            <ClearIcon className="h-4 w-4" />
          </button>
        )}
        <button
          type="button"
          {...filter.referenceProps}
          className={cn(
            "relative rounded-full p-2 transition-all duration-rapid hover:bg-(--bg-surface)/(--opacity-dim) active:scale-95",
            filter.filtersActive ? "text-brand" : "text-(--text-secondary)"
          )}
          aria-label={t("events:aria.openFilters")}
        >
          {filter.filtersActive && (
            <span
              className="absolute right-1.5 top-1.5 h-2 w-2 rounded-full bg-brand shadow-glow-green"
              aria-hidden="true"
            />
          )}
          <FilterListIcon className="h-5 w-5" />
        </button>
      </div>
      {filter.popoverNode}
    </div>
  )
}
