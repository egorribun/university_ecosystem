import { memo, type CSSProperties, type KeyboardEvent } from "react"
import { Link } from "@tanstack/react-router"
import { useTranslation } from "react-i18next"

import { Button } from "@/components/ui/Button"
import { Card } from "@/components/ui/Card"
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
  queryResult?: ReturnType<typeof useDashboardNews>
}

export function prepareOnKey(event: Pick<KeyboardEvent, "key">, callback: () => void): void {
  switch (event.key) {
    case "Enter":
    case " ":
    case "Spacebar":
      callback()
      break
  }
}

type NewsCardPresentationProps = Omit<NewsCardProps, "queryResult"> & {
  queryResult: ReturnType<typeof useDashboardNews>
}

function NewsCardWithQuery(props: Omit<NewsCardProps, "queryResult">) {
  const { language } = useLanguage()
  const queryResult = useDashboardNews(language)
  return <NewsCardContent {...props} queryResult={queryResult} />
}

export const NewsCard = memo(function NewsCard(props: NewsCardProps) {
  const { queryResult, ...presentationProps } = props
  if (queryResult) {
    return <NewsCardContent {...presentationProps} queryResult={queryResult} />
  }
  return <NewsCardWithQuery {...presentationProps} />
})

const NewsCardContent = memo(function NewsCardContent({
  locale,
  className,
  style,
  queryResult: dashboardNewsQuery,
  ...props
}: NewsCardPresentationProps) {
  const { t } = useTranslation(["dashboard", "common"])
  const { language } = useLanguage()
  const queryClient = useQueryClient()

  const news: NewsItem[] = dashboardNewsQuery.data ?? []
  const loadingNews = dashboardNewsQuery.isLoading && news.length === 0

  const prefetchNewsList = () => {
    void prefetchDashboardNews(queryClient, language)
  }

  return (
    <Card
      className={cn(
        "group glass-noise refetch-shimmer dash-border-shimmer transition-all duration-base ease-back-out p-6 md:p-7",
        "motion-reduce:hover:transform-none",
        "dash-panel-news",
        className
      )}
      padding="none"
      aria-busy={loadingNews}
      data-refetching={dashboardNewsQuery.isFetching && !dashboardNewsQuery.isLoading}
      style={style}
      {...props}
    >
      <div className="relative z-deep space-y-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2
            className="font-extrabold text-text-primary"
            style={{ fontSize: "clamp(1.35rem, 2.5vw, 1.75rem)" }}
          >
            {t("dashboard:news.heading")}
          </h2>
          <Button
            as={Link}
            to="/news"
            size="sm"
            variant="outline"
            className="btn-dash whitespace-nowrap px-5 transition-transform duration-base hover:-translate-y-0.5"
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
})
