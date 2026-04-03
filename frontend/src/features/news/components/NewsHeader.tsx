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
    const sentinel = sentinelRef.current
    if (!sentinel) return

    const observer = new IntersectionObserver(
      ([entry]) => { if (entry) setIsStuck(!entry.isIntersecting) },
      { threshold: 0 }
    )
    observer.observe(sentinel)
    return () => observer.disconnect()
  }, [])

  return (
    <header className="mb-6 sm:mb-8 space-y-4">
      {/* Row 1: Title + search + admin button */}
      <FadeSection delay="60ms" className="flex items-center gap-3 flex-wrap">
        <div className="flex items-center gap-3 shrink-0">
          <div className="news-badge-matte flex h-10 w-10 sm:h-11 sm:w-11 items-center justify-center rounded-xl text-text-primary">
            <Newspaper size={20} strokeWidth={2.2} />
          </div>
          <h1 className="text-fluid-h1 font-extrabold tracking-tight text-text-primary">
            {t("news:pageTitle")}
          </h1>
        </div>
        {newsCount != null && (
          <span
            className="news-badge-matte rounded-full px-2.5 py-1 text-xs font-bold tabular-nums shrink-0"
            style={{
              minWidth: 32,
              textAlign: "center",
            }}
          >
            {newsCount}
          </span>
        )}

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
            placeholder={t("news:search.placeholder", { defaultValue: "Search news..." })}
            className="w-full rounded-xl glass-layer-surface border border-glass-border/(--opacity-soft) pl-9 pr-9 py-2 text-sm text-text-primary placeholder:text-(--text-secondary)/(--opacity-medium) focus:outline-none focus-visible:ring-2 focus-visible:ring-brand/(--opacity-medium) transition-shadow"
            aria-label={t("news:search.placeholder", { defaultValue: "Search news..." })}
          />
          {searchQuery && (
            <button
              type="button"
              onClick={() => onSearchChange("")}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-(--text-secondary) hover:text-text-primary transition-colors"
              aria-label={t("common:buttons.clear", { defaultValue: "Clear" })}
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
      <div ref={sentinelRef} className="h-0" aria-hidden />

      {/* Row 2: Category pills + sort toggle — sticky on scroll */}
      <div
        ref={stickyRef}
        className="news-sticky-categories"
        data-stuck={isStuck}
      >
        <FadeSection delay="100ms" className="flex items-center gap-2 sm:flex-wrap max-sm:flex-nowrap max-sm:overflow-x-auto max-sm:scrollbar-none max-sm:pb-1 max-sm:-mx-4 max-sm:px-4">
          {/* "All" pill */}
          <button
            type="button"
            onClick={() => onCategoryChange("all")}
            aria-current={activeCategory === "all" ? "page" : undefined}
            className={cn(
              "rounded-full px-3 py-1.5 text-xs font-semibold tracking-wide transition-all duration-fast border whitespace-nowrap",
              activeCategory === "all"
                ? "bg-brand text-white border-brand shadow-sm"
                : "glass-layer-surface border-glass-border/(--opacity-soft) text-(--text-secondary) hover:text-text-primary hover:border-glass-border"
            )}
          >
            {t("news:categories.all", { defaultValue: "All" })}
          </button>

          {/* Category pills */}
          {ALL_CATEGORIES.map((cat) => (
            <button
              key={cat.id}
              type="button"
              onClick={() => onCategoryChange(cat.id)}
              aria-current={activeCategory === cat.id ? "page" : undefined}
              className={cn(
                "rounded-full px-3 py-1.5 text-xs font-semibold tracking-wide transition-all duration-fast border whitespace-nowrap",
                activeCategory === cat.id
                  ? "shadow-sm"
                  : "glass-layer-surface border-glass-border/(--opacity-soft) text-(--text-secondary) hover:text-text-primary hover:border-glass-border"
              )}
              style={
                activeCategory === cat.id
                  ? {
                      backgroundColor: `var(--cat-${cat.color}-bg)`,
                      color: `var(--cat-${cat.color}-text)`,
                      borderColor: `var(--cat-${cat.color}-text)`,
                    }
                  : undefined
              }
            >
              {t(cat.labelKey, { defaultValue: cat.id })}
            </button>
          ))}

          {/* Saved/bookmark filter — only shown when bookmarks exist */}
          {bookmarkCount > 0 && (
            <button
              type="button"
              onClick={() => onCategoryChange("saved")}
              aria-current={activeCategory === "saved" ? "page" : undefined}
              className={cn(
                "rounded-full px-3 py-1.5 text-xs font-semibold tracking-wide transition-all duration-fast border flex items-center gap-1.5 whitespace-nowrap",
                activeCategory === "saved"
                  ? "bg-brand text-white border-brand shadow-sm"
                  : "glass-layer-surface border-glass-border/(--opacity-soft) text-(--text-secondary) hover:text-text-primary hover:border-glass-border"
              )}
            >
              <BookmarkIcon size={12} />
              <span>{t("news:categories.saved", { defaultValue: "Saved" })}</span>
              <span className="tabular-nums">({bookmarkCount})</span>
            </button>
          )}

          {/* Sort toggle */}
          <button
            type="button"
            onClick={() => onSortChange(sortMode === "newest" ? "popular" : "newest")}
            className="ml-auto flex items-center gap-1.5 rounded-full glass-layer-surface border border-glass-border/(--opacity-soft) px-3 py-1.5 text-xs font-semibold text-(--text-secondary) hover:text-text-primary transition-colors shrink-0"
            aria-label={t("news:sort.label", { defaultValue: "Sort" })}
          >
            <ArrowUpDown size={13} />
            <span>
              {sortMode === "newest"
                ? t("news:sort.newest", { defaultValue: "Newest" })
                : t("news:sort.popular", { defaultValue: "Popular" })}
            </span>
          </button>

        </FadeSection>
      </div>
    </header>
  )
}
