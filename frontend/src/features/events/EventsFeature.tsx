import { useState, useCallback, useEffect, useMemo } from "react"
import { useQueryClient } from "@tanstack/react-query"
import { useAuth } from "@/contexts/AuthContext"
import { useLanguage } from "@/contexts/LanguageContext"
import { useOnlineStatus } from "@/hooks/useOnlineStatus"
import { useDebounced } from "@/hooks/useDebounced"
import { useSearch, useNavigate } from "@tanstack/react-router"
import { EVENTS_PAGE_SIZE, useEventsListQuery, useMyEventsQuery } from "@/api/hooks/events"
import { resetEtagCache } from "@/api/client"
import { EventsHeader } from "./components/EventsHeader"
import { EventsList } from "./components/EventsList"
import { EventFormDialog } from "./components/EventFormDialog"
import { EventsShortcutsOverlay } from "./components/EventsShortcutsOverlay"
import { EventsBackdrop } from "@/components/events/EventsBackdrop"
import { inferEventCategory, type EventCategory } from "./categories"
import { useEventsKeyboardNav } from "@/hooks/useEventsKeyboardNav"
import useMediaQuery from "@/hooks/useMediaQuery"
import { breakpoints } from "@/theme/tokens"
import type { EventDateRange, EventSortMode, EventTabKey } from "./types"

/**
 * Returns [start, end) of date range in UTC milliseconds.
 * "today" = start of today → end of today
 * "week"  = start of Monday → end of Sunday
 * "month" = start of 1st → end of last day
 */
function getDateRangeBounds(range: EventDateRange): [number, number] | null {
  if (!range) return null

  const now = new Date()
  const y = now.getFullYear()
  const m = now.getMonth()
  const d = now.getDate()

  if (range === "today") {
    const start = new Date(y, m, d).getTime()
    const end = new Date(y, m, d + 1).getTime()
    return [start, end]
  }

  if (range === "week") {
    const dayOfWeek = now.getDay()
    // Monday = 1, Sunday = 0 → shift to Monday-based
    const mondayOffset = dayOfWeek === 0 ? -6 : 1 - dayOfWeek
    const start = new Date(y, m, d + mondayOffset).getTime()
    const end = new Date(y, m, d + mondayOffset + 7).getTime()
    return [start, end]
  }

  if (range === "month") {
    const start = new Date(y, m, 1).getTime()
    const end = new Date(y, m + 1, 1).getTime()
    return [start, end]
  }

  return null
}

