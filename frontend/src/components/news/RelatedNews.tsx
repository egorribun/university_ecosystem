import { type NewsItem } from "@/api/news"

import SmartImage from "@/components/media/SmartImage"
import { cn } from "@/utils/cn"
import { localizeField } from "@/utils/localize"
import { Link } from "@tanstack/react-router"
import { ArrowUpRight } from "lucide-react"
import { useTranslation } from "react-i18next"
import { useLanguage } from "@/contexts/LanguageContext"
import { useMemo } from "react"
import { getMoscowDate } from "@/utils/date"
import { NewsCategoryBadge } from "./NewsCategoryBadge"
import { inferCategory } from "@/features/news/categories"

interface RelatedNewsProps {
  items: NewsItem[]
}

export function RelatedNews({ items }: RelatedNewsProps) {
  const { t } = useTranslation(["news"])
  const { language } = useLanguage()

  if (items.length === 0) return null

  return (
    <section aria-label={t("news:related.title")}>
      <h2 className="text-lg font-bold tracking-tight text-text-primary mb-4">
        {t("news:related.title")}
      </h2>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        {items.map((item) => (
          <RelatedCard key={item.id} item={item} language={language} />
        ))}
      </div>
    </section>
  )
}

function RelatedCard({ item, language }: { item: NewsItem; language: string }) {
  const { t } = useTranslation(["news", "common"])

  const title = useMemo(
    () => localizeField(item.title, item.title_en, language),
    [language, item.title, item.title_en]
  )

  const category = useMemo(
    () => inferCategory(item.title, item.content),
    [item.title, item.content]
  )

  const dateLabel = useMemo(
    () => (item.created_at ? getMoscowDate(item.created_at) : ""),
    [item.created_at]
  )

  return (
    <Link
      to="/news/$id"
      params={{ id: item.id }}
      className={cn(
        "group flex flex-col rounded-xl overflow-hidden card-matte glass-noise",
        "border border-glass-border/(--opacity-soft)",
        "transition-all duration-base hover:shadow-premium-lift hover:-translate-y-1"
      )}
    >
      {/* Compact image */}
      <div className="relative h-32 overflow-hidden">
        {item.image_url ? (
          <SmartImage
            srcRaw={item.image_url}
            alt={title ? t("news:alt.hero", { title }) : t("news:alt.heroFallback")}
            sizes="(min-width: 640px) 33vw, 100vw"
            className="h-full w-full object-cover transition-transform duration-slower group-hover:scale-105"
          />
        ) : (
          <div className="flex h-full w-full items-center justify-center bg-linear-to-br from-brand/(--opacity-subtle) to-transparent">
            <ArrowUpRight size={24} className="text-brand/(--opacity-medium)" />
          </div>
        )}
        {/* Category badge */}
        <div className="absolute left-2 top-2 z-surface">
          <NewsCategoryBadge category={category} size="sm" />
        </div>
      </div>

      {/* Content */}
      <div className="flex flex-1 flex-col gap-1.5 p-4">
        <h3 className="text-sm font-semibold leading-snug text-text-primary line-clamp-2">
          {title}
        </h3>
        {dateLabel && (
          <span className="text-[11px] font-medium text-(--text-secondary) uppercase tracking-wider">
            {dateLabel}
          </span>
        )}
      </div>
    </Link>
  )
}
