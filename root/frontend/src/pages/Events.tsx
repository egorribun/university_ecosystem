import Layout from "../components/Layout"
import PageFadeIn from "../components/PageFadeIn"
import EventCard from "../components/EventCard"
import {
  useEffect,
  useState,
  useCallback,
  useMemo,
  useRef,
  type SyntheticEvent,
  type CSSProperties,
} from "react"
import axios from "../api/client"
import type { Event } from "@/types/Event"
import type { PaginatedResponse } from "@/types/Pagination"
import {
  Box,
  Tabs,
  Tab,
  TextField,
  Typography,
  Button,
  Dialog,
  DialogTitle,
  DialogContent,
  Stack,
  useMediaQuery,
  Skeleton,
  InputAdornment,
  IconButton,
  Popover,
  Badge,
} from "@mui/material"
import EventNoteIcon from "@mui/icons-material/EventNote"
import SearchIcon from "@mui/icons-material/Search"
import FilterListIcon from "@mui/icons-material/FilterList"
import ClearIcon from "@mui/icons-material/Clear"
import { useAuth } from "../contexts/AuthContext"
import SmartImage from "@/components/SmartImage"
import { useSearchParams } from "react-router-dom"
import { useTranslation } from "react-i18next"

type EventTabKey = "active" | "archive" | "my"
type EventTab = { key: EventTabKey; is_active?: boolean }

const tabs = [
  { key: "active", is_active: true },
  { key: "archive", is_active: false },
  { key: "my" },
] as const satisfies readonly EventTab[]

const PAGE_SIZE = 12

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

