import { useMemo, useCallback, type CSSProperties } from "react"
import { Link, useNavigate } from "react-router-dom"
import { useTranslation } from "react-i18next"
import { useQueryClient } from "@tanstack/react-query"

import Layout from "../components/Layout"
import PageFadeIn from "../components/PageFadeIn"
import DashboardStories from "@/components/DashboardStories"
import WeatherWidget from "@/components/WeatherWidget"
import { Badge, Button, Card } from "@/components/ui"
import { useAuth } from "../contexts/AuthContext"
import { getLocaleForLanguage, useLanguage } from "@/contexts/LanguageContext"
import { useDashboardStories, prefetchDashboardStories } from "@/hooks/useDashboardStories"
import { useClock } from "@/hooks/useClock"
import { cn } from "@/utils/cn"
import type { StoryItem } from "@/types/Story"
// Extracted Components
import { ScheduleCard } from "@/components/dashboard/ScheduleCard"
import { NewsCard } from "@/components/dashboard/NewsCard"
import { EventsCard } from "@/components/dashboard/EventsCard"
import DashboardSkeleton from "@/components/dashboard/DashboardSkeleton"
import Magnetic from "@/components/Magnetic"
import { ScrollReveal } from "@/components/ScrollReveal"

function getGreetingKey(hour: number): "morning" | "afternoon" | "evening" | "night" {
  if (hour >= 4 && hour < 12) return "morning"
  if (hour >= 12 && hour < 17) return "afternoon"
  if (hour >= 17 && hour <= 23) return "evening"
  return "night"
}

