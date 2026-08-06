import { Calendar, Plus, Search, X, ArrowUpDown, Filter as FilterIcon } from "lucide-react"
import { useTranslation } from "react-i18next"
import { useRef, useEffect, useState } from "react"
import FadeSection from "@/components/motion/FadeSection"
import { Button } from "@/components/ui"
import { ALL_EVENT_CATEGORIES, type EventCategory } from "@/features/events/categories"
import { cn } from "@/utils/cn"
import useMediaQuery from "@/hooks/useMediaQuery"
import type { EventDateRange, EventSortMode, EventTabKey } from "../types"
import { useEventFilterPopover } from "@/components/events/EventFilterPopover"
import { useSlidingIndicator } from "@/hooks/ui/useSlidingIndicator"

const SORT_CYCLE: EventSortMode[] = ["newest", "popular", "upcoming"]

interface EventsHeaderProps {
  onAddClick: () => void
  isAdmin: boolean
  eventsCount?: number
  searchQuery: string
  onSearchChange: (q: string) => void
  activeCategory: EventCategory | "all"
  onCategoryChange: (c: EventCategory | "all") => void
  sortMode: EventSortMode
  onSortChange: (s: EventSortMode) => void
  tab: EventTabKey
  onTabChange: (t: string) => void
  dateRange: EventDateRange
  onDateRangeChange: (v: EventDateRange) => void
  locationFilter: string
  onLocationChange: (v: string) => void
}

