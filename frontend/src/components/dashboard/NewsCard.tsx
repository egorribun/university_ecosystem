import { type CSSProperties, type KeyboardEvent } from "react"
import { motion } from "framer-motion"
import { Link, useNavigate } from "react-router-dom"
import { useTranslation } from "react-i18next"
import { ArrowRight } from "lucide-react"

import { Button, Card, Skeleton } from "@/components/ui"
import { cn } from "@/utils/cn"
import { useDashboardNews, prefetchDashboardNews } from "@/hooks/useDashboardNews"
import { useLanguage } from "@/contexts/LanguageContext"
import { useQueryClient } from "@tanstack/react-query"
import type { NewsItem } from "@/api/news"
import { DateBullet } from "./DateBullet"

interface NewsCardProps {
  locale: string
  className?: string
  style?: CSSProperties
  "data-fade"?: string
  "data-pop"?: string
}

export function NewsCard({ locale, className, style, ...props }: NewsCardProps) {
  const { t } = useTranslation(["dashboard", "common"])
  const navigate = useNavigate()
  const { language } = useLanguage()
  const queryClient = useQueryClient()

  const dashboardNewsQuery = useDashboardNews(language)
  const news: NewsItem[] = dashboardNewsQuery.data ?? []
  const loadingNews = dashboardNewsQuery.isLoading && news.length === 0

  const warmNewsPage = () => import("../../pages/News").catch(() => {})

  const prefetchNewsList = () => {
    warmNewsPage()
    void prefetchDashboardNews(queryClient, language)
  }

  const prepareOnKey = (event: KeyboardEvent, callback: () => void) => {
    if (event.key === "Enter" || event.key === " " || event.key === "Spacebar") {
      callback()
    }
  }

  const listActionBase =
    "group relative isolate w-full overflow-hidden rounded-xl border border-border-subtle bg-surface-hover/10 px-4 py-3 text-left transition-all duration-300 ease-out hover:bg-surface-hover/20 hover:border-border-strong hover:-translate-y-0.5 hover:shadow-premium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/50"

  return (
    <Card
      className={cn(
        "group bg-glass backdrop-blur-3xl transition-all duration-300 ease-[cubic-bezier(0.34,1.56,0.64,1)]",
        "hover:-translate-y-1 hover:scale-[1.01] hover:shadow-glass motion-reduce:hover:transform-none motion-reduce:hover:shadow-none",
        "dash-panel-news border-glass-border",
        className
      )}
      padding="lg"
      aria-busy={loadingNews}
      style={style}
      {...props}
    >
      <div className="relative z-1 space-y-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-[clamp(1.1rem,2vw,1.5rem)] font-extrabold text-primary-text">
            {t("dashboard:news.heading")}
          </h2>
          <Button
            as={Link}
            to="/news"
            size="sm"
            variant="outline"
            className="whitespace-nowrap px-5 transition-transform duration-300 hover:-translate-y-[2px]"
            aria-label={t("dashboard:aria.viewAllNews")}
            onPointerDown={prefetchNewsList}
            onKeyDown={(event) => {
              prepareOnKey(event, prefetchNewsList)
            }}
          >
            {t("dashboard:viewAll")}
          </Button>
        </div>

        {loadingNews && (
          <div className="space-y-4" role="presentation">
            {[1, 2].map((i) => (
              <div
                key={i}
                className="flex items-start gap-4 rounded-ue-lg border border-[--dash-panel-item-divider] bg-[--dash-panel-item-bg] px-4 py-3 opacity-60"
              >
                <Skeleton width={44} height={44} rounded="9999px" className="shrink-0" />
                <div className="flex-1 space-y-2">
                  <Skeleton height={20} width="90%" />
                  <Skeleton height={14} width="70%" />
                  <Skeleton height={14} width="40%" />
                </div>
              </div>
            ))}
          </div>
        )}
        {!loadingNews && news.length === 0 && (
          <p className="text-sm text-secondary">{t("dashboard:news.empty")}</p>
        )}
        {!loadingNews && news.length > 0 && (
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
                    <span className="text-[clamp(.98rem,.9rem+.4vw,1.06rem)] font-bold leading-snug text-primary-text">
                      {n.title}
                    </span>
                    <span className="text-sm text-secondary-text">
                      {(n.content || "").slice(0, 110)}
                      {(n.content || "").length > 110 ? "…" : ""}
                    </span>
                  </div>
                  <span
                    aria-hidden="true"
                    className="ml-auto inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-glass-border bg-surface/20 text-primary-text opacity-0 transition-all duration-300 group-hover:opacity-100 group-hover:border-brand group-hover:bg-brand/10 group-hover:text-brand"
                  >
                    <ArrowRight aria-hidden="true" className="h-4 w-4" />
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
      <motion.span
        aria-hidden="true"
        initial={{ opacity: 0 }}
        whileHover={{ opacity: 0.8 }}
        animate={{
          scale: [1, 1.1, 1],
        }}
        transition={{
          duration: 4.5,
          repeat: Infinity,
          ease: "easeInOut",
        }}
        className="pointer-events-none absolute inset-0 z-0 bg-[radial-gradient(circle_at_top_right,var(--dash-card-news-radial),transparent_68%)] mix-blend-soft-light transition-opacity duration-500"
      />
      <motion.span
        aria-hidden="true"
        initial={{ opacity: 0.3 }}
        whileHover={{ opacity: 0.7 }}
        animate={{
          scale: [1, 1.18, 1],
          rotate: [0, -5, 0],
          x: [0, 10, 0],
        }}
        transition={{
          duration: 6.5,
          repeat: Infinity,
          ease: "easeInOut",
        }}
        className="pointer-events-none absolute -bottom-20 left-1/3 z-0 h-44 w-44 rounded-full bg-[radial-gradient(circle,var(--dash-card-news-orb),transparent)] blur-3xl mix-blend-soft-light transition-opacity duration-700"
      />
    </Card>
  )
}
