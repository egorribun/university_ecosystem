import { useCallback, useRef, useState, useEffect } from "react"
import { useQueryClient } from "@tanstack/react-query"
import { useTranslation } from "react-i18next"
import { useScroll, useTransform, motion } from "framer-motion"

import { SEO } from "@/components/ui/SEO"

import { PageLayout } from "@/components/layout/PageLayout"
import { DashboardStories } from "@/components/stories"
import { useAuth } from "@/contexts/AuthContext"
import { getLocaleForLanguage, useLanguage } from "@/contexts/LanguageContext"
import { useDashboardStories, prefetchDashboardStories } from "@/hooks/useDashboardStories"
import { useClock } from "@/hooks/useClock"
import type { StoryItem } from "@/types/Story"

import { DashboardHero } from "@/components/dashboard/DashboardHero"
import { DashboardBackdrop } from "@/components/dashboard/DashboardBackdrop"
import { ScheduleCard } from "@/components/dashboard/ScheduleCard"
import { NewsCard } from "@/components/dashboard/NewsCard"
import { EventsCard } from "@/components/dashboard/EventsCard"
import DashboardSkeleton from "@/components/dashboard/DashboardSkeleton"
import { SkeletonMorph } from "@/components/ui/SkeletonMorph"
import { Card, Skeleton } from "@/components/ui"
import useMediaQuery from "@/hooks/useMediaQuery"
import { breakpoints } from "@/theme/tokens"
import { useTilt } from "@/hooks/useTilt"
import { useDashboardSchedule } from "@/hooks/useDashboardSchedule"
import { useDashboardNews } from "@/hooks/useDashboardNews"
import { useDashboardEvents } from "@/hooks/useDashboardEvents"
import { WeatherAmbient } from "@/components/dashboard/WeatherAmbient"
import { useWeather } from "@/hooks/useWeather"

/** Wave 48: Session key for cascade reveal — module-level constant */
const CASCADE_KEY = "dash-cascade-done"

/** Wave 49: Dev-only mock stories — shown when API returns empty */
const MOCK_STORIES: StoryItem[] = [
  {
    id: "mock-1",
    title: "UniHack 2026",
    short_text: "Регистрация на хакатон открыта! Призовой фонд 500 000 ₽",
    cover_url: "https://picsum.photos/seed/unihack/400/700",
    cta_url: "/events",
    published_at: new Date().toISOString(),
    expires_at: new Date(Date.now() + 7 * 86400000).toISOString(),
    is_active: true,
    created_by: null,
    created_at: new Date().toISOString(),
    cover_url_optimized: null,
  },
  {
    id: "mock-2",
    title: "Новая библиотека",
    short_text: "Электронный каталог обновлён — 50 000+ книг онлайн",
    cover_url: "https://picsum.photos/seed/library/400/700",
    cta_url: null,
    published_at: new Date().toISOString(),
    expires_at: new Date(Date.now() + 14 * 86400000).toISOString(),
    is_active: true,
    created_by: null,
    created_at: new Date().toISOString(),
    cover_url_optimized: null,
  },
  {
    id: "mock-3",
    title: "День открытых дверей",
    short_text: "Приглашаем абитуриентов 5 апреля в главный корпус",
    cover_url: "https://picsum.photos/seed/openday/400/700",
    cta_url: "/events",
    published_at: new Date().toISOString(),
    expires_at: new Date(Date.now() + 10 * 86400000).toISOString(),
    is_active: true,
    created_by: null,
    created_at: new Date().toISOString(),
    cover_url_optimized: null,
  },
  {
    id: "mock-4",
    title: "Весенний карьерный форум",
    short_text: "50+ компаний ищут стажёров и джунов. 10 апреля, Актовый зал",
    cover_url: "https://picsum.photos/seed/career/400/700",
    cta_url: null,
    published_at: new Date().toISOString(),
    expires_at: new Date(Date.now() + 12 * 86400000).toISOString(),
    is_active: true,
    created_by: null,
    created_at: new Date().toISOString(),
    cover_url_optimized: null,
  },
  {
    id: "mock-5",
    title: "Спортивный сезон",
    short_text: "Запись в секции: волейбол, баскетбол, плавание, шахматы",
    cover_url: "https://picsum.photos/seed/sport/400/700",
    cta_url: null,
    published_at: new Date().toISOString(),
    expires_at: new Date(Date.now() + 30 * 86400000).toISOString(),
    is_active: true,
    created_by: null,
    created_at: new Date().toISOString(),
    cover_url_optimized: null,
  },
  {
    id: "mock-6",
    title: "Стипендии и гранты",
    short_text: "Подай заявку на повышенную стипендию до 15 апреля",
    cover_url: "https://picsum.photos/seed/scholarship/400/700",
    cta_url: null,
    published_at: new Date().toISOString(),
    expires_at: new Date(Date.now() + 20 * 86400000).toISOString(),
    is_active: true,
    created_by: null,
    created_at: new Date().toISOString(),
    cover_url_optimized: null,
  },
  {
    id: "mock-7",
    title: "Волонтёрский проект",
    short_text: "Присоединяйся к экологической акции «Чистый кампус»",
    cover_url: "https://picsum.photos/seed/volunteer/400/700",
    cta_url: null,
    published_at: new Date().toISOString(),
    expires_at: new Date(Date.now() + 8 * 86400000).toISOString(),
    is_active: true,
    created_by: null,
    created_at: new Date().toISOString(),
    cover_url_optimized: null,
  },
  {
    id: "mock-8",
    title: "Обмен с Берлином",
    short_text: "Программа обмена: семестр в Берлинском ТУ. Дедлайн 20 апреля",
    cover_url: "https://picsum.photos/seed/exchange/400/700",
    cta_url: null,
    published_at: new Date().toISOString(),
    expires_at: new Date(Date.now() + 25 * 86400000).toISOString(),
    is_active: true,
    created_by: null,
    created_at: new Date().toISOString(),
    cover_url_optimized: null,
  },
  {
    id: "mock-9",
    title: "Научная конференция",
    short_text: "Весенняя конференция молодых учёных — приём тезисов открыт",
    cover_url: "https://picsum.photos/seed/science/400/700",
    cta_url: null,
    published_at: new Date().toISOString(),
    expires_at: new Date(Date.now() + 15 * 86400000).toISOString(),
    is_active: true,
    created_by: null,
    created_at: new Date().toISOString(),
    cover_url_optimized: null,
  },
]

