import { type CSSProperties, type KeyboardEvent } from "react"
import { Link } from "react-router-dom"
import { useTranslation } from "react-i18next"

import { Button, Card } from "@/components/ui"
import { cn } from "@/utils/cn"
import { useDashboardNews, prefetchDashboardNews } from "@/hooks/useDashboardNews"
import { useLanguage } from "@/contexts/LanguageContext"
import { useQueryClient } from "@tanstack/react-query"
import type { NewsItem } from "@/api/news"
import { NewsCardBackground } from "./NewsCardBackground"
import { NewsCardList } from "./NewsCardList"

interface NewsCardProps {
  locale: string
  className?: string
  style?: CSSProperties
  "data-fade"?: string
  "data-pop"?: string
}

export function NewsCard({ locale, className, style, ...props }: NewsCardProps) {
  const { t } = useTranslation(["dashboard", "common"])
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
      <div className="relative z-deep space-y-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-fluid-h2 font-extrabold text-(--text-primary)">
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

        <NewsCardList news={news} loading={loadingNews} locale={locale} />
      </div>
      <NewsCardBackground />
    </Card>
  )
}