export const EventsHeader = ({
  onAddClick,
  isAdmin,
  eventsCount,
  searchQuery,
  onSearchChange,
  activeCategory,
  onCategoryChange,
  sortMode,
  onSortChange,
  tab,
  onTabChange,
  dateRange,
  onDateRangeChange,
  locationFilter,
  onLocationChange,
}: EventsHeaderProps) => {
  const { t } = useTranslation(["events", "common"])
  const prefersReducedMotion = useMediaQuery("(prefers-reduced-motion: reduce)")

  /* ── Sticky detection via IntersectionObserver ── */
  const sentinelRef = useRef<HTMLDivElement>(null)
  const [isStuck, setIsStuck] = useState(false)

  /* ── Tab indicator (Wave 124 SW1 — replaces framer-motion layoutId) ── */
  const tabsRef = useRef<HTMLDivElement>(null)
  const tabRect = useSlidingIndicator(tabsRef, tab)

  useEffect(() => {
    const sentinel = sentinelRef.current!

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry) setIsStuck(!entry.isIntersecting)
      },
      { threshold: 0, rootMargin: "-64px 0px 0px 0px" }
    )
    observer.observe(sentinel)
    return () => observer.disconnect()
  }, [])

  /* ── Sort cycle ── */
  const handleSortCycle = () => {
    const idx = SORT_CYCLE.indexOf(sortMode)
    const next = SORT_CYCLE[(idx + 1) % SORT_CYCLE.length]!
    onSortChange(next)
  }

  /* ── Filter popover (date range + location) ── */
  const filter = useEventFilterPopover({
    dateRange,
    onDateRangeChange,
    location: locationFilter,
    onLocationChange,
  })

  /* ── Tab definitions ── */
  const tabs: { key: EventTabKey; labelKey: string }[] = [
    { key: "active", labelKey: "events:tabs.active" },
    { key: "archive", labelKey: "events:tabs.archive" },
    { key: "my", labelKey: "events:tabs.my" },
  ]

  return (
    <header className="mb-6 sm:mb-8 space-y-5">
      {/* Row 1: Icon + Title + Badge */}
      <FadeSection delay="60ms" className="flex items-center gap-3 flex-wrap">
        <div className="flex items-center gap-2 sm:gap-3 min-w-0">
          <div className="events-badge-matte hidden sm:flex h-11 w-11 items-center justify-center rounded-xl text-text-primary shrink-0">
            <Calendar size={20} strokeWidth={2.2} />
          </div>
          <h1 className="text-fluid-h1 font-extrabold tracking-tight text-text-primary whitespace-nowrap">
            {t("events:pageTitle")}
            {eventsCount != null && (
              <span
                className="events-badge-matte ml-2 inline-flex items-center justify-center rounded-full px-2 py-0.5 align-middle font-bold tabular-nums leading-none"
                style={{ fontSize: "0.45em" }}
              >
                {eventsCount}
              </span>
            )}
          </h1>
        </div>

        {/* Search */}
        <div className="relative ml-auto w-full sm:w-64 lg:w-72">
          <Search
            size={16}
            className="absolute left-3 top-1/2 -translate-y-1/2 text-(--text-secondary) pointer-events-none"
          />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => onSearchChange(e.target.value)}
            placeholder={t("events:filters.search")}
            className="w-full rounded-xl matte-input pl-9 pr-16 py-2 text-sm text-text-primary placeholder:text-(--text-secondary)/(--opacity-medium) focus:outline-none focus-visible:ring-2 focus-visible:ring-brand transition-shadow"
            aria-label={t("events:filters.search")}
          />
          <div className="absolute right-2 top-1/2 flex -translate-y-1/2 items-center gap-0.5">
            {searchQuery && (
              <button
                type="button"
                onClick={() => onSearchChange("")}
                className="rounded-full p-1.5 text-(--text-secondary) hover:text-text-primary transition-colors focus-visible:ring-2 focus-visible:ring-brand"
                aria-label={t("events:aria.clearSearch")}
              >
                <X size={14} />
              </button>
            )}
            <button
              type="button"
              {...filter.referenceProps}
              className={cn(
                "relative rounded-full p-1.5 transition-colors focus-visible:ring-2 focus-visible:ring-brand",
                filter.filtersActive
                  ? "text-brand"
                  : "text-(--text-secondary) hover:text-text-primary"
              )}
              aria-label={t("events:aria.openFilters")}
            >
              {filter.filtersActive && (
                <span
                  className="absolute right-0.5 top-0.5 h-2 w-2 rounded-full bg-brand"
                  aria-hidden="true"
                />
              )}
              <FilterIcon size={14} />
            </button>
          </div>
          {filter.popoverNode}
        </div>

        {isAdmin && (
          <Button
            id="events-header-add-btn"
            variant="glass"
            size="sm"
            onClick={onAddClick}
            leadingIcon={<Plus size={16} />}
            className="shrink-0"
          >
            {t("events:actions.openCreate")}
          </Button>
        )}
      </FadeSection>

      {/* Row 2: Tabs (Active / Archive / My)
          Wave 124 SW1 — Refactored from framer-motion layoutId to a single
          absolutely-positioned indicator + CSS transition (layoutId requires
          domMax). Same sliding UX, no framer-motion involvement. */}
      <FadeSection delay="100ms" role="tablist" aria-label={t("events:pageTitle")}>
        <div
          ref={tabsRef}
          className="relative inline-flex items-center gap-1 rounded-xl border border-glass-border bg-(--bg-surface)/(--opacity-medium) p-1 backdrop-blur-md shadow-glass sm:w-auto"
        >
          {tabRect && (
            <div
              aria-hidden="true"
              className="absolute bg-(--bg-surface) shadow-sm rounded-lg z-negative"
              style={{
                transform: `translate3d(${tabRect.left}px, ${tabRect.top}px, 0)`,
                width: tabRect.width,
                height: tabRect.height,
                transition: prefersReducedMotion
                  ? "none"
                  : "transform 250ms cubic-bezier(0.4, 0, 0.2, 1), width 250ms cubic-bezier(0.4, 0, 0.2, 1), height 250ms cubic-bezier(0.4, 0, 0.2, 1)",
              }}
            />
          )}
          {tabs.map((tabItem) => (
            <button
              key={tabItem.key}
              id={`events-tab-${tabItem.key}`}
              data-tab-key={tabItem.key}
              type="button"
              role="tab"
              aria-selected={tab === tabItem.key}
              // Wave 116 polish — single stable tabpanel ID instead of
              // per-tab suffix. Only the active tab's panel is rendered (the
              // other tabs act as a filter over the same EventsList section),
              // so per-tab aria-controls pointed to IDs that don't exist for
              // inactive tabs — Lighthouse aria-valid-attr-value fires at 0.
              // All three tabs now point to the same rendered panel which
              // always exists; aria-labelledby on the panel still resolves
              // to the active tab button, preserving the tablist contract.
              aria-controls="events-tabpanel"
              onClick={() => onTabChange(tabItem.key)}
              className={cn(
                "relative z-base px-4 py-2 text-body-sm font-semibold rounded-lg transition-colors duration-fast",
                "sm:px-6 sm:text-base",
                tab === tabItem.key
                  ? "text-text-primary"
                  : "text-(--text-secondary) hover:text-text-primary"
              )}
            >
              <span className="relative z-base">{t(tabItem.labelKey)}</span>
            </button>
          ))}
        </div>
      </FadeSection>

      {/* Sentinel for sticky detection */}
      <div ref={sentinelRef} className="h-0" aria-hidden="true" />

      {/* Row 3: Category pills + sort toggle -- sticky on scroll */}
      <div className="events-sticky-categories" data-stuck={isStuck}>
        <FadeSection
          delay="140ms"
          className="flex items-center gap-2 sm:flex-wrap max-sm:flex-nowrap max-sm:overflow-x-auto max-sm:scrollbar-none max-sm:pb-1 max-sm:-mx-4 max-sm:px-4"
          role="toolbar"
          aria-label={t("events:aria.categoryFilter")}
          onKeyDown={(e: React.KeyboardEvent) => {
            if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return
            const buttons = (e.currentTarget as HTMLElement).querySelectorAll<HTMLButtonElement>(
              "button"
            )
            const focused = document.activeElement as HTMLElement
            const idx = Array.from(buttons).indexOf(focused as HTMLButtonElement)
            if (idx === -1) return
            e.preventDefault()
            const next =
              e.key === "ArrowRight"
                ? buttons[(idx + 1) % buttons.length]
                : buttons[(idx - 1 + buttons.length) % buttons.length]
            next?.focus()
          }}
        >
          {/* "All" pill */}
          <button
            type="button"
            onClick={() => onCategoryChange("all")}
            aria-current={activeCategory === "all" ? "page" : undefined}
            className={cn(
              "rounded-full px-3 py-2 text-xs font-semibold tracking-wide transition-all duration-fast whitespace-nowrap min-h-[44px] flex items-center focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-1",
              activeCategory === "all"
                ? "bg-brand text-[var(--text-inverse)] shadow-sm"
                : "matte-chip text-(--text-secondary)"
            )}
          >
            {t("events:categories.all")}
          </button>

          {/* Category pills */}
          {ALL_EVENT_CATEGORIES.map((cat) => (
            <button
              key={cat.id}
              type="button"
              onClick={() => onCategoryChange(cat.id)}
              aria-current={activeCategory === cat.id ? "page" : undefined}
              className={cn(
                "rounded-full px-3 py-2 text-xs font-semibold tracking-wide transition-all duration-fast whitespace-nowrap min-h-[44px] flex items-center focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-1",
                activeCategory === cat.id ? "shadow-sm" : "matte-chip text-(--text-secondary)"
              )}
              style={
                activeCategory === cat.id
                  ? {
                      backgroundColor: `var(--cat-${cat.color}-bg)`,
                      color: `var(--cat-${cat.color}-text)`,
                    }
                  : undefined
              }
            >
              {t(cat.labelKey)}
            </button>
          ))}

          {/* Sort toggle */}
          <button
            type="button"
            onClick={handleSortCycle}
            className="ml-auto flex items-center gap-1.5 rounded-full matte-chip px-3 py-2 text-xs font-semibold text-(--text-secondary) shrink-0 min-h-[44px] focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-1"
            aria-label={`${t("events:sort.label")}: ${
              sortMode === "newest"
                ? t("events:sort.newest")
                : sortMode === "popular"
                  ? t("events:sort.popular")
                  : t("events:sort.upcoming")
            }`}
          >
            <ArrowUpDown size={13} />
            <span>
              {sortMode === "newest"
                ? t("events:sort.newest")
                : sortMode === "popular"
                  ? t("events:sort.popular")
                  : t("events:sort.upcoming")}
            </span>
          </button>
        </FadeSection>
      </div>
    </header>
  )
}
