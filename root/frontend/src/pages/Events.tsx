import Layout from "../components/Layout"
import PageFadeIn from "../components/PageFadeIn"
import EventCard from "../components/EventCard"
import { useEffect, useState, useCallback, useMemo, useRef, type CSSProperties } from "react"
import { useQueryClient } from "@tanstack/react-query"
import { useWindowVirtualizer } from "@tanstack/react-virtual"
import { createEvent, uploadEventImage } from "@/api/events"
import type { Event } from "@/types/Event"
import EventNoteIcon from "@mui/icons-material/EventNote"
import SearchIcon from "@mui/icons-material/Search"
import FilterListIcon from "@mui/icons-material/FilterList"
import ClearIcon from "@mui/icons-material/Clear"
import { useAuth } from "../contexts/AuthContext"
import SmartImage from "@/components/SmartImage"
import { useSearchParams } from "react-router-dom"
import { useTranslation } from "react-i18next"
import { EVENTS_PAGE_SIZE, useEventsListQuery, useMyEventsQuery } from "@/api/hooks/events"
import { Button, Skeleton } from "@/components/ui"
import Dialog from "@/components/Dialog"
import { cn } from "@/utils/cn"
import useMediaQuery from "@/hooks/useMediaQuery"

type EventTabKey = "active" | "archive" | "my"
type EventTab = { key: EventTabKey; is_active?: boolean }

const tabs = [
  { key: "active", is_active: true },
  { key: "archive", is_active: false },
  { key: "my" },
] as const satisfies readonly EventTab[]

type EventDraft = {
  title: string
  title_en: string
  description: string
  description_en: string
  event_type: string
  event_type_en: string
  location: string
  location_en: string
  starts_at: string
  ends_at: string
  speaker: string
  image_url: string
  about: string
  about_en: string
}

const initialEvent: EventDraft = {
  title: "",
  title_en: "",
  description: "",
  description_en: "",
  event_type: "",
  event_type_en: "",
  location: "",
  location_en: "",
  starts_at: "",
  ends_at: "",
  speaker: "",
  image_url: "",
  about: "",
  about_en: "",
}

function useDebounced<T>(value: T, delay = 350) {
  const [v, setV] = useState(value)
  useEffect(() => {
    const t = setTimeout(() => setV(value), delay)
    return () => clearTimeout(t)
  }, [value, delay])
  return v
}

const fadeDelayStyle = (value: string): CSSProperties =>
  ({ "--fade-delay": value }) as CSSProperties