/** Wave 46: Card-shaped skeleton placeholders for SkeletonMorph */
function ScheduleCardSkeleton() {
  return (
    <Card className="card-matte glass-noise p-6 md:p-7">
      <Skeleton width="60%" height="1.5rem" className="mb-5" />
      <div className="space-y-3">
        {[1, 2, 3].map((i) => (
          <div key={i} className="flex flex-col gap-2 rounded-xl bg-(--bg-matte-list) px-4 py-3">
            <div className="flex items-center gap-2">
              <Skeleton width="5rem" height="1.125rem" />
              <Skeleton width="7.5rem" height="1.25rem" />
            </div>
            <Skeleton width="60%" height="0.875rem" />
          </div>
        ))}
      </div>
    </Card>
  )
}

function NewsCardSkeleton() {
  return (
    <Card className="card-matte glass-noise p-6 md:p-7">
      <Skeleton width="50%" height="1.5rem" className="mb-5" />
      <div className="space-y-3">
        {[1, 2].map((i) => (
          <div key={i} className="flex items-start gap-4 rounded-xl bg-(--bg-matte-list) px-4 py-3">
            <Skeleton width="2.75rem" height="2.75rem" rounded="9999rem" className="shrink-0" />
            <div className="flex-1 space-y-2">
              <Skeleton width="90%" height="1rem" />
              <Skeleton width="70%" height="0.875rem" />
            </div>
          </div>
        ))}
      </div>
    </Card>
  )
}

function EventsCardSkeleton() {
  return (
    <Card className="card-matte glass-noise p-6 md:p-7">
      <Skeleton width="55%" height="1.5rem" className="mb-5" />
      <div className="mb-4 flex gap-2">
        <Skeleton width="4rem" height="2rem" rounded="0.75rem" />
        <Skeleton width="4rem" height="2rem" rounded="0.75rem" />
      </div>
      <div className="space-y-3">
        {[1, 2, 3].map((i) => (
          <div key={i} className="flex flex-col gap-2 rounded-xl bg-(--bg-matte-list) px-4 py-3">
            <Skeleton width="80%" height="1rem" />
            <div className="flex items-center gap-2">
              <Skeleton width="7.5rem" height="0.875rem" />
              <Skeleton width="5rem" height="0.875rem" />
            </div>
          </div>
        ))}
      </div>
    </Card>
  )
}

