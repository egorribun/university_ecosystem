import { PageLayout } from "@/components/layout/PageLayout"
import { logError } from "@/app/logger"
import EventCard from "@/components/events/EventCard/EventCard"
import { useState, useCallback, useMemo, useRef } from "react"
import { useQueryClient } from "@tanstack/react-query"
import { createEvent } from "@/api/events"
import { Calendar as EventNoteIcon } from "lucide-react"
import { useAuth } from "@/contexts/AuthContext"
import { useSearch, useNavigate } from "@tanstack/react-router"
import { useTranslation } from "react-i18next"
import { EVENTS_PAGE_SIZE, useEventsListQuery, useMyEventsQuery } from "@/api/hooks/events"
import { Button } from "@/components/ui"
import { motion } from "framer-motion"
import { springSoft } from "@/utils/animations"
import { cn } from "@/utils/cn"
import useMediaQuery from "@/hooks/useMediaQuery"
import { breakpoints } from "@/theme/tokens"
import { useDebounced } from "@/hooks/useDebounced"
import FadeSection from "@/components/motion/FadeSection"
import { EventCreateDialog } from "@/components/events/EventCreateDialog"
import { EventSearchBar } from "@/components/events/EventSearchBar"
import { EventsEmptyState } from "@/components/events/EventsEmptyState"
import { EventCardSkeleton } from "@/components/events/EventCard/EventCardSkeleton"

type EventTabKey = "active" | "archive" | "my"
type EventTab = { key: EventTabKey; is_active?: boolean }

const tabs = [
  { key: "active", is_active: true },
  { key: "archive", is_active: false },
  { key: "my" },
] as const satisfies readonly EventTab[]

const ANIMATION_DELAYS = {
  header: "80ms",
  createButton: "140ms",
  tabs: "200ms",
  search: "240ms",
  grid: "260ms",
}

// PERF-23-04: use "search" strategy (200ms) for snappier search-as-you-type
const DEBOUNCE_STRATEGY = "search" as const

