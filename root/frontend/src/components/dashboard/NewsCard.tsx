import { type CSSProperties, type KeyboardEvent } from "react"
import { Link, useNavigate } from "react-router-dom"
import { useTranslation } from "react-i18next"
import ArrowForwardRoundedIcon from "@mui/icons-material/ArrowForwardRounded"

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

  // Styles
  const panelBase =
    "group relative isolate overflow-hidden rounded-[2.4rem] border !border-[color:var(--dash-panel-border)] !bg-[color:var(--dash-panel-bg-muted)] text-page-foreground !shadow-[var(--dash-panel-shadow-soft)] transition-[transform,box-shadow] duration-[var(--dash-hover-duration)] ease-[var(--dash-hover-ease)]"
  const panelHover =
    "hover:-translate-y-[var(--dash-hover-lift)] hover:scale-[var(--dash-hover-scale)] hover:shadow-[var(--dash-panel-hover-shadow)] motion-reduce:hover:transform-none motion-reduce:hover:shadow-[var(--dash-panel-shadow)]"
  const listActionBase =
    "group relative isolate w-full overflow-hidden rounded-ue-lg border border-[color:var(--dash-panel-item-divider)] bg-[color:var(--dash-panel-item-bg)] px-4 py-3 text-left transition-[background-color,transform,box-shadow,border-color] duration-[var(--dash-hover-duration)] ease-[var(--dash-hover-ease)] sm:px-5 sm:py-4 group-even/list:bg-[color:var(--dash-panel-item-bg-alt)] hover:border-[color:var(--dash-panel-item-ring)] hover:bg-[color:var(--dash-panel-item-hover)] hover:-translate-y-[var(--dash-hover-lift)] hover:scale-[var(--dash-hover-scale)] focus-visible:border-[color:var(--dash-panel-item-ring)] focus-visible:outline-none focus-visible:shadow-focus motion-reduce:hover:transform-none motion-reduce:hover:translate-y-0 motion-reduce:hover:scale-100 before:pointer-events-none before:absolute before:inset-0 before:rounded-[inherit] before:border before:border-[color:var(--dash-panel-item-ring)] before:opacity-0 before:scale-[0.96] before:transition-[transform,opacity,border-color] before:duration-[var(--dash-hover-duration)] before:ease-[var(--dash-hover-ease)] before:content-[''] hover:before:opacity-100 hover:before:scale-100"

  return (
    <Card
      className={cn(panelBase, panelHover, "dash-panel-news", className)}
      padding="lg"
      aria-busy={loadingNews}
      style={style}
      {...props}
    >
      <div className="relative z-[1] space-y-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-[clamp(1.05rem,2vw,1.4rem)] font-extrabold text-page-foreground">
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
            <div className="flex items-center gap-3">
              <Skeleton width={44} height={44} rounded="9999px" />
              <div className="flex-1 space-y-2">
                <Skeleton height={22} />
                <Skeleton height={18} width="60%" />
              </div>
            </div>
            <div className="flex items-center gap-3">
              <Skeleton width={44} height={44} rounded="9999px" />
              <div className="flex-1 space-y-2">
                <Skeleton height={22} width="80%" />
                <Skeleton height={18} width="50%" />
              </div>
            </div>
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
                    <span className="text-[clamp(.98rem,.9rem+.4vw,1.06rem)] font-bold leading-snug text-page-foreground">
                      {n.title}
                    </span>
                    <span className="text-sm text-secondary">
                      {(n.content || "").slice(0, 110)}
                      {(n.content || "").length > 110 ? "…" : ""}
                    </span>
                  </div>
                  <span
                    aria-hidden="true"
                    className="ml-auto inline-flex h-9 w-9 flex-none items-center justify-center rounded-full border border-[color:var(--dash-arrow-pill-border)] bg-[color:var(--dash-arrow-pill-bg)] text-base text-[color:var(--dash-arrow-pill-text)] opacity-0 transition-[transform,opacity,background-color,border-color] duration-[var(--dash-hover-duration)] ease-[var(--dash-hover-ease)] group-hover:-translate-y-[calc(var(--dash-hover-lift)/2)] group-hover:opacity-100 group-hover:border-[color:var(--dash-arrow-pill-border-active)] group-hover:bg-[color:var(--dash-arrow-pill-bg-active)] group-hover:text-[color:var(--dash-arrow-pill-text-active)]"
                  >
                    <ArrowForwardRoundedIcon
                      aria-hidden="true"
                      fontSize="inherit"
                      className="h-4 w-4"
                    />
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
      <span
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 z-0 bg-[radial-gradient(circle_at_top_right,var(--dash-card-news-radial),transparent_68%)] opacity-0 mix-blend-soft-light transition-opacity duration-500 group-hover:opacity-80"
      />
      <span
        aria-hidden="true"
        className="pointer-events-none absolute -bottom-20 left-1/3 z-0 h-44 w-44 rounded-full bg-[radial-gradient(circle,var(--dash-card-news-orb),transparent)] opacity-30 blur-3xl mix-blend-soft-light transition duration-700 group-hover:opacity-70"
      />
    </Card>
  )
}