// eslint-disable-next-line react-compiler/react-compiler
export default function Dashboard() {
  "use no memo" // Wave 48: opt out of React Compiler — Framer Motion useScroll reads refs during render
  const { t } = useTranslation(["dashboard", "common"])
  const { user, loading: authLoading } = useAuth()
  const isNarrow = useMediaQuery(`(max-width: ${breakpoints.dashboard})`)
  const prefersReducedMotion = useMediaQuery("(prefers-reduced-motion: reduce)")
  const { language } = useLanguage()
  const locale = getLocaleForLanguage(language)
  const { hh, mm, dateStr, time } = useClock(locale)

  // Wave 46: Parallax — backdrop scrolls slower than content
  const parallaxRef = useRef<HTMLDivElement>(null)
  const { scrollYProgress } = useScroll({
    target: parallaxRef,
    offset: ["start start", "end start"],
  })
  const backdropY = useTransform(scrollYProgress, [0, 1], ["0%", "15%"])

  // Wave 47: Weather-aware ambient particles
  const weatherResult = useWeather()
  const weatherAnimation = weatherResult.data?.animation ?? "none"

  // Wave 48: Card reveal cascade — first load per session
  const [showCascade, setShowCascade] = useState(() => {
    if (typeof sessionStorage === "undefined") return false
    return !sessionStorage.getItem(CASCADE_KEY)
  })
  useEffect(() => {
    if (showCascade && typeof sessionStorage !== "undefined") {
      sessionStorage.setItem(CASCADE_KEY, "1")
      // Disable cascade flag after all 3 cards finish (last delay 0.3s + duration 0.5s = 0.8s)
      const timer = setTimeout(() => setShowCascade(false), 1000)
      return () => clearTimeout(timer)
    }
  }, [showCascade])

  // Wave 48: Scroll depth — cards recede as they scroll above viewport
  const cardGridRef = useRef<HTMLDivElement>(null)
  const { scrollYProgress: gridScrollProgress } = useScroll({
    target: cardGridRef,
    offset: ["start start", "end start"],
  })
  const depthScale = useTransform(gridScrollProgress, [0, 0.3, 1], [1, 1, 0.96])
  const depthOpacity = useTransform(gridScrollProgress, [0, 0.3, 1], [1, 1, 0.7])

  // Wave 46: 3D tilt on dashboard cards
  const tiltSchedule = useTilt({ max: 5, disabled: prefersReducedMotion || isNarrow })
  const tiltNews = useTilt({ max: 5, disabled: prefersReducedMotion || isNarrow })
  const tiltEvents = useTilt({ max: 5, disabled: prefersReducedMotion || isNarrow })

  const queryClient = useQueryClient()

  // Wave 46: SkeletonMorph — shared query instances for loading state
  // React Query deduplicates, so no extra network requests
  const scheduleQuery = useDashboardSchedule(
    (user?.role as "student" | "teacher" | "admin" | null) ?? null,
    user?.group_id ?? null
  )
  const newsQuery = useDashboardNews(language)
  const eventsQuery = useDashboardEvents()
  const scheduleLoaded = !scheduleQuery.isLoading
  const newsLoaded = !newsQuery.isLoading
  const eventsLoaded = !eventsQuery.isLoading

  const dashboardStoriesQuery = useDashboardStories()
  const realStories = dashboardStoriesQuery.data ?? []
  // Wave 49: fallback to mock stories in dev when API returns empty
  const stories: StoryItem[] = realStories.length > 0 ? realStories : MOCK_STORIES
  const loadingStories = dashboardStoriesQuery.isLoading && realStories.length === 0

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

      {/* Aurora wrapper — parallax via Framer Motion useScroll (Wave 46) */}
      <div ref={parallaxRef} className="aurora-mesh relative w-full">
        <motion.div
          style={prefersReducedMotion ? undefined : { y: backdropY }}
          className="absolute inset-0 pointer-events-none"
          aria-hidden="true"
        >
          <DashboardBackdrop isNarrow={isNarrow} prefersReducedMotion={prefersReducedMotion} />
          {/* Wave 47: Weather-aware ambient particles */}
          <WeatherAmbient animation={weatherAnimation} disabled={prefersReducedMotion} />
        </motion.div>

        {/* Hero — greeting card + stories in right slot */}
        <DashboardHero
          user={user}
          time={time}
          hh={hh}
          mm={mm}
          dateStr={dateStr}
          isNarrow={isNarrow}
          prefersReducedMotion={prefersReducedMotion}
          rightSlot={
            <DashboardStories
              stories={stories}
              loading={loadingStories}
              onPrefetch={prefetchStories}
              onStoryOpen={handleStoryOpen}
              maxVisibleStories={9}
            />
          }
        />

        {/* Content: cards */}
        <div className="relative z-base px-4 sm:px-6 md:px-10 lg:px-14">
          {/* Wave 49: stories on mobile — hidden on sm+ (shown in Hero rightSlot) */}
          <div className="sm:hidden">
            <DashboardStories
              stories={stories}
              loading={loadingStories}
              onPrefetch={prefetchStories}
              onStoryOpen={handleStoryOpen}
            />
          </div>

          {/* Wave 48: scroll depth wrapper — cards recede on scroll */}
          <motion.div
            ref={cardGridRef}
            className="mt-4 grid w-full grid-cols-12 gap-3 md:mt-5 md:gap-3.5 lg:gap-4 pb-10"
            style={prefersReducedMotion ? undefined : { scale: depthScale, opacity: depthOpacity }}
          >
            {/* Schedule card */}
            <motion.div
              className="col-span-12 lg:col-span-4"
              {...(showCascade && !prefersReducedMotion ? {
                initial: { opacity: 0, scale: 0.92, filter: "blur(8px)" },
                animate: { opacity: 1, scale: 1, filter: "blur(0px)" },
                transition: { duration: 0.5, delay: 0.1, ease: [0.16, 1, 0.3, 1] },
              } : {})}
            >
              <div
                ref={tiltSchedule.ref}
                style={tiltSchedule.style}
                className="dash-tilt-card vt-dash-schedule"
                onMouseMove={tiltSchedule.onMouseMove}
                onMouseLeave={tiltSchedule.onMouseLeave}
              >
                <SkeletonMorph loaded={scheduleLoaded} skeleton={<ScheduleCardSkeleton />}>
                  <ScheduleCard userRole={user?.role} userGroupId={user?.group_id} time={time} />
                </SkeletonMorph>
              </div>
            </motion.div>

            {/* News card */}
            <motion.div
              className="col-span-12 lg:col-span-4"
              {...(showCascade && !prefersReducedMotion ? {
                initial: { opacity: 0, scale: 0.92, filter: "blur(8px)" },
                animate: { opacity: 1, scale: 1, filter: "blur(0px)" },
                transition: { duration: 0.5, delay: 0.2, ease: [0.16, 1, 0.3, 1] },
              } : {})}
            >
              <div
                ref={tiltNews.ref}
                style={tiltNews.style}
                className="dash-tilt-card vt-dash-news"
                onMouseMove={tiltNews.onMouseMove}
                onMouseLeave={tiltNews.onMouseLeave}
              >
                <SkeletonMorph loaded={newsLoaded} skeleton={<NewsCardSkeleton />}>
                  <NewsCard locale={locale} />
                </SkeletonMorph>
              </div>
            </motion.div>

            {/* Events card */}
            <motion.div
              className="col-span-12 lg:col-span-4"
              {...(showCascade && !prefersReducedMotion ? {
                initial: { opacity: 0, scale: 0.92, filter: "blur(8px)" },
                animate: { opacity: 1, scale: 1, filter: "blur(0px)" },
                transition: { duration: 0.5, delay: 0.3, ease: [0.16, 1, 0.3, 1] },
              } : {})}
            >
              <div
                ref={tiltEvents.ref}
                style={tiltEvents.style}
                className="dash-tilt-card vt-dash-events"
                onMouseMove={tiltEvents.onMouseMove}
                onMouseLeave={tiltEvents.onMouseLeave}
              >
                <SkeletonMorph loaded={eventsLoaded} skeleton={<EventsCardSkeleton />}>
                  <EventsCard />
                </SkeletonMorph>
              </div>
            </motion.div>
          </motion.div>
        </div>
      </div>
    </PageLayout>
  )
}