export default function Dashboard() {
  const { user, loading: authLoading } = useAuth()
  const isNarrow = useMediaQuery("(max-width:1100px)")
  const prefersReducedMotion = useMediaQuery("(prefers-reduced-motion: reduce)")
  const navigate = useNavigate()
  const { language } = useLanguage()
  const locale = getLocaleForLanguage(language)
  const { t } = useTranslation(["dashboard", "common", "navigation"])
  const { hh, mm, dateStr, time } = useClock(locale)

  const greetingKey = useMemo(() => getGreetingKey(time.getHours()), [time])
  const greeting = t(`dashboard:greeting.${greetingKey}`)

  const queryClient = useQueryClient()

  const dashboardStoriesQuery = useDashboardStories()
  const stories: StoryItem[] = dashboardStoriesQuery.data ?? []
  const loadingStories = dashboardStoriesQuery.isLoading && stories.length === 0

  const prefetchStories = useCallback(() => {
    void prefetchDashboardStories(queryClient)
  }, [queryClient])

  const handleStoryOpen = useCallback(() => {
    prefetchStories()
  }, [prefetchStories])

  const headerGradientClass = cn(
    "transition-[background] duration-700",
    isNarrow
      ? "bg-[linear-gradient(135deg,var(--dash-header-grad-start),var(--dash-header-grad-end))]"
      : "bg-[linear-gradient(125deg,var(--dash-header-grad-start),var(--dash-header-grad-end))]"
  )

  const heroSectionClass = cn(
    "relative flex min-h-screen w-full flex-col overflow-hidden",
    "px-4 pb-16 pt-10 text-page-foreground sm:px-8 md:px-12 lg:px-16",
    "bg-[linear-gradient(145deg,var(--hero-grad-start),var(--hero-grad-end))]"
  )

  const heroBackdropLayers = useMemo(() => {
    const layers = [
      "absolute inset-0 -z-10 bg-[radial-gradient(circle_at_top,var(--dash-hero-radial-top),transparent_78%)] mix-blend-soft-light",
      "absolute inset-0 -z-20 bg-[radial-gradient(circle_at_bottom,var(--dash-hero-radial-bottom),transparent_78%)]",
    ]

    const orbSize = isNarrow ? "h-[28rem] w-[28rem]" : "h-[46rem] w-[46rem]"
    layers.push(
      `absolute -top-56 left-1/2 ${orbSize} -translate-x-1/2 rounded-full bg-[radial-gradient(circle,var(--dash-hero-orb),transparent)] blur-[210px]`
    )

    if (!isNarrow) {
      layers.push(
        prefersReducedMotion
          ? "absolute bottom-[-16rem] right-[10%] h-[28rem] w-[28rem] rounded-full bg-[radial-gradient(circle,var(--dash-hero-pulse),transparent)] opacity-70 blur-[180px]"
          : "absolute bottom-[-18rem] right-[8%] h-[34rem] w-[34rem] animate-[pulse_14s_ease-in-out_infinite] rounded-full bg-[radial-gradient(circle,var(--dash-hero-pulse),transparent)] blur-[210px]"
      )
    }

    if (!prefersReducedMotion && !isNarrow) {
      layers.push(
        "absolute -left-28 top-1/2 h-[30rem] w-[30rem] -translate-y-1/2 animate-[spin_26s_linear_infinite] rounded-full bg-[conic-gradient(from_120deg_at_50%_50%,var(--dash-hero-conic-primary),var(--dash-hero-conic-secondary),var(--dash-hero-conic-tertiary),var(--dash-hero-conic-accent))] opacity-80 blur-[220px]"
      )
    } else if (!isNarrow) {
      layers.push(
        "absolute -left-24 top-1/2 h-[26rem] w-[26rem] -translate-y-1/2 rounded-full bg-[conic-gradient(from_140deg_at_50%_50%,var(--dash-hero-conic-primary),var(--dash-hero-conic-secondary),transparent_85%)] opacity-60 blur-[200px]"
      )
    }

    return layers
  }, [isNarrow, prefersReducedMotion])

  const showHeaderMotion = !prefersReducedMotion && !isNarrow

  if (authLoading) {
    return (
      <Layout>
        <DashboardSkeleton />
      </Layout>
    )
  }

  return (
    <Layout>
      <PageFadeIn>
        <section className={heroSectionClass}>
          <div aria-hidden="true" className="pointer-events-none absolute inset-0">
            {heroBackdropLayers.map((layer, index) => (
              <div key={index} className={layer} />
            ))}
          </div>
          <div className="relative z-[1] space-y-6">
            <ScrollReveal mode="pop" delay={0.1} width="100%">
              <header
                className={cn(
                  "group card-glass rounded-[2.4rem] transition-all duration-500 ease-[cubic-bezier(0.34,1.56,0.64,1)]",
                  "hover:-translate-y-1 hover:scale-[1.01] hover:shadow-xl motion-reduce:hover:transform-none motion-reduce:hover:shadow-none",
                  "p-6 md:p-9 focus-within:shadow-focus focus-visible:outline-none focus-visible:shadow-focus",
                  headerGradientClass
                )}
              >
                <span
                  aria-hidden="true"
                  className="pointer-events-none absolute inset-0 dash-highlight-veil bg-[radial-gradient(circle_at_top_left,color-mix(in_srgb,var(--dash-hero-highlight-soft)_65%,transparent),transparent_60%)] transition-opacity duration-700"
                />
                {showHeaderMotion ? (
                  <span
                    aria-hidden="true"
                    className="pointer-events-none absolute -inset-y-24 -left-1/2 w-[170%] skew-x-[-18deg] bg-gradient-to-r from-transparent via-white/55 to-transparent opacity-0 transition-all duration-[2200ms] ease-out group-hover:translate-x-[35%] group-hover:opacity-70"
                  >
                    <span className="block h-full w-full animate-skeleton-wave bg-gradient-to-r from-transparent via-white/70 to-transparent" />
                  </span>
                ) : (
                  <span
                    aria-hidden="true"
                    className="pointer-events-none absolute -inset-y-20 -left-1/2 w-[160%] skew-x-[-14deg] bg-gradient-to-r from-transparent via-white/35 to-transparent opacity-0 transition-opacity duration-700 ease-out group-hover:opacity-45"
                  />
                )}
                <div className="pointer-events-none absolute -right-24 top-1/2 h-64 w-64 -translate-y-1/2 rounded-full bg-[radial-gradient(circle,var(--dash-hero-highlight),transparent)] dash-highlight-veil blur-3xl" />
                {showHeaderMotion ? (
                  <div className="pointer-events-none absolute left-[-20%] top-[-40%] h-56 w-56 animate-[spin_18s_linear_infinite] rounded-full bg-[conic-gradient(from_90deg_at_50%_50%,var(--dash-hero-conic-primary),var(--dash-hero-conic-secondary),var(--dash-hero-conic-tertiary),var(--dash-hero-conic-accent))] opacity-60 blur-[120px]" />
                ) : (
                  <div className="pointer-events-none absolute left-[-18%] top-[-42%] h-48 w-48 rounded-full bg-[conic-gradient(from_130deg_at_50%_50%,var(--dash-hero-conic-primary),var(--dash-hero-conic-secondary),transparent_85%)] opacity-50 blur-[110px]" />
                )}
                <div className="relative grid gap-6 lg:grid-cols-12 lg:items-center">
                  <div className="space-y-3 text-nav-text lg:col-span-8">
                    <h1 className="font-display text-[clamp(1.5rem,2.4vw,2.6rem)] font-extrabold leading-tight">
                      {greeting}
                      {user?.full_name ? `, ${user.full_name.split(" ")[0]}` : ""}!
                    </h1>
                    <div
                      className="flex flex-wrap items-center gap-x-3 gap-y-2 text-sm text-nav-text/90"
                      role="status"
                      aria-live="polite"
                    >
                      <Badge
                        size="sm"
                        className="flex-shrink-0 border-slate-200 bg-slate-100 font-mono text-base text-slate-700 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300"
                        aria-label={t("common:ariaCurrentTime")}
                      >
                        <span className="flex items-baseline gap-1 font-mono text-lg leading-none">
                          <span>{hh}</span>
                          <span
                            aria-hidden="true"
                            className="inline-block animate-dash-colon-blink"
                          >
                            :
                          </span>
                          <span>{mm}</span>
                        </span>
                      </Badge>
                      <WeatherWidget className="flex-shrink-0" />
                      <span className="text-sm font-medium tracking-tight leading-tight">
                        {dateStr}
                      </span>
                    </div>
                  </div>
                  <div className="hidden justify-end md:flex lg:col-span-4">
                    <Magnetic strength={0.25}>
                      <Button
                        variant="outline"
                        size="md"
                        className="whitespace-nowrap px-5 transition-transform duration-300 hover:-translate-y-[2px]"
                        onClick={() => navigate("/profile")}
                        aria-label={t("navigation:aria.openProfile")}
                      >
                        {t("navigation:menu.profile")}
                      </Button>
                    </Magnetic>
                  </div>
                </div>
              </header>
            </ScrollReveal>

            <ScrollReveal mode="slide" direction="up" delay={0.2}>
              <DashboardStories
                stories={stories}
                loading={loadingStories}
                onPrefetch={prefetchStories}
                onStoryOpen={handleStoryOpen}
              />
            </ScrollReveal>

            <section className="mt-6 grid grid-cols-1 gap-4 md:mt-8 md:gap-6 lg:grid-cols-12">
              <ScrollReveal
                mode="slide"
                direction="up"
                delay={0.3}
                className="lg:col-span-4"
                width="100%"
              >
                <ScheduleCard userRole={user?.role} userGroupId={user?.group_id} time={time} />
              </ScrollReveal>

              <ScrollReveal
                mode="slide"
                direction="up"
                delay={0.4}
                className="lg:col-span-4"
                width="100%"
              >
                <NewsCard locale={locale} />
              </ScrollReveal>

              <ScrollReveal
                mode="slide"
                direction="up"
                delay={0.5}
                className="lg:col-span-4"
                width="100%"
              >
                <EventsCard locale={locale} />
              </ScrollReveal>
            </section>
          </div>
        </section>
      </PageFadeIn>
    </Layout>
  )
}

// Helper for useMediaQuery since it was imported from hooks
import useMediaQuery from "@/hooks/useMediaQuery"
