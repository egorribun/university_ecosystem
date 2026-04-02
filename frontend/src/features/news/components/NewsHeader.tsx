import { Plus, Search, X, ArrowUpDown } from "lucide-react"
import { useTranslation } from "react-i18next"
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
  activeCategory: NewsCategory | "all"
  onCategoryChange: (c: NewsCategory | "all") => void
  sortMode: SortMode
  onSortChange: (s: SortMode) => void
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
}: NewsHeaderProps) => {
  const { t } = useTranslation(["news", "common"])

  return (
    <header className="mb-6 sm:mb-8 space-y-4">
      {/* Row 1: Title + search + admin button */}
      <FadeSection delay="60ms" className="flex items-center gap-3 flex-wrap">
        <h1 className="text-fluid-h1 font-extrabold tracking-tight text-text-primary shrink-0">
          {t("news:pageTitle")}
        </h1>
        {newsCount != null && (
          <span className="px-2 py-0.5 rounded-full bg-brand/(--opacity-subtle) border border-brand/(--opacity-dim) text-xs font-bold tabular-nums text-brand shrink-0">
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
            type="search"
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

      {/* Row 2: Category pills + sort toggle */}
      <FadeSection delay="100ms" className="flex items-center gap-2 flex-wrap">
        {/* "All" pill */}
        <button
          type="button"
          onClick={() => onCategoryChange("all")}
          className={cn(
            "rounded-full px-3 py-1.5 text-xs font-semibold tracking-wide transition-all duration-fast border",
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
            className={cn(
              "rounded-full px-3 py-1.5 text-xs font-semibold tracking-wide transition-all duration-fast border",
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
    </header>
  )
}
