import { useNavigate } from "react-router-dom"
import { useTranslation } from "react-i18next"
import { ArrowRight } from "lucide-react"
import { cn } from "@/utils/cn"
import { Skeleton } from "@/components/ui"
import { DateBullet } from "./DateBullet"
import type { NewsItem } from "@/api/news"

interface NewsCardListProps {
  news: NewsItem[]
  loading: boolean
  locale: string
}

export function NewsCardList({ news, loading, locale }: NewsCardListProps) {
  const { t } = useTranslation(["dashboard"])
  const navigate = useNavigate()

  const listActionBase =
    "group relative isolate w-full overflow-hidden rounded-lg border border-border-subtle bg-surface-hover/subtle px-4 py-3 text-left transition-all duration-base ease-out hover:bg-surface-hover/dim hover:border-border-strong hover:-translate-y-0.5 hover:shadow-premium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/medium"

  if (loading) {
    return (
      <div className="space-y-4" role="presentation">
        {[1, 2].map((i) => (
          <div
            key={i}
            className="flex items-start gap-4 rounded-lg border border-border-subtle bg-(--bg-surface)/(--opacity-dim) px-4 py-3 opacity-medium"
          >
            <Skeleton width="2.75rem" height="2.75rem" rounded="9999rem" className="shrink-0" />
            <div className="flex-1 space-y-2">
              <Skeleton height={20} width="90%" />
              <Skeleton height={14} width="70%" />
              <Skeleton height={14} width="40%" />
            </div>
          </div>
        ))}
      </div>
    )
  }

  if (news.length === 0) {
    return <p className="text-sm text-(--text-secondary)">{t("dashboard:news.empty")}</p>
  }

  return (
    <ul className="space-y-3" aria-label={t("dashboard:aria.newsList")}>
      {news.map((n) => (
        <li key={n.id} className="dash-list-item">
          <button
            type="button"
            className={cn(listActionBase, "flex items-start gap-4 text-left sm:gap-5")}
            onClick={() => navigate(`/news/${n.id}`)}
            title={n.title}
            aria-label={t("dashboard:aria.newsItem", { title: n.title })}
          >
            <DateBullet date={n.created_at} locale={locale} />
            <div className="flex flex-col gap-1">
              <span className="text-fluid-h3 font-bold leading-snug text-text-primary">
                {n.title}
              </span>
              <span className="text-sm text-(--text-secondary)">
                {(n.content || "").slice(0, 110)}
                {(n.content || "").length > 110 ? "…" : ""}
              </span>
            </div>
            <span
              aria-hidden="true"
              className="ml-auto inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-glass-border bg-surface/dim text-text-primary opacity-0 transition-all duration-base group-hover:opacity-100 group-hover:border-brand group-hover:bg-brand/subtle group-hover:text-brand"
            >
              <ArrowRight aria-hidden="true" className="h-4 w-4" />
            </span>
          </button>
        </li>
      ))}
    </ul>
  )
}
