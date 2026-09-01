import { Newspaper, Plus, Search, X, ArrowUpDown, Bookmark as BookmarkIcon } from "lucide-react"
import { useTranslation } from "react-i18next"
import { useRef, useEffect, useState } from "react"
import FadeSection from "@/components/motion/FadeSection"
import { Button } from "@/components/ui"
import { ALL_CATEGORIES, type NewsCategory } from "@/features/news/categories"
import { cn } from "@/utils/cn"
import type { SortMode } from "@/features/news/NewsFeature"

interface NewsHeaderProps {
  onAddClick: () => void
  isAdmin: boolean
  newsCount?: number
  searchQuery: string
  onSearchChange: (q: string) => void
  activeCategory: NewsCategory | "all" | "saved"
  onCategoryChange: (c: NewsCategory | "all" | "saved") => void
  sortMode: SortMode
  onSortChange: (s: SortMode) => void
  bookmarkCount?: number
}

export const NewsHeader = ({
  onAddClick,
  isAdmin,
  newsCount,
  searchQuery,
  onSearchChange,
  activeCategory,
  onCategoryChange,
  sortMode,
  onSortChange,
  bookmarkCount = 0,
}: NewsHeaderProps) => {
  const { t } = useTranslation(["news", "common"])
  /* ── Sticky detection via IntersectionObserver ── */
  const sentinelRef = useRef<HTMLDivElement>(null)
  const stickyRef = useRef<HTMLDivElement>(null)
  const [isStuck, setIsStuck] = useState(false)

  useEffect(() => {
    const sentinel = sentinelRef.current!

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry) setIsStuck(!entry.isIntersecting)
      },
      { threshold: 0 }
    )
    observer.observe(sentinel)
    return () => observer.disconnect()
  }, [])

  return (
    <header className="mb-6 sm:mb-8 space-y-4">
      {/* Row 1: Title + search + admin button */}
      <FadeSection delay="60ms" className="flex items-center gap-3 flex-wrap">
        <div className="flex items-center gap-2 sm:gap-3 min-w-0">
          <div className="news-badge-matte hidden sm:flex h-11 w-11 items-center justify-center rounded-xl text-text-primary shrink-0">
            <Newspaper size={20} strokeWidth={2.2} />
          </div>
          <h1 className="text-fluid-h1 font-extrabold tracking-tight text-text-primary whitespace-nowrap">
            {t("news:pageTitle")}
            {newsCount != null && (
              <span
                className="news-badge-matte ml-2 inline-flex items-center justify-center rounded-full px-2 py-0.5 align-middle font-bold tabular-nums leading-none"
                style={{ fontSize: "0.45em" }}
              >
                {newsCount}
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
            placeholder={t("news:search.placeholder")}
            className="w-full rounded-xl matte-input py-2 pl-9 pr-14 text-sm text-text-primary placeholder:text-(--text-secondary)/(--opacity-medium) focus:outline-none transition-shadow"
            aria-label={t("news:search.placeholder")}
          />
          {searchQuery && (
            <button
              type="button"
              onClick={() => onSearchChange("")}
              className="absolute right-1 top-1/2 flex size-11 -translate-y-1/2 items-center justify-center rounded-full text-(--text-secondary) hover:text-text-primary transition-colors focus-visible:ring-2 focus-visible:ring-brand"
              aria-label={t("common:buttons.clear")}
            >
              <X size={14} />
            </button>
          )}
        </div>

        {isAdmin && (
          <Button
            id="news-header-add-btn"
            variant="glass"
            size="sm"
            onClick={onAddClick}
            leadingIcon={<Plus size={16} />}
            className="shrink-0"
          >
            {t("news:actions.add")}
          </Button>
        )}
      </FadeSection>

      {/* Sentinel for sticky detection */}
      <div ref={sentinelRef} className="h-0" aria-hidden="true" />

      {/* Row 2: Category pills + sort toggle — sticky on scroll */}
      <div ref={stickyRef} className="news-sticky-categories" data-stuck={isStuck}>
        <FadeSection
          delay="100ms"
          className="flex items-center gap-2 sm:flex-wrap max-sm:flex-nowrap max-sm:overflow-x-auto max-sm:scrollbar-none max-sm:pb-1 max-sm:-mx-4 max-sm:px-4"
          role="toolbar"
          aria-label={t("news:aria.categoryFilter")}
          onKeyDown={(event: React.KeyboardEvent) => {
            if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return
            const buttons = Array.from(
              event.currentTarget.querySelectorAll<HTMLButtonElement>("button")
            )
            const focusedIndex = buttons.indexOf(document.activeElement as HTMLButtonElement)
            // A non-negative index already proves that the rendered toolbar
            // contains at least one button.
            if (focusedIndex < 0) return
            event.preventDefault()
            const nextIndex =
              event.key === "ArrowRight"
                ? (focusedIndex + 1) % buttons.length
                : (focusedIndex - 1 + buttons.length) % buttons.length
            buttons[nextIndex]?.focus()
          }}
        >
          {/* "All" pill */}
          <button
            type="button"
            onClick={() => onCategoryChange("all")}
            aria-current={activeCategory === "all" ? "page" : undefined}
            className={cn(
              "rounded-full px-3 py-2 min-h-[44px] text-xs font-semibold tracking-wide transition-all duration-fast whitespace-nowrap",
              activeCategory === "all"
                ? "bg-brand text-[var(--text-inverse)] shadow-sm"
                : "matte-chip text-(--text-secondary)"
            )}
          >
            {t("news:categories.all")}
          </button>

          {/* Category pills */}
          {ALL_CATEGORIES.map((cat) => (
            <button
              key={cat.id}
              type="button"
              onClick={() => onCategoryChange(cat.id)}
              aria-current={activeCategory === cat.id ? "page" : undefined}
              className={cn(
                "rounded-full px-3 py-2 min-h-[44px] text-xs font-semibold tracking-wide transition-all duration-fast whitespace-nowrap",
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

          {/* Saved/bookmark filter — only shown when bookmarks exist */}
          {bookmarkCount > 0 && (
            <button
              type="button"
              onClick={() => onCategoryChange("saved")}
              aria-current={activeCategory === "saved" ? "page" : undefined}
              className={cn(
                "rounded-full px-3 py-2 min-h-[44px] text-xs font-semibold tracking-wide transition-all duration-fast flex items-center gap-1.5 whitespace-nowrap",
                activeCategory === "saved"
                  ? "bg-brand text-white shadow-sm"
                  : "matte-chip text-(--text-secondary)"
              )}
            >
              <BookmarkIcon size={12} />
              <span>{t("news:categories.saved")}</span>
              <span className="tabular-nums">({bookmarkCount})</span>
            </button>
          )}

          {/* Sort toggle — Wave 116 SW3: aria-label includes visible text
              ("Sort: Newest"/"Sort: Popular") so axe label-content-name-mismatch
              does not fire (visible "Newest" must appear in accessible name). */}
          {(() => {
            const currentSortLabel =
              sortMode === "newest" ? t("news:sort.newest") : t("news:sort.popular")
            const sortPrefix = t("news:sort.label")
            return (
              <button
                type="button"
                onClick={() => onSortChange(sortMode === "newest" ? "popular" : "newest")}
                className="ml-auto flex min-h-[44px] items-center gap-1.5 rounded-full matte-chip px-3 py-2 text-xs font-semibold text-(--text-secondary) shrink-0"
                aria-label={`${sortPrefix}: ${currentSortLabel}`}
              >
                <ArrowUpDown size={13} />
                <span>{currentSortLabel}</span>
              </button>
            )
          })()}
        </FadeSection>
      </div>
    </header>
  )
}
