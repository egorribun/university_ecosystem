import Layout from "../components/Layout"
import PageFadeIn from "../components/PageFadeIn"
import EventCard from "../components/EventCard"
import {
  useEffect,
  useState,
  useCallback,
  useMemo,
  useRef,
  useLayoutEffect,
  type CSSProperties,
} from "react"
import { useQueryClient } from "@tanstack/react-query"
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
import { Button, Badge, Skeleton } from "@/components/ui"
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

  // Tab indicator animation
  const tabContainerRef = useRef<HTMLDivElement>(null)
  const tabRefs = useRef<Map<EventTabKey, HTMLButtonElement | null>>(new Map())
  const [indicatorStyle, setIndicatorStyle] = useState<{ left: number; width: number }>({
    left: 0,
    width: 0,
  })

  useLayoutEffect(() => {
    const activeButton = tabRefs.current.get(tab)
    const container = tabContainerRef.current
    if (activeButton && container) {
      const containerRect = container.getBoundingClientRect()
      const buttonRect = activeButton.getBoundingClientRect()
      setIndicatorStyle({
        left: buttonRect.left - containerRect.left,
        width: buttonRect.width,
      })
    }
  }, [tab])

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

  const loadMore = useCallback(async () => {
    if (tab !== "my" && listHasNextPage) {
      await fetchNextEventsPage()
    }
  }, [fetchNextEventsPage, listHasNextPage, tab])

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
  const dateError = !!(eventData.starts_at && eventData.ends_at && ends <= starts)
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

  return (
    <Layout>
      <PageFadeIn>
        <div className="w-screen min-h-screen bg-[color:var(--page-bg)] text-[color:var(--page-text)] py-8 sm:py-10">
          <div className="px-4 sm:px-6 lg:px-8">
            {/* Header */}
            <div
              data-fade
              style={fadeDelayStyle("80ms")}
              className="mb-8 flex flex-wrap items-center gap-4 sm:gap-5"
            >
              <div className="flex h-12 w-12 items-center justify-center rounded-full bg-[color:color-mix(in_srgb,var(--glass-bg)_70%,var(--nav-link)_30%)] text-[color:var(--nav-link)] shadow-[0_6px_20px_color-mix(in_srgb,var(--nav-link)_24%,transparent)] transition-transform duration-300 hover:scale-[1.08] dark:bg-[color:color-mix(in_srgb,var(--glass-bg)_65%,var(--nav-link)_35%)] dark:shadow-[0_8px_24px_color-mix(in_srgb,var(--nav-link)_28%,transparent)] overflow-hidden">
                <span className="flex items-center justify-center">
                  <EventNoteIcon className="text-[2rem]" />
                </span>
              </div>
              <h1 className="text-[clamp(1.6rem,5vw,2.75rem)] font-bold tracking-tight text-[color:var(--page-text)]">
                {t("events:pageTitle")}
              </h1>
            </div>

            {/* Create button */}
            {(user?.role === "admin" || user?.role === "teacher") && (
              <div data-fade style={fadeDelayStyle("140ms")} className="mb-6 flex justify-start">
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
              className="mb-6 lg:max-w-4xl"
              role="tablist"
            >
              <div
                ref={tabContainerRef}
                className="relative inline-flex rounded-[12px] bg-[color:color-mix(in_srgb,var(--card-bg)_92%,var(--nav-link)_8%)] p-1 border border-[color:color-mix(in_srgb,var(--nav-link)_12%,transparent_88%)] shadow-[0_2px_8px_-2px_rgba(0,0,0,0.1),inset_0_1px_0_rgba(255,255,255,0.04)]"
              >
                {/* Sliding indicator */}
                <div
                  className="absolute top-1 bottom-1 rounded-[9px] bg-[color:var(--card-bg)] shadow-[0_2px_8px_-2px_rgba(0,0,0,0.15),0_1px_2px_rgba(0,0,0,0.08),inset_0_1px_0_rgba(255,255,255,0.06)] border border-[color:color-mix(in_srgb,var(--nav-link)_20%,transparent_80%)] transition-all duration-300 ease-[cubic-bezier(0.34,1.56,0.64,1)]"
                  style={{
                    left: indicatorStyle.left,
                    width: indicatorStyle.width,
                  }}
                  aria-hidden="true"
                />
                {tabs.map((tabItem) => (
                  <button
                    key={tabItem.key}
                    ref={(el) => {
                      tabRefs.current.set(tabItem.key, el)
                    }}
                    role="tab"
                    id={`events-tab-${tabItem.key}`}
                    aria-selected={tab === tabItem.key}
                    aria-controls={`events-tabpanel-${tabItem.key}`}
                    onClick={() => handleTabChange(tabItem.key)}
                    className={cn(
                      "relative z-[1] px-4 py-2 text-[15px] font-semibold rounded-[9px] transition-colors duration-200",
                      "sm:px-6 sm:text-base",
                      tab === tabItem.key
                        ? "text-[color:var(--page-text)]"
                        : "text-[color:var(--secondary-text)] hover:text-[color:var(--page-text)]"
                    )}
                  >
                    {t(`events:tabs.${tabItem.key}`)}
                  </button>
                ))}
              </div>
            </div>

            {/* Search and filters */}
            <div data-fade style={fadeDelayStyle("240ms")} className="mb-6 lg:max-w-4xl">
              <div className="relative">
                <SearchIcon className="absolute left-4 top-1/2 h-5 w-5 -translate-y-1/2 text-[color:var(--secondary-text)] pointer-events-none opacity-60" />
                <input
                  type="text"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder={t("events:filters.search")}
                  className={cn(
                    "w-full rounded-[14px] px-4 py-3.5 pl-11 pr-20 text-base text-[color:var(--page-text)]",
                    "bg-[color:color-mix(in_srgb,var(--card-bg)_94%,var(--nav-link)_6%)]",
                    "border border-[color:color-mix(in_srgb,var(--nav-link)_12%,var(--glass-border)_88%)]",
                    "shadow-[0_2px_12px_-4px_rgba(0,0,0,0.08),inset_0_1px_0_rgba(255,255,255,0.04)]",
                    "placeholder:text-[color:var(--secondary-text)] placeholder:opacity-50",
                    "outline-none transition-all duration-200",
                    "focus:border-[color:color-mix(in_srgb,var(--nav-link)_35%,var(--glass-border)_65%)]",
                    "focus:shadow-[0_0_0_3px_color-mix(in_srgb,var(--nav-link)_12%,transparent_88%),0_2px_12px_-4px_rgba(0,0,0,0.08)]"
                  )}
                />
                <div className="absolute right-2 top-1/2 flex -translate-y-1/2 items-center gap-1">
                  {search && (
                    <button
                      type="button"
                      onClick={() => setSearch("")}
                      className="rounded-full p-2 text-[color:var(--secondary-text)] transition-all duration-150 hover:bg-[color:color-mix(in_srgb,var(--nav-link)_8%,transparent_92%)] active:scale-95"
                      aria-label={t("events:aria.clearSearch")}
                    >
                      <ClearIcon className="h-4 w-4" />
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={(e) => setFilterAnchor(e.currentTarget)}
                    className={cn(
                      "relative rounded-full p-2 transition-all duration-150 hover:bg-[color:color-mix(in_srgb,var(--nav-link)_8%,transparent_92%)] active:scale-95",
                      filtersActive
                        ? "text-[color:var(--nav-link)]"
                        : "text-[color:var(--secondary-text)]"
                    )}
                    aria-label={t("events:aria.openFilters")}
                  >
                    {filtersActive && (
                      <span
                        className="absolute right-1.5 top-1.5 h-2 w-2 rounded-full bg-[color:var(--nav-link)] shadow-[0_0_4px_var(--nav-link)]"
                        aria-hidden="true"
                      />
                    )}
                    <FilterListIcon className="h-5 w-5" />
                  </button>
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
                  left: Math.min(
                    filterAnchor.getBoundingClientRect().left,
                    window.innerWidth - 280
                  ),
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
              className="grid gap-5 sm:gap-6 pb-6 grid-cols-1 md:grid-cols-2 xl:grid-cols-3"
            >
              {loading &&
                Array.from({ length: skeletonCount }).map((_, i) => (
                  <div key={`event-skel-${i}`} className="w-full">
                    <div className="w-full space-y-4 rounded-[var(--ios-card-radius)] border border-[color:var(--ios-card-border)] bg-[color:var(--card-bg)] p-5 shadow-[var(--ios-card-shadow)]">
                      <Skeleton height={isMobile ? 180 : 200} className="rounded-[16px]" />
                      <Skeleton height={28} className="rounded-[6px]" />
                      <Skeleton height={20} width="75%" className="rounded-[6px]" />
                      <div className="flex gap-3 pt-2">
                        <Skeleton height={36} width={120} className="rounded-[10px]" />
                        <Skeleton height={36} width={100} className="rounded-[10px]" />
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
                <div className="col-span-full mt-12 flex w-full justify-center animate-in fade-in slide-in-from-bottom-4 duration-500">
                  <div className="flex w-full max-w-md flex-col items-center gap-5 rounded-[1.25rem] border border-[color:color-mix(in_srgb,var(--nav-link)_15%,var(--glass-border)_85%)] bg-gradient-to-br from-[color:var(--card-bg)] to-[color:color-mix(in_srgb,var(--card-bg)_94%,var(--nav-link)_6%)] px-8 py-14 text-center shadow-[0_4px_24px_-8px_rgba(0,0,0,0.12)]">
                    <div className="flex h-16 w-16 items-center justify-center rounded-full bg-gradient-to-br from-[color:color-mix(in_srgb,var(--nav-link)_20%,var(--card-bg)_80%)] to-[color:color-mix(in_srgb,var(--nav-link)_10%,var(--card-bg)_90%)] shadow-[0_4px_12px_-4px_color-mix(in_srgb,var(--nav-link)_30%,transparent_70%)]">
                      <EventNoteIcon className="text-[2rem] text-[color:var(--nav-link)]" />
                    </div>
                    <div className="space-y-2">
                      <p className="text-lg font-semibold text-[color:var(--page-text)]">
                        {t("events:states.empty")}
                      </p>
                      <p className="text-sm text-[color:var(--secondary-text)]">
                        {tab === "active"
                          ? "Попробуйте посмотреть прошедшие мероприятия"
                          : tab === "archive"
                            ? "Загляните в актуальные мероприятия"
                            : "Зарегистрируйтесь на интересующие мероприятия"}
                      </p>
                    </div>
                    {tab !== "my" && (
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => handleTabChange(tab === "active" ? "archive" : "active")}
                        className="mt-2"
                      >
                        {tab === "active" ? "Прошедшие" : "Актуальные"}
                      </Button>
                    )}
                  </div>
                </div>
              )}
            </div>

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
        </div>
      </PageFadeIn>
    </Layout>
  )
}

export default Events
