import { useState, useCallback, useEffect, useMemo, useRef } from "react"
import { useQueryClient } from "@tanstack/react-query"
import { useAuth } from "@/contexts/AuthContext"
import { useLanguage } from "@/contexts/LanguageContext"
import { useOnlineStatus } from "@/hooks/useOnlineStatus"
import { useDebounced } from "@/hooks/useDebounced"
import { useStableListHeight } from "@/hooks/ui/useStableListHeight"
import { useSearch, useNavigate } from "@tanstack/react-router"
import {
  EVENTS_PAGE_SIZE,
  useEventsListQuery,
  useMyEventsQuery,
  type EventsListOrder,
} from "@/api/hooks/events"
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
import { useCampusTimezone } from "@/contexts/CampusTimezoneContext"
import { getCampusDateKey, getCampusDateRangeKeys } from "@/utils/campusTimezone"
import { useMinuteClock } from "@/hooks/useMinuteClock"

export const EventsFeature = () => {
  const { user } = useAuth()
  const { language } = useLanguage()
  const queryClient = useQueryClient()
  const isOnline = useOnlineStatus()
  const campusTimezone = useCampusTimezone()
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

  const setTab = useCallback(
    (v: EventTabKey) => handleURLChange("tab", v === "active" ? "" : v),
    [handleURLChange]
  )
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
    const order: EventsListOrder | undefined =
      sortMode === "newest"
        ? "starts_at_desc"
        : sortMode === "upcoming"
          ? "starts_at_asc"
          : undefined

    return {
      language,
      is_active: isActiveFilter,
      search: debouncedSearch,
      location: debouncedLocation,
      limit: EVENTS_PAGE_SIZE,
      ...(order ? { order } : {}),
    }
  }, [tab, language, debouncedSearch, debouncedLocation, sortMode])

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
    isError: eventsListError,
  } = eventsListQuery

  const {
    data: myEventsData,
    isLoading: myEventsLoading,
    isFetching: myEventsFetching,
    isError: myEventsError,
  } = myEventsQuery

  const queryError = tab === "my" ? myEventsError : eventsListError

  const rawEvents = useMemo(() => {
    return tab === "my" ? (myEventsData ?? []) : rawEventsList
  }, [tab, rawEventsList, myEventsData])

  const isInitialLoading = tab === "my" ? myEventsLoading : listIsLoading
  const isFetching = tab === "my" ? myEventsFetching : listIsFetching

  /* ── Client-side filter + sort ── */
  // Date range and "upcoming" depend on the current time; the minute tick keeps them current.
  const clock = useMinuteClock()
  const filteredEvents = useMemo(() => {
    let list = rawEvents

    // Category filter (client-side within fetched data)
    if (activeCategory !== "all") {
      list = list.filter(
        (e) => inferEventCategory(e.event_type ?? e.event_type_en) === activeCategory
      )
    }

    // Date range filter (client-side)
    const bounds = getCampusDateRangeKeys(dateRange, new Date(clock), campusTimezone)
    const isSupportedDateRange =
      dateRange === "today" || dateRange === "week" || dateRange === "month"
    if (isSupportedDateRange && !bounds) {
      list = []
    } else if (bounds) {
      const [rangeStart, rangeEnd] = bounds
      list = list.filter((e) => {
        if (!e.starts_at) return false
        const eventDay = getCampusDateKey(e.starts_at, campusTimezone)
        return eventDay !== null && eventDay >= rangeStart && eventDay < rangeEnd
      })
    }

    // Sort
    if (sortMode === "newest" && tab === "my") {
      // The legacy My endpoint returns its complete array in ASC batch order.
      // Sort a copy here without changing that API or main-feed pagination.
      list = [...list].sort(
        (a, b) => Date.parse(b.starts_at) - Date.parse(a.starts_at) || b.id.localeCompare(a.id)
      )
    } else if (sortMode === "popular") {
      list = [...list].sort((a, b) => (b.participant_count ?? 0) - (a.participant_count ?? 0))
    } else if (sortMode === "upcoming") {
      list = [...list]
        .filter((e) => e.starts_at && new Date(e.starts_at).getTime() > clock)
        .sort((a, b) => new Date(a.starts_at!).getTime() - new Date(b.starts_at!).getTime())
    }

    return list
  }, [rawEvents, activeCategory, dateRange, sortMode, tab, campusTimezone, clock])

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

  // A narrower filter first shows only the loaded matches (or nothing while a
  // refetch runs); hold the list's height until it settles so the page cannot
  // jump up.
  const listContainerRef = useRef<HTMLDivElement>(null)
  const listMinHeight = useStableListHeight(
    listContainerRef,
    `${tab}|${activeCategory}|${dateRange}|${sortMode}`,
    isFetching || (requiresCompleteDataset && Boolean(hasNextPage))
  )

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

        <div ref={listContainerRef} style={{ minHeight: listMinHeight }}>
          <EventsList
            eventsList={filteredEvents}
            isInitialLoading={isInitialLoading}
            queryError={queryError}
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
        </div>

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