const inputClass =
  "w-full rounded-ue-lg border border-[color:color-mix(in_srgb,white_12%,var(--nav-link)_88%)] bg-[color:color-mix(in_srgb,var(--card-bg)_96%,white_4%)] px-4 py-3 text-[0.98rem] font-medium text-[color:var(--page-text)] shadow-[inset_0_1px_2px_rgba(0,0,0,0.04)] transition-all duration-200 focus:border-[color:var(--nav-link)] focus:outline-none focus:shadow-[0_0_0_3px_color-mix(in_srgb,var(--nav-link)_15%,transparent)] placeholder:text-[color:color-mix(in_srgb,var(--placeholder-fg)_70%,transparent)]"

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
  const [eventData, setEventData] = useState<EventDraft>(initialEvent)
  const [imageUploading, setImageUploading] = useState(false)
  const [createPreview, setCreatePreview] = useState<string | null>(null)

  const isMobile = useMediaQuery("(max-width:900px)")

  const [filterAnchor, setFilterAnchor] = useState<HTMLElement | null>(null)
  const filtersOpen = Boolean(filterAnchor)
  const filtersActive = Boolean(type?.trim() || location?.trim())
  const filterPopoverRef = useRef<HTMLDivElement>(null)
  const listContainerRef = useRef<HTMLDivElement>(null)
  const [scrollMargin, setScrollMargin] = useState(0)

  useEffect(() => {
    if (!filtersOpen) return
    const handleClickOutside = (event: MouseEvent) => {
      if (
        filterPopoverRef.current &&
        !filterPopoverRef.current.contains(event.target as Node) &&
        filterAnchor &&
        !filterAnchor.contains(event.target as Node)
      ) {
        setFilterAnchor(null)
      }
    }
    document.addEventListener("mousedown", handleClickOutside)
    return () => document.removeEventListener("mousedown", handleClickOutside)
  }, [filtersOpen, filterAnchor])

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

  const dSearch = useDebounced(search, 350)
  const dType = useDebounced(type, 350)
  const dLocation = useDebounced(location, 350)

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

  const estimatedItemSize = isMobile ? 360 : 420
  const totalVirtualCount = normalizedEvents.length + (hasMore ? 1 : 0)

  const eventsVirtualizer = useWindowVirtualizer({
    count: totalVirtualCount,
    estimateSize: () => estimatedItemSize,
    overscan: 6,
    scrollMargin,
  })

  const virtualItems = eventsVirtualizer.getVirtualItems()

  useEffect(() => {
    const updateMargin = () => {
      if (!listContainerRef.current) return
      const rect = listContainerRef.current.getBoundingClientRect()
      setScrollMargin(rect.top + window.scrollY)
    }
    updateMargin()
    window.addEventListener("resize", updateMargin)
    return () => window.removeEventListener("resize", updateMargin)
  }, [])

  useEffect(() => {
    if (!listContainerRef.current) return
    const rect = listContainerRef.current.getBoundingClientRect()
    setScrollMargin(rect.top + window.scrollY)
  }, [tab, isMobile, loading])

  useEffect(() => {
    if (!totalVirtualCount) return
    eventsVirtualizer.scrollToOffset(0, { align: "start", behavior: "auto" })
    if (Number.isFinite(scrollMargin)) {
      window.scrollTo({ top: scrollMargin, behavior: "auto" })
    }
  }, [eventsVirtualizer, scrollMargin, tab, totalVirtualCount])

  useEffect(() => {
    if (tab === "my" || !hasMore || loadingMore || !virtualItems.length) {
      return
    }

    const lastItem = virtualItems[virtualItems.length - 1]
    if (!lastItem) {
      return
    }

    const isBeforeLoader = lastItem.index >= Math.max(0, normalizedEvents.length - 1)
    if (isBeforeLoader) {
      void fetchNextEventsPage()
    }
  }, [fetchNextEventsPage, hasMore, loadingMore, normalizedEvents.length, tab, virtualItems])

  const handleTabChange = (newValue: EventTabKey) => setTab(newValue)

  const handleImageUpload = async (file: File) => {
    setImageUploading(true)
    const localUrl = URL.createObjectURL(file)
    setCreatePreview((prev) => {
      if (prev) URL.revokeObjectURL(prev)
      return localUrl
    })
    try {
      const imageUrl = await uploadEventImage(file)
      setEventData((prev) => ({ ...prev, image_url: imageUrl }))
    } finally {
      setImageUploading(false)
    }
  }

  const getLocalizedDraftValue = (
    field: "title" | "description" | "event_type" | "location" | "about"
  ) => {
    const key = (language === "en" ? `${field}_en` : field) as keyof EventDraft
    return eventData[key]
  }

  const updateLocalizedDraftValue = (
    field: "title" | "description" | "event_type" | "location" | "about",
    value: string
  ) => {
    const key = (language === "en" ? `${field}_en` : field) as keyof EventDraft
    setEventData((prev) => ({ ...prev, [key]: value }))
  }

  const handleCreateEvent = async () => {
    const titleValue = normalizedTitle
    const locationValue = normalizedLocation
    try {
      const payload = {
        ...eventData,
        title: titleValue,
        location: locationValue,
        starts_at: eventData.starts_at,
        ends_at: eventData.ends_at,
      } satisfies Parameters<typeof createEvent>[0]
      await createEvent(payload)
      closeCreate()
      setTab("active")
      void queryClient.invalidateQueries({ queryKey: ["events"] })
      window.scrollTo({ top: 0, behavior: "smooth" })
    } catch {}
  }

  const handleRefresh = useCallback(() => {
    if (tab === "my") {
      void refetchMyEvents()
    } else {
      void refetchEventsList()
    }
  }, [refetchEventsList, refetchMyEvents, tab])

  const starts = new Date(eventData.starts_at).getTime()
  const ends = new Date(eventData.ends_at).getTime()
  const dateError = !!(eventData.starts_at && eventData.ends_at && ends < starts)
  const normalizedTitle = eventData.title.trim() || eventData.title_en.trim()
  const normalizedLocation = eventData.location.trim() || eventData.location_en.trim()

  const closeCreate = () => {
    setCreateOpen(false)
    setEventData(initialEvent)
    if (createPreview) URL.revokeObjectURL(createPreview)
    setCreatePreview(null)
  }

  useEffect(() => {
    return () => {
      if (createPreview) URL.revokeObjectURL(createPreview)
    }
  }, [createPreview])

  const skeletonCount = isMobile ? 3 : 6
  const virtualListMinHeight = isMobile ? 320 : 360
  const eventsListLabel = t("events:aria.listLabel", { defaultValue: "Events list" })
  const loadingMoreLabel = t("events:aria.loadingMore", { defaultValue: "Loading more events" })

  return (
    <Layout>
      <PageFadeIn>
        <div className="relative w-full min-h-screen bg-[color:var(--page-bg)] text-[color:var(--page-text)] px-4 py-6 sm:px-6 md:px-8 lg:px-12 overflow-hidden">
          {/* Background gradients */}
          <div className="pointer-events-none absolute inset-0 -z-10 opacity-60" aria-hidden="true">
            <div className="absolute -inset-[40%_-20%_10%_-20%] bg-[radial-gradient(60%_60%_at_80%_10%,rgba(0,118,255,0.22),transparent),radial-gradient(45%_45%_at_10%_80%,rgba(46,213,166,0.18),transparent)]" />
          </div>
          <div className="pointer-events-none absolute inset-0 -z-[1]" aria-hidden="true">
            <div className="absolute inset-0 bg-[linear-gradient(180deg,rgba(7,18,39,0.22)_0%,rgba(7,18,39,0)_45%),linear-gradient(140deg,rgba(255,255,255,0.04)_0%,rgba(255,255,255,0)_55%)]" />
          </div>

          {/* Header */}
          <div
            data-fade
            style={fadeDelayStyle("80ms")}
            className="mb-4 mt-4 flex flex-wrap items-center gap-3 text-[color:var(--nav-link)] sm:mb-6 sm:mt-6"
          >
            <span className="inline-flex h-11 w-11 items-center justify-center rounded-full bg-[color:var(--glass-bg)]/70 text-[color:var(--nav-link)] shadow-surface">
              <EventNoteIcon className="text-[1.85rem]" />
            </span>
            <h1 className="text-[clamp(1.6rem,5vw,2.75rem)] font-bold tracking-tight text-[color:var(--page-text)]">
              {t("events:pageTitle")}
            </h1>
          </div>

          {/* Create button */}
          {(user?.role === "admin" || user?.role === "teacher") && (
            <div data-fade className="mb-5 flex justify-start" style={fadeDelayStyle("140ms")}>
              <Button
                size="lg"
                onClick={() => setCreateOpen(true)}
                disabled={imageUploading || loading}
                className="px-6 text-[clamp(1rem,2.2vw,1.1rem)]"
              >
                {t("events:actions.openCreate")}
              </Button>
            </div>
          )}

          {/* Tabs */}
          <div
            data-fade
            style={fadeDelayStyle("200ms")}
            className="relative mb-4 min-h-[45px] rounded-ue-xl border border-[color:var(--glass-border)] bg-[linear-gradient(135deg,rgba(0,118,255,0.12),rgba(0,118,255,0))] px-3 py-2 shadow-[0_18px_45px_rgba(15,23,42,0.18)] backdrop-blur-[16px] sm:px-4 sm:py-2.5 lg:max-w-4xl"
            role="tablist"
          >
            <div className="flex flex-wrap items-center gap-2 sm:gap-4">
              {tabs.map((tabItem) => (
                <button
                  key={tabItem.key}
                  role="tab"
                  id={`events-tab-${tabItem.key}`}
                  aria-selected={tab === tabItem.key}
                  aria-controls={`events-tabpanel-${tabItem.key}`}
                  onClick={() => handleTabChange(tabItem.key)}
                  className={cn(
                    "relative px-4 py-2 text-base font-semibold transition-colors duration-200 rounded-ue-lg sm:px-6 sm:text-lg",
                    tab === tabItem.key
                      ? "text-[color:var(--nav-link)] font-bold"
                      : "text-[color:var(--page-text)] opacity-80 hover:opacity-100"
                  )}
                >
                  {tab === tabItem.key && (
                    <span
                      className="absolute bottom-0 left-0 right-0 h-0.5 bg-[color:var(--nav-link)] rounded-full"
                      aria-hidden="true"
                    />
                  )}
                  {t(`events:tabs.${tabItem.key}`)}
                </button>
              ))}
            </div>
          </div>

          {/* Search and filters */}
          <div
            data-fade
            style={fadeDelayStyle("240ms")}
            className="mb-5 flex flex-wrap items-center gap-3 rounded-ue-xl border border-[color:var(--glass-border)] bg-[linear-gradient(135deg,rgba(14,116,144,0.12),rgba(14,116,144,0))] px-4 py-3 shadow-[0_18px_45px_rgba(15,23,42,0.18)] backdrop-blur-[14px] sm:px-5 sm:py-4 lg:max-w-4xl"
          >
            <div className="relative flex-1 min-w-[200px]">
              <SearchIcon className="absolute left-3 top-1/2 h-5 w-5 -translate-y-1/2 text-[color:var(--secondary-text)] pointer-events-none" />
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder={t("events:filters.search")}
                className={cn(inputClass, "pl-10 pr-10", "w-full")}
              />
              <div className="absolute right-2 top-1/2 flex -translate-y-1/2 items-center gap-1">
                {search && (
                  <button
                    type="button"
                    onClick={() => setSearch("")}
                    className="rounded-full p-1.5 text-[color:var(--secondary-text)] transition-colors hover:text-[color:var(--nav-link)]"
                    aria-label={t("events:aria.clearSearch")}
                  >
                    <ClearIcon className="h-4 w-4" />
                  </button>
                )}
                <div className="relative">
                  <button
                    type="button"
                    onClick={(e) => setFilterAnchor(e.currentTarget)}
                    className="rounded-full p-1.5 text-[color:var(--secondary-text)] transition-colors hover:text-[color:var(--nav-link)]"
                    aria-label={t("events:aria.openFilters")}
                  >
                    {filtersActive && (
                      <span
                        className="absolute -right-0.5 -top-0.5 h-2 w-2 rounded-full bg-[color:var(--nav-link)]"
                        aria-hidden="true"
                      />
                    )}
                    <FilterListIcon className="h-4 w-4" />
                  </button>
                </div>
              </div>
            </div>
          </div>

          {/* Filter popover */}
          {filtersOpen && filterAnchor && (
            <div
              ref={filterPopoverRef}
              className="fixed z-50 mt-2 min-w-[260px] rounded-ue-lg border border-[color:var(--glass-border)] bg-[color:var(--card-bg)] p-4 shadow-surface-strong"
              style={{
                top: filterAnchor.getBoundingClientRect().bottom + 8,
                left: Math.min(filterAnchor.getBoundingClientRect().left, window.innerWidth - 280),
              }}
            >
              <div className="space-y-4">
                <div>
                  <label className="mb-2 block text-sm font-semibold text-[color:var(--secondary-text)]">
                    {t("events:filters.type")}
                  </label>
                  <input
                    type="text"
                    value={type}
                    onChange={(e) => setType(e.target.value)}
                    className={inputClass}
                  />
                </div>
                <div>
                  <label className="mb-2 block text-sm font-semibold text-[color:var(--secondary-text)]">
                    {t("events:filters.location")}
                  </label>
                  <input
                    type="text"
                    value={location}
                    onChange={(e) => setLocation(e.target.value)}
                    className={inputClass}
                  />
                </div>
                <div className="flex justify-end gap-2">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => {
                      setType("")
                      setLocation("")
                    }}
                  >
                    {t("common:buttons.reset")}
                  </Button>
                  <Button variant="solid" size="sm" onClick={() => setFilterAnchor(null)}>
                    {t("common:buttons.done")}
                  </Button>
                </div>
              </div>
            </div>
          )}

          {/* Events grid */}
          <div
            data-fade
            style={fadeDelayStyle("260ms")}
            role="tabpanel"
            id={`events-tabpanel-${tab}`}
            aria-labelledby={`events-tab-${tab}`}
            className="flex w-full flex-col gap-5 pb-6 transition-all duration-300 sm:gap-6 md:gap-8"
          >
            {loading && (
              <div className="flex flex-col items-center gap-5 sm:gap-6 md:gap-8">
                {Array.from({ length: skeletonCount }).map((_, i) => (
                  <div key={`event-skel-${i}`} className="flex w-full justify-center">
                    <div className="w-full max-w-[500px] space-y-3 rounded-ue-xl border border-[color:var(--glass-border)] bg-[color:var(--card-bg)] p-4 shadow-surface">
                      <Skeleton height={isMobile ? 160 : 200} className="rounded-ue-lg" />
                      <Skeleton height={isMobile ? 28 : 32} />
                      <Skeleton height={20} width={isMobile ? "85%" : "80%"} />
                      {!isMobile && <Skeleton height={20} width="60%" />}
                    </div>
                  </div>
                ))}
              </div>
            )}

            {!loading && normalizedEvents.length > 0 && (
              <div
                ref={listContainerRef}
                data-testid="events-virtual-scroll"
                role="region"
                aria-label={eventsListLabel}
                className="relative w-full"
                style={{ minHeight: virtualListMinHeight }}
              >
                <div
                  role="list"
                  aria-label={eventsListLabel}
                  className="relative w-full"
                  style={{ height: `${eventsVirtualizer.getTotalSize()}px` }}
                >
                  {virtualItems.map((virtualItem) => {
                    const isLoaderRow = virtualItem.index >= normalizedEvents.length
                    const event = normalizedEvents[virtualItem.index]

                    return (
                      <div
                        key={virtualItem.key}
                        data-virtual-index={virtualItem.index}
                        data-index={virtualItem.index}
                        role="listitem"
                        className="absolute left-0 right-0 flex justify-center pb-5 sm:pb-6 md:pb-8"
                        style={{ transform: `translateY(${virtualItem.start}px)` }}
                      >
                        <div className="flex w-full max-w-[500px]">
                          {isLoaderRow ? (
                            <div
                              className="flex w-full items-center justify-center rounded-ue-xl border border-dashed border-[color:var(--glass-border)] bg-[color:var(--card-bg)]/70 px-4 py-6 text-sm font-medium text-[color:var(--secondary-text)] shadow-surface"
                              role="status"
                              aria-live="polite"
                            >
                              {loadingMore ? loadingMoreLabel : null}
                            </div>
                          ) : (
                            <EventCard {...event} onChange={handleRefresh} maxWidth="500px" />
                          )}
                        </div>
                      </div>
                    )
                  })}
                </div>
              </div>
            )}

            {!loading && normalizedEvents.length === 0 && (
              <div className="mt-16 flex w-full justify-center">
                <div className="flex w-full max-w-[420px] flex-col items-center gap-5 rounded-ue-xl border border-[color:var(--glass-border)] bg-[color:color-mix(in_srgb,var(--card-bg)_96%,white_4%)] px-6 py-10 text-center text-[color:var(--secondary-text)] shadow-surface">
                  <span className="flex h-16 w-16 items-center justify-center rounded-full bg-[color:var(--glass-bg)]/70 text-[color:var(--nav-link)] shadow-surface">
                    <EventNoteIcon className="text-[2.2rem]" />
                  </span>
                  <p className="text-lg font-semibold text-[color:var(--page-text)] sm:text-xl">
                    {t("events:states.empty")}
                  </p>
                </div>
              </div>
            )}
          </div>

          {/* Create dialog */}
          <Dialog
            open={createOpen}
            onClose={closeCreate}
            title={t("events:dialogs.create.title")}
            size="lg"
            fullScreenOnMobile
            footer={
              <>
                <Button variant="outline" onClick={closeCreate} className="w-full sm:w-auto">
                  {t("common:buttons.cancel")}
                </Button>
                <Button
                  onClick={handleCreateEvent}
                  disabled={
                    !normalizedTitle ||
                    !eventData.starts_at ||
                    !eventData.ends_at ||
                    !normalizedLocation ||
                    imageUploading ||
                    dateError
                  }
                  className="w-full sm:w-auto"
                >
                  {t("common:buttons.create")}
                </Button>
              </>
            }
            footerClassName="flex-col-reverse gap-3 sm:flex-row"
          >
            <div className="space-y-4">
              <div>
                <label className="mb-2 block text-sm font-semibold tracking-wide text-[color:color-mix(in_srgb,var(--secondary-text)_85%,white_15%)]">
                  {language === "en"
                    ? t("events:form.title_en", {
                        defaultValue: `${t("events:form.title")} (English)`,
                      })
                    : t("events:form.title")}
                </label>
                <input
                  type="text"
                  value={getLocalizedDraftValue("title")}
                  onChange={(e) => updateLocalizedDraftValue("title", e.target.value)}
                  className={inputClass}
                />
              </div>
              <div>
                <label className="mb-2 block text-sm font-semibold tracking-wide text-[color:color-mix(in_srgb,var(--secondary-text)_85%,white_15%)]">
                  {language === "en"
                    ? t("events:form.description_en", {
                        defaultValue: `${t("events:form.description")} (English)`,
                      })
                    : t("events:form.description")}
                </label>
                <textarea
                  value={getLocalizedDraftValue("description")}
                  onChange={(e) => updateLocalizedDraftValue("description", e.target.value)}
                  rows={3}
                  className={cn(inputClass, "min-h-[120px] resize-y")}
                />
              </div>
              <div>
                <label className="mb-2 block text-sm font-semibold tracking-wide text-[color:color-mix(in_srgb,var(--secondary-text)_85%,white_15%)]">
                  {language === "en"
                    ? t("events:form.type_en", {
                        defaultValue: `${t("events:form.type")} (English)`,
                      })
                    : t("events:form.type")}
                </label>
                <input
                  type="text"
                  value={getLocalizedDraftValue("event_type")}
                  onChange={(e) => updateLocalizedDraftValue("event_type", e.target.value)}
                  className={inputClass}
                />
              </div>
              <div>
                <label className="mb-2 block text-sm font-semibold tracking-wide text-[color:color-mix(in_srgb,var(--secondary-text)_85%,white_15%)]">
                  {language === "en"
                    ? t("events:form.location_en", {
                        defaultValue: `${t("events:form.location")} (English)`,
                      })
                    : t("events:form.location")}
                </label>
                <input
                  type="text"
                  value={getLocalizedDraftValue("location")}
                  onChange={(e) => updateLocalizedDraftValue("location", e.target.value)}
                  className={inputClass}
                />
              </div>
              <div>
                <label className="mb-2 block text-sm font-semibold tracking-wide text-[color:color-mix(in_srgb,var(--secondary-text)_85%,white_15%)]">
                  {t("events:form.speaker")}
                </label>
                <input
                  type="text"
                  value={eventData.speaker}
                  onChange={(e) => setEventData({ ...eventData, speaker: e.target.value })}
                  className={inputClass}
                />
              </div>
              <div>
                <Button
                  as="label"
                  variant="outline"
                  disabled={imageUploading}
                  className="w-full sm:w-auto"
                >
                  {imageUploading
                    ? t("common:statuses.uploading")
                    : eventData.image_url
                      ? t("events:form.imageSelected")
                      : t("events:form.uploadImage")}
                  <input
                    type="file"
                    hidden
                    accept="image/*"
                    onChange={(e) => {
                      const file = e.target.files?.[0]
                      if (file) handleImageUpload(file)
                    }}
                  />
                </Button>
                {(createPreview || eventData.image_url) && (
                  <div className="mt-3">
                    <SmartImage
                      srcRaw={createPreview || eventData.image_url || ""}
                      alt={t("events:alt.preview")}
                      className="max-h-[140px] rounded-ue-lg border border-[color:var(--glass-border)] object-cover shadow-surface"
                    />
                  </div>
                )}
              </div>
              <div>
                <label className="mb-2 block text-sm font-semibold tracking-wide text-[color:color-mix(in_srgb,var(--secondary-text)_85%,white_15%)]">
                  {t("events:form.start")}
                </label>
                <input
                  type="datetime-local"
                  value={eventData.starts_at}
                  onChange={(e) => setEventData({ ...eventData, starts_at: e.target.value })}
                  className={inputClass}
                />
              </div>
              <div>
                <label className="mb-2 block text-sm font-semibold tracking-wide text-[color:color-mix(in_srgb,var(--secondary-text)_85%,white_15%)]">
                  {t("events:form.end")}
                </label>
                <input
                  type="datetime-local"
                  value={eventData.ends_at}
                  onChange={(e) => setEventData({ ...eventData, ends_at: e.target.value })}
                  className={cn(inputClass, dateError && "border-red-500")}
                />
                {dateError && (
                  <p className="mt-1 text-sm text-red-500">
                    {t("events:form.errors.endsBeforeStarts")}
                  </p>
                )}
              </div>
            </div>
          </Dialog>
        </div>
      </PageFadeIn>
    </Layout>
  )
}

export default Events
