import { useCallback } from "react"
import { useQueryClient } from "@tanstack/react-query"

import Layout from "../components/Layout"
import PageFadeIn from "../components/PageFadeIn"
import DashboardStories from "@/components/DashboardStories"
import { useAuth } from "../contexts/AuthContext"
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
import { ScrollReveal } from "@/components/ScrollReveal"
import useMediaQuery from "@/hooks/useMediaQuery"

export default function Dashboard() {
  const { user, loading: authLoading } = useAuth()
  const isNarrow = useMediaQuery("(max-width:1100px)")
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
      <Layout>
        <DashboardSkeleton />
      </Layout>
    )
  }

  return (
    <Layout>
      <PageFadeIn>
        <DashboardHero
          user={user}
          time={time}
          hh={hh}
          mm={mm}
          dateStr={dateStr}
          isNarrow={isNarrow}
          prefersReducedMotion={prefersReducedMotion}
        />

        <div className="relative z-1 -mt-10 px-4 pb-16 sm:px-8 md:px-12 lg:px-16">
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
      </PageFadeIn>
    </Layout>
  )
}




