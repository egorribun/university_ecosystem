import { PageLayout } from "@/components/PageLayout"
import EventCard from "@/components/EventCard"
import { useEffect, useState, useCallback, useMemo, useRef } from "react"
import { useQueryClient } from "@tanstack/react-query"
import { createEvent } from "@/api/events"
import { Calendar as EventNoteIcon } from "lucide-react"
import { useAuth } from "@/contexts/AuthContext"
import { useSearchParams } from "react-router-dom"
import { useTranslation } from "react-i18next"
import { EVENTS_PAGE_SIZE, useEventsListQuery, useMyEventsQuery } from "@/api/hooks/events"
import { Button, Skeleton } from "@/components/ui"
import { motion } from "framer-motion"
import { springSoft } from "@/utils/animations"
import { cn } from "@/utils/cn"
import useMediaQuery from "@/hooks/useMediaQuery"
import { breakpoints } from "@/theme/tokens"
import { useDebounced } from "@/hooks/useDebounced"
import FadeSection from "@/components/FadeSection"
import { EventCreateDialog } from "@/components/events/EventCreateDialog"
import { EventSearchBar } from "@/components/events/EventSearchBar"
import { EventsEmptyState } from "@/components/events/EventsEmptyState"

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

const DEBOUNCE_MS = 350

const SKELETON_HEIGHTS = {
  mobile: 180,
  desktop: 200,
  title: 28,
  meta: 20,
  avatar: 36,
}

const Events = () => {
  const { user } = useAuth()
  const [searchParams, setSearchParams] = useSearchParams()
  const { t, i18n } = useTranslation(["events", "common"])
  const language = i18n.language?.startsWith("en") ? "en" : "ru"

  const queryClient = useQueryClient()
  const [tab, setTab] = useState<EventTabKey>("active")
  const [search, setSearch] = useState("")
  const [type, setType] = useState("")
  const [location, setLocation] = useState("")

  const [createOpen, setCreateOpen] = useState(false)

  const isMobile = useMediaQuery(`(max-width: ${breakpoints.content})`)

  // Tab indicator animation
  const tabContainerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const t = (searchParams.get("tab") as typeof tab) || "active"
    const s = searchParams.get("q") || ""
    const ty = searchParams.get("type") || ""
    const loc = searchParams.get("loc") || ""
    setTab(t)
    setSearch(s)
    setType(ty)
    setLocation(loc)
  }, [])

  useEffect(() => {
    const next = new URLSearchParams(searchParams)
    next.set("tab", tab)
    next.set("q", search)
    next.set("type", type)
    next.set("loc", location)
    setSearchParams(next, { replace: true })
  }, [tab, search, type, location, searchParams, setSearchParams])

  const dSearch = useDebounced(search, DEBOUNCE_MS)
  const dType = useDebounced(type, DEBOUNCE_MS)
  const dLocation = useDebounced(location, DEBOUNCE_MS)

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
      console.error("[Events] Failed to create event:", error)
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
        className="w-full max-w-md z-content"
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
              <div key={`event-skel-${i}`} className="w-full">
                <div className="w-full space-y-4 rounded-lg border border-glass-border bg-(--bg-surface)/(--opacity-medium) p-5 shadow-glass backdrop-blur-md">
                  <Skeleton
                    height={isMobile ? SKELETON_HEIGHTS.mobile : SKELETON_HEIGHTS.desktop}
                    className="rounded-md"
                  />
                  <Skeleton height={SKELETON_HEIGHTS.title} className="rounded-lg" />
                  <Skeleton height={SKELETON_HEIGHTS.meta} width="75%" className="rounded-lg" />
                  <div className="flex gap-3 pt-2">
                    <Skeleton height={SKELETON_HEIGHTS.avatar} width={120} className="rounded-sm" />
                    <Skeleton height={SKELETON_HEIGHTS.avatar} width={100} className="rounded-sm" />
                  </div>
                </div>
              </div>
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