const Events = () => {
  const { user } = useAuth()
  const searchParams = useSearch({ strict: false }) as Record<string, string | undefined>
  const navigate = useNavigate()
  const { t, i18n } = useTranslation(["events", "common"])
  const language = i18n.language?.startsWith("en") ? "en" : "ru"

  const queryClient = useQueryClient()
  const [createOpen, setCreateOpen] = useState(false)
  const isMobile = useMediaQuery(`(max-width: ${breakpoints.content})`)

  // Sync state variables directly from the URL params to prevent stale closures
  const tab = (searchParams.tab as EventTabKey) || "active"
  const search = searchParams.q || ""
  const type = searchParams.type || ""
  const location = searchParams.loc || ""

  const handleURLChange = useCallback(
    (key: string, value: string) => {
      void navigate({
        to: ".",
        search: (prev: Record<string, unknown>) => {
          const next = { ...prev }
          if (value) {
            next[key] = value
          } else {
            delete next[key]
          }
          return next
        },
        replace: true,
      })
    },
    [navigate]
  )

  const setTab = useCallback((val: string) => handleURLChange("tab", val), [handleURLChange])
  const setSearch = useCallback((val: string) => handleURLChange("q", val), [handleURLChange])
  const setType = useCallback((val: string) => handleURLChange("type", val), [handleURLChange])
  const setLocation = useCallback((val: string) => handleURLChange("loc", val), [handleURLChange])

  // Tab indicator animation
  const tabContainerRef = useRef<HTMLDivElement>(null)

  const dSearch = useDebounced(search, DEBOUNCE_STRATEGY)
  const dType = useDebounced(type, DEBOUNCE_STRATEGY)
  const dLocation = useDebounced(location, DEBOUNCE_STRATEGY)

  const eventsListFilters = useMemo(() => {
    const isActiveFilter = tab === "active" ? true : tab === "archive" ? false : null
    return {
      language,
      is_active: isActiveFilter,
      search: dSearch,
      type: dType,
      location: dLocation,
      limit: EVENTS_PAGE_SIZE,
    }
  }, [tab, language, dSearch, dType, dLocation])

  const eventsListQuery = useEventsListQuery(eventsListFilters, {
    enabled: tab !== "my",
  })

  const myEventsQuery = useMyEventsQuery(
    { language, userId: user?.id ?? null },
    { enabled: tab === "my" }
  )

  const {
    events: listEvents,
    isLoading: listIsLoading,
    isFetching: listIsFetching,
    isFetchingNextPage: listIsFetchingNextPage,
    hasNextPage: listHasNextPage,
    fetchNextPage: fetchNextEventsPage,
    refetch: refetchEventsList,
  } = eventsListQuery

  const {
    data: myEventsData,
    isLoading: myEventsLoading,
    isFetching: myEventsFetching,
    refetch: refetchMyEvents,
  } = myEventsQuery

  const normalizedEvents = useMemo(() => {
    return tab === "my" ? (myEventsData ?? []) : listEvents
  }, [tab, listEvents, myEventsData])

  const loading = useMemo(() => {
    if (tab === "my") {
      return myEventsLoading || (myEventsFetching && !myEventsLoading)
    }
    return listIsLoading || (listIsFetching && !listIsFetchingNextPage)
  }, [
    tab,
    myEventsLoading,
    myEventsFetching,
    listIsLoading,
    listIsFetching,
    listIsFetchingNextPage,
  ])

  const loadingMore = tab !== "my" && Boolean(listIsFetchingNextPage)
  const hasMore = tab !== "my" && Boolean(listHasNextPage)

  const loadMore = useCallback(async () => {
    if (tab !== "my" && listHasNextPage) {
      await fetchNextEventsPage()
    }
  }, [fetchNextEventsPage, listHasNextPage, tab])

  const handleTabChange = (newValue: EventTabKey) => setTab(newValue)

  const handleCreateEvent = async (draft: Parameters<typeof createEvent>[0]) => {
    try {
      await createEvent(draft)
      setCreateOpen(false)
      setTab("active")
      void queryClient.invalidateQueries({ queryKey: ["events"] })
      window.scrollTo({ top: 0, behavior: "smooth" })
    } catch (error) {
      logError("[Events] Failed to create event:", error)
    }
  }

  const handleRefresh = useCallback(() => {
    if (tab === "my") {
      void refetchMyEvents()
    } else {
      void refetchEventsList()
    }
  }, [refetchEventsList, refetchMyEvents, tab])

  const skeletonCount = isMobile ? 3 : 6

  return (
    <PageLayout
      seo={{
        title: t("events:pageTitle"),
        description: t("events:pageDescription", "Upcoming events, lectures, and activities."),
      }}
    >
      {/* Header */}
      <header>
        <FadeSection
          delay={ANIMATION_DELAYS.header}
          className="mb-8 flex flex-wrap items-center gap-4 sm:gap-5"
        >
          <div className="flex h-12 w-12 items-center justify-center rounded-full bg-(--bg-surface)/(--opacity-medium) border border-glass-border text-brand shadow-glass transition-transform duration-base hover:scale-[1.08] overflow-hidden">
            <EventNoteIcon className="h-7 w-7" />
          </div>
          <h1 className="text-(--fs-page-title) font-bold tracking-tight">
            {t("events:pageTitle")}
          </h1>
        </FadeSection>

        {/* Create button */}
        {(user?.role === "admin" || user?.role === "teacher") && (
          <FadeSection delay={ANIMATION_DELAYS.createButton} className="mb-6 flex justify-start">
            <Button
              id="create-event-btn"
              size="lg"
              onClick={() => setCreateOpen(true)}
              disabled={loading}
              className="px-6 text-fluid-title-sm"
            >
              {t("events:actions.openCreate")}
            </Button>
          </FadeSection>
        )}
      </header>

      {/* Tabs */}
      <FadeSection
        delay={ANIMATION_DELAYS.tabs}
        className="w-full max-w-[28rem] z-content"
        role="tablist"
      >
        <div
          ref={tabContainerRef}
          className={cn(
            "inline-flex w-full items-center gap-1 rounded-xl border border-glass-border bg-(--bg-surface)/(--opacity-medium) p-1 backdrop-blur-md shadow-glass",
            "sm:w-auto"
          )}
        >
          {tabs.map((tabItem) => (
            <button
              key={tabItem.key}
              id={`events-tab-${tabItem.key}`}
              type="button"
              role="tab"
              aria-selected={tab === tabItem.key}
              aria-controls={`events-tabpanel-${tabItem.key}`}
              onClick={() => handleTabChange(tabItem.key)}
              className={cn(
                "relative z-base px-4 py-2 text-body-sm font-semibold rounded-lg transition-colors duration-fast",
                "sm:px-6 sm:text-base",
                tab === tabItem.key
                  ? "text-text-primary"
                  : "text-(--text-secondary) hover:text-text-primary"
              )}
            >
              {tab === tabItem.key && (
                <motion.div
                  layoutId="active-tab-indicator"
                  className="absolute inset-0 bg-(--bg-surface) shadow-sm rounded-[inherit] z-negative"
                  transition={springSoft}
                />
              )}
              <span className="relative z-base">{t(`events:tabs.${tabItem.key}`)}</span>
            </button>
          ))}
        </div>
      </FadeSection>

      {/* Search + filter popover */}
      <FadeSection delay={ANIMATION_DELAYS.search} className="mb-6 lg:max-w-4xl">
        <EventSearchBar
          search={search}
          onSearchChange={setSearch}
          type={type}
          onTypeChange={setType}
          location={location}
          onLocationChange={setLocation}
        />
      </FadeSection>

      {/* Events grid */}
      <section aria-label={t("events:pageTitle")}>
        <FadeSection
          delay={ANIMATION_DELAYS.grid}
          role="tabpanel"
          id={`events-tabpanel-${tab}`}
          aria-labelledby={`events-tab-${tab}`}
          className="grid gap-5 sm:gap-6 pb-6 grid-cols-1 md:grid-cols-2 xl:grid-cols-3"
        >
          {loading &&
            Array.from({ length: skeletonCount }).map((_, i) => (
              <EventCardSkeleton key={`event-skel-${i}`} />
            ))}

          {!loading &&
            normalizedEvents.map((event, index) => (
              <EventCard
                key={event.id}
                {...event}
                onChange={handleRefresh}
                maxWidth="100%"
                animationIndex={index}
              />
            ))}

          {!loading && normalizedEvents.length === 0 && (
            <EventsEmptyState tab={tab} onTabChange={handleTabChange} />
          )}
        </FadeSection>
      </section>

      {/* Load more */}
      {hasMore && (
        <div className="mb-8 flex justify-center">
          <Button
            variant="outline"
            size="lg"
            onClick={loadMore}
            disabled={loadingMore}
            className="px-6"
          >
            {loadingMore
              ? t("common:statuses.loading")
              : t("common:buttons.loadMore", { defaultValue: "Load more" })}
          </Button>
        </div>
      )}

      {/* Create dialog */}
      <EventCreateDialog
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onCreated={handleCreateEvent}
        language={language as "ru" | "en"}
      />
    </PageLayout>
  )
}

export default Events
