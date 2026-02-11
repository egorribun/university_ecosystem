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
import {
  Calendar as EventNoteIcon,
  Search as SearchIcon,
  Filter as FilterListIcon,
  X as ClearIcon,
} from "lucide-react"
import { useAuth } from "../contexts/AuthContext"
import SmartImage from "@/components/SmartImage"
import { useSearchParams } from "react-router-dom"
import { useTranslation } from "react-i18next"
import { EVENTS_PAGE_SIZE, useEventsListQuery, useMyEventsQuery } from "@/api/hooks/events"
import { Button, Badge, Skeleton } from "@/components/ui"
import { Dialog, DialogActions, DialogContent, DialogTitle } from "@/components/settings"
import { motion, AnimatePresence } from "framer-motion"
import { springSoft } from "@/utils/animations"
import { cn } from "@/utils/cn"
import useMediaQuery from "@/hooks/useMediaQuery"
import { breakpoints } from "@/theme/tokens"
import { useDebounced } from "@/hooks/useDebounced"

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


const fadeDelayStyle = (value: string): CSSProperties =>
  ({ "--fade-delay": value }) as CSSProperties

const inputClass =
  "w-full rounded-xl border border-glass-border bg-(--bg-surface)/(--opacity-medium) px-4 py-3 text-md font-medium text-(--text-primary) shadow-sm focus:border-brand focus:outline-none transition-all placeholder:text-(--text-secondary)/(--opacity-medium)"

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

  const isMobile = useMediaQuery(`(max-width: ${breakpoints.content})`)

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
        <div className="w-full min-h-screen bg-transparent text-(--text-primary) py-8 sm:py-10">
          <div className="px-4 sm:px-6 lg:px-8">
            {/* Header */}
            <div
              data-fade
              style={fadeDelayStyle("80ms")}
              className="mb-8 flex flex-wrap items-center gap-4 sm:gap-5"
            >
              <div className="flex h-12 w-12 items-center justify-center rounded-full bg-(--bg-surface)/(--opacity-medium) border border-glass-border text-brand shadow-glass transition-transform duration-300 hover:scale-[1.08] overflow-hidden">
                <EventNoteIcon className="h-7 w-7" />
              </div>
              <h1 className="text-(length:--fs-page-title) font-bold tracking-tight text-(--text-primary)">
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
                  className="px-6 text-fluid-title-sm"
                >
                  {t("events:actions.openCreate")}
                </Button>
              </div>
            )}

            {/* Tabs */}
            <div
              data-fade
              style={fadeDelayStyle("200ms")}
              className="w-full max-w-[440px] z-(--z-modal)"
              role="tablist"
            >
              <div
                ref={tabContainerRef}
                className={cn(
                  "inline-flex w-full items-center gap-1 rounded-[11px] border border-glass-border bg-(--bg-surface)/(--opacity-medium) p-1 backdrop-blur-md shadow-glass",
                  "sm:w-auto"
                )}
              >
                {tabs.map((tabItem) => (
                  <button
                    key={tabItem.key}
                    type="button"
                    role="tab"
                    aria-selected={tab === tabItem.key}
                    aria-controls={`events-tabpanel-${tabItem.key}`}
                    onClick={() => handleTabChange(tabItem.key)}
                    className={cn(
                      "relative z-(--z-base) px-4 py-2 text-body-sm font-semibold rounded-[9px] transition-colors duration-200",
                      "sm:px-6 sm:text-base",
                      tab === tabItem.key
                        ? "text-(--text-primary)"
                        : "text-(--text-secondary) hover:text-(--text-primary)"
                    )}
                  >
                    {tab === tabItem.key && (
                      <motion.div
                        layoutId="active-tab-indicator"
                        className="absolute inset-0 bg-(--bg-surface) shadow-sm"
                        style={{ borderRadius: "inherit", zIndex: -1 }}
                        transition={springSoft}
                      />
                    )}
                    <span className="relative z-(--z-base)">{t(`events:tabs.${tabItem.key}`)}</span>
                  </button>
                ))}
              </div>
            </div>

            {/* Search and filters */}
            <div data-fade style={fadeDelayStyle("240ms")} className="mb-6 lg:max-w-4xl">
              <div className="relative">
                <SearchIcon className="absolute left-4 top-1/2 h-5 w-5 -translate-y-1/2 text-(--text-secondary) pointer-events-none opacity-(--opacity-strong)" />
                <input
                  type="text"
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                  placeholder={t("events:filters.search")}
                  className={cn(
                    "w-full rounded-2xl px-4 py-3.5 pl-11 pr-20 text-base text-(--text-primary)",
                    "bg-(--bg-surface)/(--opacity-medium) border border-glass-border shadow-glass backdrop-blur-md",
                    "placeholder:text-(--text-secondary)/(--opacity-medium)",
                    "outline-none transition-all duration-200",
                    "focus:border-brand/(--opacity-medium) focus:ring-4 focus:ring-brand/(--opacity-subtle)"
                  )}
                />
                <div className="absolute right-2 top-1/2 flex -translate-y-1/2 items-center gap-1">
                  {search && (
                    <button
                      type="button"
                      onClick={() => setSearch("")}
                      className="rounded-full p-2 text-(--text-secondary) transition-all duration-150 hover:bg-(--bg-surface)/(--opacity-dim) active:scale-95"
                      aria-label={t("events:aria.clearSearch")}
                    >
                      <ClearIcon className="h-4 w-4" />
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={(event) => setFilterAnchor(event.currentTarget)}
                    className={cn(
                      "relative rounded-full p-2 transition-all duration-150 hover:bg-(--bg-surface)/(--opacity-dim) active:scale-95",
                      filtersActive ? "text-brand" : "text-(--text-secondary)"
                    )}
                    aria-label={t("events:aria.openFilters")}
                  >
                    {filtersActive && (
                      <span
                        className="absolute right-1.5 top-1.5 h-2 w-2 rounded-full bg-brand shadow-glow-green"
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
                className="fixed z-(--z-modal) mt-2 min-w-[260px] rounded-2xl border border-glass-border bg-(--bg-surface)/(--opacity-heavy) p-4 shadow-glass backdrop-blur-xl"
                style={{
                  top: filterAnchor.getBoundingClientRect().bottom + 8,
                  right: window.innerWidth - filterAnchor.getBoundingClientRect().right,
                }}
              >
                <div className="space-y-4">
                  <div>
                    <label className="mb-2 block text-sm font-semibold text-(--text-secondary)">
                      {t("events:filters.type")}
                    </label>
                    <input
                      type="text"
                      value={type}
                      onChange={(event) => setType(event.target.value)}
                      className={inputClass}
                    />
                  </div>
                  <div>
                    <label className="mb-2 block text-sm font-semibold text-(--text-secondary)">
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
                    <div className="w-full space-y-4 rounded-3xl border border-glass-border bg-(--bg-surface)/(--opacity-medium) p-5 shadow-glass backdrop-blur-md">
                      <Skeleton height={isMobile ? 180 : 200} className="rounded-2xl" />
                      <Skeleton height={28} className="rounded-lg" />
                      <Skeleton height={20} width="75%" className="rounded-lg" />
                      <div className="flex gap-3 pt-2">
                        <Skeleton height={36} width={120} className="rounded-xl" />
                        <Skeleton height={36} width={100} className="rounded-xl" />
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
                  <div className="flex w-full max-w-md flex-col items-center gap-5 rounded-3xl border border-glass-border/(--opacity-soft) bg-(--bg-surface)/(--opacity-medium) px-8 py-14 text-center shadow-glass backdrop-blur-md">
                    <div className="relative z-(--z-base) flex h-16 w-16 items-center justify-center rounded-full bg-brand/(--opacity-subtle) border border-brand/(--opacity-dim) shadow-brand/(--opacity-subtle) shadow-lg">
                      <EventNoteIcon className="h-8 w-8 text-brand" />
                    </div>
                    <div className="space-y-2">
                      <p className="text-lg font-semibold text-(--text-primary)">
                        {t("events:states.empty")}
                      </p>
                      <p className="text-sm text-(--text-secondary)">
                        {tab === "active"
                          ? t("events:states.emptyHint.active")
                          : tab === "archive"
                            ? t("events:states.emptyHint.archive")
                            : t("events:states.emptyHint.my")}
                      </p>
                    </div>
                    {tab !== "my" && (
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleTabChange(tab === "active" ? "archive" : "active")}
                        className="mt-2 text-brand hover:bg-brand/(--opacity-subtle)"
                      >
                        {tab === "active" ? t("events:tabs.archive") : t("events:tabs.active")}
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
            <Dialog open={createOpen} onClose={closeCreate} maxWidth="lg" fullWidth>
              <DialogTitle>{t("events:dialogs.create.title")}</DialogTitle>
              <DialogContent className="space-y-6 pt-4">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  <div className="space-y-4">
                    <div>
                      <label className="mb-2 block text-sm font-semibold text-(--text-secondary)">
                        {language === "en"
                          ? t("events:form.title_en", {
                              defaultValue: `${t("events:form.title")} (English)`,
                            })
                          : t("events:form.title")}
                      </label>
                      <input
                        type="text"
                        value={getLocalizedDraftValue("title")}
                        onChange={(event) => updateLocalizedDraftValue("title", event.target.value)}
                        className={inputClass}
                      />
                    </div>
                    <div>
                      <label className="mb-2 block text-sm font-semibold text-(--text-secondary)">
                        {language === "en"
                          ? t("events:form.description_en", {
                              defaultValue: `${t("events:form.description")} (English)`,
                            })
                          : t("events:form.description")}
                      </label>
                      <textarea
                        value={getLocalizedDraftValue("description")}
                        onChange={(event) =>
                          updateLocalizedDraftValue("description", event.target.value)
                        }
                        rows={3}
                        className={cn(inputClass, "min-h-[120px] resize-y")}
                      />
                    </div>
                    <div>
                      <label className="mb-2 block text-sm font-semibold text-(--text-secondary)">
                        {language === "en"
                          ? t("events:form.type_en", {
                              defaultValue: `${t("events:form.type")} (English)`,
                            })
                          : t("events:form.type")}
                      </label>
                      <input
                        type="text"
                        value={getLocalizedDraftValue("event_type")}
                        onChange={(event) =>
                          updateLocalizedDraftValue("event_type", event.target.value)
                        }
                        className={inputClass}
                      />
                    </div>
                    <div>
                      <label className="mb-2 block text-sm font-semibold text-(--text-secondary)">
                        {language === "en"
                          ? t("events:form.location_en", {
                              defaultValue: `${t("events:form.location")} (English)`,
                            })
                          : t("events:form.location")}
                      </label>
                      <input
                        type="text"
                        value={getLocalizedDraftValue("location")}
                        onChange={(event) =>
                          updateLocalizedDraftValue("location", event.target.value)
                        }
                        className={inputClass}
                      />
                    </div>
                  </div>

                  <div className="space-y-4">
                    <div>
                      <label className="mb-2 block text-sm font-semibold text-(--text-secondary)">
                        {t("events:form.speaker")}
                      </label>
                      <input
                        type="text"
                        value={eventData.speaker}
                        onChange={(event) =>
                          setEventData({ ...eventData, speaker: event.target.value })
                        }
                        className={inputClass}
                      />
                    </div>
                    <div className="space-y-3">
                      <label className="block text-sm font-semibold text-(--text-secondary)">
                        {t("events:form.image")}
                      </label>
                      <Button
                        as="label"
                        variant="outline"
                        disabled={imageUploading}
                        className="w-full justify-start gap-2 bg-(--bg-surface)/(--opacity-dim)"
                      >
                        {imageUploading ? (
                          t("common:statuses.uploading")
                        ) : (
                          <>
                            <SearchIcon className="h-4 w-4" />
                            {eventData.image_url
                              ? t("events:form.imageSelected")
                              : t("events:form.uploadImage")}
                          </>
                        )}
                        <input
                          type="file"
                          hidden
                          accept="image/*"
                          onChange={(event) => {
                            const file = event.target.files?.[0]
                            if (file) handleImageUpload(file)
                          }}
                        />
                      </Button>
                      {(createPreview || eventData.image_url) && (
                        <div className="mt-3 overflow-hidden rounded-2xl border border-glass-border shadow-glass">
                          <SmartImage
                            srcRaw={createPreview || eventData.image_url || ""}
                            alt={t("events:alt.preview")}
                            className="aspect-video w-full object-cover"
                          />
                        </div>
                      )}
                    </div>
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <label className="mb-2 block text-sm font-semibold text-(--text-secondary)">
                          {t("events:form.start")}
                        </label>
                        <input
                          type="datetime-local"
                          value={eventData.starts_at}
                          onChange={(event) =>
                            setEventData({ ...eventData, starts_at: event.target.value })
                          }
                          className={inputClass}
                        />
                      </div>
                      <div>
                        <label className="mb-2 block text-sm font-semibold text-(--text-secondary)">
                          {t("events:form.end")}
                        </label>
                        <input
                          type="datetime-local"
                          value={eventData.ends_at}
                          onChange={(event) =>
                            setEventData({ ...eventData, ends_at: event.target.value })
                          }
                          className={cn(inputClass, dateError && "border-error-border")}
                        />
                      </div>
                    </div>
                    {dateError && (
                      <p className="mt-1 text-sm text-error-text font-medium">
                        {t("events:form.errors.endsBeforeStarts")}
                      </p>
                    )}
                  </div>
                </div>
              </DialogContent>
              <DialogActions className="flex-col-reverse gap-3 sm:flex-row p-6">
                <Button variant="ghost" onClick={closeCreate} className="w-full sm:w-auto">
                  {t("common:buttons.cancel")}
                </Button>
                <Button
                  variant="solid"
                  onClick={handleCreateEvent}
                  disabled={
                    !normalizedTitle ||
                    !eventData.starts_at ||
                    !eventData.ends_at ||
                    !normalizedLocation ||
                    imageUploading ||
                    dateError
                  }
                  className="w-full sm:w-auto min-w-(--min-w-btn)"
                >
                  {t("common:buttons.create")}
                </Button>
              </DialogActions>
            </Dialog>
          </div>
        </div>
      </PageFadeIn>
    </Layout>
  )
}

export default Events