const Events = () => {
  const { user } = useAuth()
  const [searchParams, setSearchParams] = useSearchParams()
  const { t, i18n } = useTranslation(["events", "common"])
  const language = i18n.language?.startsWith("en") ? "en" : "ru"

  const [events, setEvents] = useState<Event[]>([])
  const [tab, setTab] = useState<EventTabKey>("active")
  const [search, setSearch] = useState("")
  const [type, setType] = useState("")
  const [location, setLocation] = useState("")

  const [createOpen, setCreateOpen] = useState(false)
  const [eventData, setEventData] = useState<EventDraft>(initialEvent)
  const [imageUploading, setImageUploading] = useState(false)
  const [loading, setLoading] = useState(false)
  const [loadingMore, setLoadingMore] = useState(false)
  const [pagination, setPagination] = useState<PaginatedResponse<Event> | null>(null)

  const [createPreview, setCreatePreview] = useState<string | null>(null)

  const isMobile = useMediaQuery("(max-width:900px)")

  const [filterAnchor, setFilterAnchor] = useState<HTMLElement | null>(null)
  const filtersOpen = Boolean(filterAnchor)
  const filtersActive = Boolean(type?.trim() || location?.trim())
  const etagCacheRef = useRef<Record<string, string>>({})
  const eventsCacheRef = useRef<
    Record<string, { events: Event[]; pagination: PaginatedResponse<Event> | null }>
  >({})

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

  const cacheKey = useMemo(() => {
    if (tab === "my") {
      return `my:${language}`
    }
    const isActiveFilter = tab === "active" ? true : tab === "archive" ? false : undefined
    return `${tab}:${language}:${String(isActiveFilter)}:${dSearch}:${dType}:${dLocation}:limit:${PAGE_SIZE}`
  }, [tab, language, dSearch, dType, dLocation])

  const fetchEvents = useCallback(
    async (signal?: AbortSignal) => {
      setLoading(true)
      if (tab !== "my") {
        setPagination(null)
      }
      try {
        const isActiveFilter = tab === "active" ? true : tab === "archive" ? false : undefined
        const params =
          tab === "my"
            ? undefined
            : {
                is_active: isActiveFilter,
                search: dSearch,
                type: dType,
                location: dLocation,
                limit: PAGE_SIZE,
                cursor: 0,
              }

        const keyBase = cacheKey
        const headers = etagCacheRef.current[keyBase]
          ? { "If-None-Match": etagCacheRef.current[keyBase] }
          : undefined
        const requestConfig = {
          signal,
          params,
          headers,
          validateStatus: (status: number) => status >= 200 && status < 400,
        } as const

        if (tab === "my") {
          const res = await axios.get<Event[]>("/events/my", requestConfig)
          const receivedEtag = res.headers?.etag
          if (receivedEtag) {
            etagCacheRef.current[keyBase] = receivedEtag
          } else {
            delete etagCacheRef.current[keyBase]
          }
          if (res.status === 304) {
            const cached = eventsCacheRef.current[keyBase]
            if (cached) {
              setEvents(cached.events)
            }
            setPagination(null)
            return
          }
          const nextEvents = Array.isArray(res.data) ? res.data : []
          eventsCacheRef.current[keyBase] = { events: nextEvents, pagination: null }
          setEvents(nextEvents)
          setPagination(null)
          return
        }

        const res = await axios.get<PaginatedResponse<Event>>("/events", requestConfig)
        const receivedEtag = res.headers?.etag
        if (receivedEtag) {
          etagCacheRef.current[keyBase] = receivedEtag
        } else {
          delete etagCacheRef.current[keyBase]
        }
        if (res.status === 304) {
          const cached = eventsCacheRef.current[keyBase]
          if (cached) {
            setEvents(cached.events)
            setPagination(cached.pagination)
          }
          return
        }

        const data = res.data
        const nextEvents = Array.isArray(data?.items) ? data.items : []
        const nextPagination = data ?? null
        eventsCacheRef.current[keyBase] = { events: nextEvents, pagination: nextPagination }
        setEvents(nextEvents)
        setPagination(nextPagination)
      } catch (err: any) {
        if (err?.name !== "CanceledError" && err?.code !== "ERR_CANCELED") {
          setEvents([])
          setPagination(null)
        }
      } finally {
        setLoading(false)
      }
    },
    [tab, dSearch, dType, dLocation, language, cacheKey]
  )

  useEffect(() => {
    const ctrl = new AbortController()
    fetchEvents(ctrl.signal)
    return () => ctrl.abort()
  }, [fetchEvents])

  const loadMore = useCallback(async () => {
    if (tab === "my" || loadingMore) return
    const nextCursor = pagination?.next_cursor
    if (nextCursor == null) return
    setLoadingMore(true)
    try {
      const isActiveFilter = tab === "active" ? true : tab === "archive" ? false : undefined
      const res = await axios.get<PaginatedResponse<Event>>("/events", {
        params: {
          is_active: isActiveFilter,
          search: dSearch,
          type: dType,
          location: dLocation,
          limit: PAGE_SIZE,
          cursor: nextCursor,
        },
        validateStatus: (status: number) => status >= 200 && status < 300,
      })
      const data = res.data
      const newItems = Array.isArray(data?.items) ? data.items : []
      let mergedEvents: Event[] = []
      setEvents((prev) => {
        const existing = Array.isArray(prev) ? [...prev] : []
        const seen = new Set(existing.map((item) => item.id))
        newItems.forEach((item) => {
          if (seen.has(item.id)) {
            const index = existing.findIndex((evt) => evt.id === item.id)
            if (index >= 0) existing[index] = item
          } else {
            existing.push(item)
            seen.add(item.id)
          }
        })
        mergedEvents = existing
        return existing
      })
      setPagination((prev) => {
        if (!data) {
          const cached = eventsCacheRef.current[cacheKey]
          eventsCacheRef.current[cacheKey] = {
            events: mergedEvents,
            pagination: prev ?? null,
          }
          return prev
        }
        if (!prev) {
          eventsCacheRef.current[cacheKey] = { events: mergedEvents, pagination: data }
          return data
        }
        const nextPagination = {
          ...prev,
          ...data,
        }
        eventsCacheRef.current[cacheKey] = {
          events: mergedEvents,
          pagination: nextPagination,
        }
        return nextPagination
      })
    } catch (err: any) {
      if (err?.name !== "CanceledError" && err?.code !== "ERR_CANCELED") {
        setPagination((prev) => (prev ? { ...prev, has_more: false, next_cursor: null } : prev))
      }
    } finally {
      setLoadingMore(false)
    }
  }, [tab, loadingMore, pagination?.next_cursor, dSearch, dType, dLocation, cacheKey])

  const handleTabChange = (_event: SyntheticEvent, newValue: EventTabKey) => setTab(newValue)

  const handleImageUpload = async (file: File) => {
    setImageUploading(true)
    const localUrl = URL.createObjectURL(file)
    setCreatePreview((prev) => {
      if (prev) URL.revokeObjectURL(prev)
      return localUrl
    })
    try {
      const formData = new FormData()
      formData.append("file", file)
      const res = await axios.post<{ url: string }>("/events/upload_image", formData, {
        headers: { "Content-Type": "multipart/form-data" },
      })
      setEventData((prev) => ({ ...prev, image_url: res.data.url }))
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
      }
      const res = await axios.post<Event>("/events", payload)
      closeCreate()
      setTab("active")
      setEvents((prev) => [res.data, ...prev])
      setPagination((prev) => (prev ? { ...prev, total: prev.total + 1 } : prev))
      window.scrollTo({ top: 0, behavior: "smooth" })
    } catch {}
  }

  const handleRefresh = useCallback(() => {
    if (!loading) fetchEvents()
  }, [fetchEvents, loading])

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

  const normalizedEvents = useMemo(() => (Array.isArray(events) ? events : []), [events])

  const layoutConfig = useMemo(() => {
    if (isMobile) {
      return {
        gridTemplateColumns: "minmax(0, 1fr)",
        gap: { xs: 2, sm: 2 },
        cardMaxWidth: "100%",
      }
    }

    return {
      gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))",
      gap: { xs: 2, sm: 2.5, md: 3 },
      cardMaxWidth: "100%",
    }
  }, [isMobile])

  const { gridTemplateColumns, gap, cardMaxWidth } = layoutConfig

  const eventsContent = useMemo(() => {
    const skeletonCount = isMobile ? 3 : 6
    return (
      <Box
        data-fade
        style={{ "--fade-delay": "260ms" } as CSSProperties}
        sx={{
          display: "grid",
          gridTemplateColumns,
          gap,
          minHeight: "180px",
          transition: "grid-template-columns 0.28s ease, gap 0.28s ease",
        }}
      >
        {loading &&
          Array.from({ length: skeletonCount }).map((_, i) => (
            <Box key={`event-skel-${i}`}>
              <Skeleton
                variant="rectangular"
                height={isMobile ? 160 : 200}
                sx={{ borderRadius: 2 }}
              />
              <Skeleton height={isMobile ? 28 : 32} sx={{ mt: 1 }} />
              <Skeleton height={20} width={isMobile ? "85%" : "80%"} />
              {!isMobile && <Skeleton height={20} width="60%" />}
            </Box>
          ))}

        {!loading &&
          normalizedEvents.map((event) => (
            <Box
              key={event.id}
              sx={{
                display: "flex",
                width: "100%",
                height: "100%",
                transition: "max-width 0.28s ease",
              }}
            >
              <EventCard {...event} onChange={handleRefresh} maxWidth={cardMaxWidth} />
            </Box>
          ))}

        {!loading && normalizedEvents.length === 0 && (
          <Box sx={{ width: "100%", textAlign: "center", mt: 7, mb: 7 }}>
            <Typography fontSize={24} className="events-empty-text">
              {t("events:states.empty")}
            </Typography>
          </Box>
        )}
      </Box>
    )
  }, [cardMaxWidth, gap, gridTemplateColumns, handleRefresh, isMobile, loading, normalizedEvents])

  return (
    <Layout>
      <PageFadeIn>
        <Box
          sx={{
            width: "100vw",
            minHeight: "100vh",
            bgcolor: "var(--page-bg)",
            color: "var(--page-text)",
            pl: { xs: 2, sm: 4, md: 5, lg: 8 },
            pr: { xs: 4, sm: 6, md: 7, lg: 10 },
            py: { xs: 0.5, sm: 0.5, md: 0.5, lg: 0.5 },
          }}
        >
          <Box
            data-fade
            style={{ "--fade-delay": "80ms" } as CSSProperties}
            display="flex"
            alignItems="center"
            gap={2}
            mb={isMobile ? 1.5 : 3}
            mt={isMobile ? 1.5 : 3}
          >
            <EventNoteIcon color="primary" sx={{ fontSize: 34 }} />
            <Typography
              variant="h4"
              fontWeight={700}
              color="primary.main"
              sx={{ fontSize: "clamp(0.8rem, 5vw, 2.7rem)" }}
            >
              {t("events:pageTitle")}
            </Typography>
          </Box>

          {(user?.role === "admin" || user?.role === "teacher") && (
            <Box
              data-fade
              style={{ "--fade-delay": "140ms" } as CSSProperties}
              sx={{ display: "flex", justifyContent: "flex-start", mb: isMobile ? 1.3 : 2 }}
            >
              <Button
                variant="contained"
                sx={{ fontWeight: 600, fontSize: 16, px: 2.5, borderRadius: 2 }}
                onClick={() => setCreateOpen(true)}
                disabled={imageUploading || loading}
              >
                {t("events:actions.openCreate")}
              </Button>
            </Box>
          )}

          <Tabs
            data-fade
            style={{ "--fade-delay": "200ms" } as CSSProperties}
            value={tab}
            onChange={handleTabChange}
            variant={isMobile ? "scrollable" : "standard"}
            scrollButtons={isMobile ? "auto" : false}
            sx={{
              minHeight: 45,
              "& .MuiTab-root": {
                color: "var(--page-text)",
                fontWeight: 600,
                fontSize: isMobile ? 16 : 20,
                opacity: 1,
                minWidth: isMobile ? 85 : 130,
                textTransform: "none",
                mr: isMobile ? 0.3 : 1.5,
                transition: "color 0.2s",
              },
              "& .Mui-selected": { color: "var(--nav-link)", fontWeight: 700 },
              "& .MuiTabs-indicator": {
                background: "var(--nav-link)",
                height: 3,
                borderRadius: 2,
              },
            }}
            TabIndicatorProps={{ style: { height: 3 } }}
          >
            {tabs.map((tabItem) => (
              <Tab
                key={tabItem.key}
                value={tabItem.key}
                label={t(`events:tabs.${tabItem.key}`)}
                sx={{
                  minHeight: 45,
                  fontWeight: 600,
                  fontSize: isMobile ? 16 : 20,
                  textTransform: "none",
                }}
              />
            ))}
          </Tabs>

          <Stack
            data-fade
            style={{ "--fade-delay": "240ms" } as CSSProperties}
            direction="row"
            spacing={1.5}
            alignItems="center"
            mb={isMobile ? 2 : 5}
            mt={isMobile ? 2 : 3}
            sx={{ flexWrap: "wrap" }}
          >
            <TextField
              label={t("events:filters.search")}
              variant="outlined"
              size="small"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              sx={{
                width: { xs: "100%", md: "min(640px, 48vw)" },
                "& .MuiOutlinedInput-root": {
                  backgroundColor: "var(--card-bg)",
                  borderRadius: 2,
                  "& fieldset": { borderColor: "var(--btn-border)" },
                  "&:hover fieldset": { borderColor: "var(--nav-link)" },
                  "&.Mui-focused fieldset": {
                    borderColor: "var(--nav-link)",
                    boxShadow: "0 0 0 3px rgba(0,94,162,.18)",
                  },
                },
              }}
              InputLabelProps={{
                sx: {
                  color: "var(--secondary-text)",
                  "&.Mui-focused": { color: "var(--nav-link)" },
                },
              }}
              InputProps={{
                startAdornment: (
                  <InputAdornment position="start">
                    <SearchIcon sx={{ color: "var(--secondary-text)" }} fontSize="small" />
                  </InputAdornment>
                ),
                endAdornment: (
                  <InputAdornment position="end" sx={{ gap: 0.5 }}>
                    {search ? (
                      <IconButton
                        aria-label={t("events:aria.clearSearch")}
                        edge="end"
                        onClick={() => setSearch("")}
                        size="small"
                        sx={{
                          color: "var(--secondary-text)",
                          "&:hover": { color: "var(--nav-link)" },
                        }}
                      >
                        <ClearIcon fontSize="small" />
                      </IconButton>
                    ) : null}
                    <IconButton
                      aria-label={t("events:aria.openFilters")}
                      edge="end"
                      onClick={(e) => setFilterAnchor(e.currentTarget)}
                      size="small"
                      sx={{
                        color: "var(--secondary-text)",
                        "&:hover": { color: "var(--nav-link)" },
                      }}
                    >
                      <Badge
                        color="primary"
                        variant={filtersActive ? "dot" : "standard"}
                        overlap="circular"
                        sx={{
                          "& .MuiBadge-badge": {
                            bgcolor: "var(--nav-link)",
                          },
                        }}
                      >
                        <FilterListIcon fontSize="small" />
                      </Badge>
                    </IconButton>
                  </InputAdornment>
                ),
              }}
            />
          </Stack>

          <Popover
            open={filtersOpen}
            anchorEl={filterAnchor}
            onClose={() => setFilterAnchor(null)}
            anchorOrigin={{ vertical: "bottom", horizontal: "right" }}
            transformOrigin={{ vertical: "top", horizontal: "right" }}
            PaperProps={{
              sx: {
                p: 2,
                borderRadius: 2,
                minWidth: 260,
                bgcolor: "var(--card-bg)",
                border: "1px solid var(--glass-border)",
              },
            }}
          >
            <Stack spacing={1.5}>
              <TextField
                label={t("events:filters.type")}
                variant="outlined"
                size="small"
                value={type}
                onChange={(e) => setType(e.target.value)}
                sx={{
                  "& .MuiOutlinedInput-root": {
                    backgroundColor: "var(--card-bg)",
                    "& fieldset": { borderColor: "var(--btn-border)" },
                    "&:hover fieldset": { borderColor: "var(--nav-link)" },
                    "&.Mui-focused fieldset": { borderColor: "var(--nav-link)" },
                  },
                }}
              />
              <TextField
                label={t("events:filters.location")}
                variant="outlined"
                size="small"
                value={location}
                onChange={(e) => setLocation(e.target.value)}
                sx={{
                  "& .MuiOutlinedInput-root": {
                    backgroundColor: "var(--card-bg)",
                    "& fieldset": { borderColor: "var(--btn-border)" },
                    "&:hover fieldset": { borderColor: "var(--nav-link)" },
                    "&.Mui-focused fieldset": { borderColor: "var(--nav-link)" },
                  },
                }}
              />
              <Stack direction="row" spacing={1} justifyContent="flex-end">
                <Button
                  variant="text"
                  onClick={() => {
                    setType("")
                    setLocation("")
                  }}
                >
                  {t("common:buttons.reset")}
                </Button>
                <Button variant="contained" onClick={() => setFilterAnchor(null)}>
                  {t("common:buttons.done")}
                </Button>
              </Stack>
            </Stack>
          </Popover>

          {eventsContent}

          {tab !== "my" && pagination?.has_more ? (
            <Box display="flex" justifyContent="center" mt={4} mb={6}>
              <Button
                variant="outlined"
                size="large"
                onClick={loadMore}
                disabled={loadingMore}
                sx={{
                  px: 3.5,
                  borderRadius: 2,
                  fontWeight: 600,
                }}
              >
                {loadingMore
                  ? t("common:statuses.loading")
                  : t("common:buttons.loadMore", { defaultValue: "Load more" })}
              </Button>
            </Box>
          ) : null}

          <Dialog open={createOpen} onClose={closeCreate}>
            <DialogTitle>{t("events:dialogs.create.title")}</DialogTitle>
            <DialogContent>
              <Stack spacing={2} mt={1} minWidth={isMobile ? "auto" : 340} mb={2}>
                <TextField
                  label={
                    language === "en"
                      ? t("events:form.title_en", {
                          defaultValue: `${t("events:form.title")}${" (English)"}`,
                        })
                      : t("events:form.title")
                  }
                  value={getLocalizedDraftValue("title")}
                  onChange={(e) => updateLocalizedDraftValue("title", e.target.value)}
                  fullWidth
                />
                <TextField
                  label={
                    language === "en"
                      ? t("events:form.description_en", {
                          defaultValue: `${t("events:form.description")}${" (English)"}`,
                        })
                      : t("events:form.description")
                  }
                  value={getLocalizedDraftValue("description")}
                  onChange={(e) => updateLocalizedDraftValue("description", e.target.value)}
                  multiline
                  rows={3}
                  fullWidth
                />
                <TextField
                  label={
                    language === "en"
                      ? t("events:form.type_en", {
                          defaultValue: `${t("events:form.type")}${" (English)"}`,
                        })
                      : t("events:form.type")
                  }
                  value={getLocalizedDraftValue("event_type")}
                  onChange={(e) => updateLocalizedDraftValue("event_type", e.target.value)}
                  fullWidth
                />
                <TextField
                  label={
                    language === "en"
                      ? t("events:form.location_en", {
                          defaultValue: `${t("events:form.location")}${" (English)"}`,
                        })
                      : t("events:form.location")
                  }
                  value={getLocalizedDraftValue("location")}
                  onChange={(e) => updateLocalizedDraftValue("location", e.target.value)}
                  fullWidth
                />
                <TextField
                  label={t("events:form.speaker")}
                  value={eventData.speaker}
                  onChange={(e) => setEventData({ ...eventData, speaker: e.target.value })}
                  fullWidth
                />

                <Button component="label" variant="outlined" disabled={imageUploading}>
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

                {createPreview && (
                  <Box mt={1}>
                    <SmartImage
                      srcRaw={createPreview}
                      alt={t("events:alt.preview")}
                      style={{
                        maxHeight: 140,
                        borderRadius: 8,
                        border: "1px solid #eee",
                        display: "block",
                      }}
                    />
                  </Box>
                )}
                {!createPreview && eventData.image_url && (
                  <Box mt={1}>
                    <SmartImage
                      srcRaw={eventData.image_url}
                      alt={t("events:alt.image")}
                      style={{
                        maxHeight: 140,
                        borderRadius: 8,
                        border: "1px solid #eee",
                        display: "block",
                      }}
                    />
                  </Box>
                )}

                <TextField
                  label={t("events:form.start")}
                  type="datetime-local"
                  value={eventData.starts_at}
                  onChange={(e) => setEventData({ ...eventData, starts_at: e.target.value })}
                  InputLabelProps={{ shrink: true }}
                  fullWidth
                />
                <TextField
                  label={t("events:form.end")}
                  type="datetime-local"
                  value={eventData.ends_at}
                  onChange={(e) => setEventData({ ...eventData, ends_at: e.target.value })}
                  InputLabelProps={{ shrink: true }}
                  error={dateError}
                  helperText={dateError ? t("events:form.errors.endsBeforeStarts") : " "}
                  fullWidth
                />

                <Box display="flex" gap={2} mt={2}>
                  <Button
                    variant="contained"
                    onClick={handleCreateEvent}
                    disabled={
                      !normalizedTitle ||
                      !eventData.starts_at ||
                      !eventData.ends_at ||
                      !normalizedLocation ||
                      imageUploading ||
                      dateError
                    }
                  >
                    {t("common:buttons.create")}
                  </Button>
                  <Button variant="outlined" color="secondary" onClick={closeCreate}>
                    {t("common:buttons.cancel")}
                  </Button>
                </Box>
              </Stack>
            </DialogContent>
          </Dialog>
        </Box>
      </PageFadeIn>
    </Layout>
  )
}

export default Events