export const EventsFeature = () => {
  const { user } = useAuth()
  const { language } = useLanguage()
  const queryClient = useQueryClient()
  const isOnline = useOnlineStatus()
  const prefersReducedMotion = useMediaQuery("(prefers-reduced-motion: reduce)")
  const isNarrow = useMediaQuery(`(max-width: ${breakpoints.content})`)

  /* ── URL-synced state ── */
  const searchParams = useSearch({ strict: false }) as Record<string, string | undefined>
  const navigate = useNavigate()

  const tab = (searchParams.tab as EventTabKey) || "active"
  const searchQuery = searchParams.q || ""
  const locationFilter = searchParams.loc || ""
  const sortMode = (searchParams.sort as EventSortMode) || "newest"
  const activeCategory = (searchParams.cat as EventCategory | "all") || "all"
  const dateRange = (searchParams.dr as EventDateRange) || ""

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
        resetScroll: false,
        viewTransition: false,
      })
    },
    [navigate]
  )

  const setTab = useCallback((v: string) => handleURLChange("tab", v), [handleURLChange])
  const setSearchQuery = useCallback((v: string) => handleURLChange("q", v), [handleURLChange])
  const setSortMode = useCallback(
    (v: EventSortMode) => handleURLChange("sort", v === "newest" ? "" : v),
    [handleURLChange]
  )
  const setActiveCategory = useCallback(
    (v: EventCategory | "all") => handleURLChange("cat", v === "all" ? "" : v),
    [handleURLChange]
  )
  const setDateRange = useCallback(
    (v: EventDateRange) => handleURLChange("dr", v),
    [handleURLChange]
  )

  const debouncedSearch = useDebounced(searchQuery, "search")
  const debouncedLocation = useDebounced(locationFilter, "search")

  /* ── Create dialog ── */
  const [createOpen, setCreateOpen] = useState(false)

  /* ── Data fetching ── */
  const eventsListFilters = useMemo(() => {
    const isActiveFilter = tab === "active" ? true : tab === "archive" ? false : null
    return {
      language,
      is_active: isActiveFilter,
      search: debouncedSearch,
      location: debouncedLocation,
      limit: EVENTS_PAGE_SIZE,
    }
  }, [tab, language, debouncedSearch, debouncedLocation])

  const eventsListQuery = useEventsListQuery(eventsListFilters, {
    enabled: tab !== "my",
  })

  const myEventsQuery = useMyEventsQuery(
    { language, userId: user?.id ?? null },
    { enabled: tab === "my" }
  )

  const {
    events: rawEventsList,
    isLoading: listIsLoading,
    isFetching: listIsFetching,
    isFetchingNextPage,
    hasNextPage,
    fetchNextPage,
  } = eventsListQuery

  const {
    data: myEventsData,
    isLoading: myEventsLoading,
    isFetching: myEventsFetching,
  } = myEventsQuery

  const rawEvents = useMemo(() => {
    return tab === "my" ? (myEventsData ?? []) : rawEventsList
  }, [tab, rawEventsList, myEventsData])

  const isInitialLoading = tab === "my" ? myEventsLoading : listIsLoading
  const isFetching = tab === "my" ? myEventsFetching : listIsFetching

  /* ── Client-side filter + sort ── */
  const filteredEvents = useMemo(() => {
    let list = rawEvents

    // Category filter (client-side within fetched data)
    if (activeCategory !== "all") {
      list = list.filter(
        (e) => inferEventCategory(e.event_type ?? e.event_type_en) === activeCategory
      )
    }

    // Date range filter (client-side)
    const bounds = getDateRangeBounds(dateRange)
    if (bounds) {
      const [rangeStart, rangeEnd] = bounds
      list = list.filter((e) => {
        if (!e.starts_at) return false
        const ts = new Date(e.starts_at).getTime()
        return ts >= rangeStart && ts < rangeEnd
      })
    }

    // Sort
    if (sortMode === "popular") {
      list = [...list].sort((a, b) => (b.participant_count ?? 0) - (a.participant_count ?? 0))
    } else if (sortMode === "upcoming") {
      const now = Date.now()
      list = [...list]
        .filter((e) => e.starts_at && new Date(e.starts_at).getTime() > now)
        .sort((a, b) => new Date(a.starts_at!).getTime() - new Date(b.starts_at!).getTime())
    }

    return list
  }, [rawEvents, activeCategory, dateRange, sortMode])

  const requiresCompleteDataset =
    tab !== "my" && (activeCategory !== "all" || Boolean(dateRange) || sortMode !== "newest")
  useEffect(() => {
    if (
      requiresCompleteDataset &&
      hasNextPage &&
      !listIsLoading &&
      !isFetchingNextPage &&
      isOnline
    ) {
      void fetchNextPage()
    }
  }, [
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
    isOnline,
    listIsLoading,
    requiresCompleteDataset,
  ])

  /* ── Keyboard navigation ── */
  const { activeIndex, registerRef } = useEventsKeyboardNav(filteredEvents)

  const refreshEvents = useCallback(() => {
    resetEtagCache()
    void queryClient.invalidateQueries({ queryKey: ["events"] })
  }, [queryClient])

  /* ── Derived flags ── */
  const canFetchMore = tab !== "my" && Boolean(hasNextPage)

  const isAdmin = user?.role === "admin" || user?.role === "teacher"

  return (
    <div className="events-theme aurora-mesh relative w-full text-text-primary py-6 sm:py-8 md:py-10 px-4 sm:px-6 md:px-10 lg:px-14 overflow-x-clip">
      <EventsBackdrop isNarrow={isNarrow} prefersReducedMotion={prefersReducedMotion} />
      <div className="relative z-[1]">
        <EventsHeader
          onAddClick={() => setCreateOpen(true)}
          isAdmin={isAdmin}
          eventsCount={filteredEvents.length}
          searchQuery={searchQuery}
          onSearchChange={setSearchQuery}
          activeCategory={activeCategory}
          onCategoryChange={setActiveCategory}
          sortMode={sortMode}
          onSortChange={setSortMode}
          tab={tab}
          onTabChange={setTab}
          dateRange={dateRange}
          onDateRangeChange={setDateRange}
          locationFilter={locationFilter}
          onLocationChange={(v: string) => handleURLChange("loc", v)}
        />

        <EventsList
          eventsList={filteredEvents}
          isInitialLoading={isInitialLoading}
          isFetching={isFetching}
          isFetchingNextPage={isFetchingNextPage}
          hasNextPage={canFetchMore}
          fetchNextPage={fetchNextPage}
          refreshEvents={refreshEvents}
          onAddClick={() => setCreateOpen(true)}
          isAdmin={isAdmin}
          isOnline={isOnline}
          tab={tab}
          onTabChange={setTab}
          activeKeyboardIndex={activeIndex}
          registerCardRef={registerRef}
        />

        <EventFormDialog
          open={createOpen}
          onClose={() => setCreateOpen(false)}
          onSuccess={refreshEvents}
          language={language as "ru" | "en"}
        />

        <EventsShortcutsOverlay />
      </div>
    </div>
  )
}
