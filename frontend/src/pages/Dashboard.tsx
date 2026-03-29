import { useCallback } from "react"
import { useQueryClient } from "@tanstack/react-query"
import { useTranslation } from "react-i18next"

import { SEO } from "@/components/ui/SEO"

import { PageLayout } from "@/components/layout/PageLayout"
import { DashboardStories } from "@/components/stories"
import { useAuth } from "@/contexts/AuthContext"
import { getLocaleForLanguage, useLanguage } from "@/contexts/LanguageContext"
import { useDashboardStories, prefetchDashboardStories } from "@/hooks/useDashboardStories"
import { useClock } from "@/hooks/useClock"
import type { StoryItem } from "@/types/Story"

// Extracted Components
import { DashboardHero } from "@/components/dashboard/DashboardHero"
import { ScheduleCard } from "@/components/dashboard/ScheduleCard"
import { NewsCard } from "@/components/dashboard/NewsCard"
import { EventsCard } from "@/components/dashboard/EventsCard"
import DashboardSkeleton from "@/components/dashboard/DashboardSkeleton"
import { ScrollReveal } from "@/components/motion/ScrollReveal"
import useMediaQuery from "@/hooks/useMediaQuery"
import { breakpoints } from "@/theme/tokens"

export default function Dashboard() {
  const { t } = useTranslation(["dashboard", "common"])
  const { user, loading: authLoading } = useAuth()
  const isNarrow = useMediaQuery(`(max-width: ${breakpoints.dashboard})`)
  const prefersReducedMotion = useMediaQuery("(prefers-reduced-motion: reduce)")
  const { language } = useLanguage()
  const locale = getLocaleForLanguage(language)
  const { hh, mm, dateStr, time } = useClock(locale)

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

  if (authLoading) {
    return (
      <PageLayout variant="full" className="py-0 md:py-0">
        <DashboardSkeleton />
      </PageLayout>
    )
  }

  return (
    <PageLayout variant="full" className="dashboard-theme py-0 md:py-0">
      <SEO title={t("dashboard:pageTitle", "Dashboard")} />
      <DashboardHero
        user={user}
        time={time}
        hh={hh}
        mm={mm}
        dateStr={dateStr}
        isNarrow={isNarrow}
        prefersReducedMotion={prefersReducedMotion}
      >
        <ScrollReveal mode="slide" direction="up" delay={0.2}>
          <DashboardStories
            stories={stories}
            loading={loadingStories}
            onPrefetch={prefetchStories}
            onStoryOpen={handleStoryOpen}
          />
        </ScrollReveal>

        <div className="mt-lg grid w-full grid-cols-12 gap-md md:mt-xl md:gap-lg pb-3xl">
          <div className="col-span-12 lg:col-span-4">
            <ScrollReveal mode="slide" direction="up" delay={0.3} width="100%">
              <ScheduleCard userRole={user?.role} userGroupId={user?.group_id} time={time} />
            </ScrollReveal>
          </div>

          <div className="col-span-12 lg:col-span-4">
            <ScrollReveal mode="slide" direction="up" delay={0.4} width="100%">
              <NewsCard locale={locale} />
            </ScrollReveal>
          </div>

          <div className="col-span-12 lg:col-span-4">
            <ScrollReveal mode="slide" direction="up" delay={0.5} width="100%">
              <EventsCard />
            </ScrollReveal>
          </div>
        </div>
      </DashboardHero>
    </PageLayout>
  )
}
