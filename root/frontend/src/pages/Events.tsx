import Layout from "../components/Layout"
import EventCard from "../components/EventCard"
import { useEffect, useState, useCallback } from "react"
import axios from "../api/axios"
import {
  Box, Tabs, Tab, TextField, Typography, Button,
  Dialog, DialogTitle, DialogContent, Stack, useMediaQuery,
  Skeleton, InputAdornment, IconButton, Popover, Badge
} from "@mui/material"
import EventNoteIcon from "@mui/icons-material/EventNote"
import SearchIcon from "@mui/icons-material/Search"
import FilterListIcon from "@mui/icons-material/FilterList"
import ClearIcon from "@mui/icons-material/Clear"
import { useAuth } from "../contexts/AuthContext"
import { resolveMediaUrl } from "@/utils/media"
import { useSearchParams } from "react-router-dom"

const BACKEND_ORIGIN = import.meta.env.VITE_BACKEND_ORIGIN || ""

const tabs = [
  { key: "active", label: "Актуальные", is_active: true },
  { key: "archive", label: "Архив", is_active: false },
  { key: "my", label: "Мои события" },
] as const

const initialEvent = {
  title: "",
  description: "",
  event_type: "",
  location: "",
  starts_at: "",
  ends_at: "",
  speaker: "",
  image_url: "",
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

  const [events, setEvents] = useState<any[]>([])
  const [tab, setTab] = useState<(typeof tabs)[number]["key"]>("active")
  const [search, setSearch] = useState("")
  const [type, setType] = useState("")
  const [location, setLocation] = useState("")

  const [createOpen, setCreateOpen] = useState(false)
  const [eventData, setEventData] = useState(initialEvent)
  const [imageUploading, setImageUploading] = useState(false)
  const [loading, setLoading] = useState(false)

  const [createPreview, setCreatePreview] = useState<string | null>(null)

  const isMobile = useMediaQuery("(max-width:900px)")

  const [filterAnchor, setFilterAnchor] = useState<HTMLElement | null>(null)
  const filtersOpen = Boolean(filterAnchor)
  const filtersActive = Boolean(type?.trim() || location?.trim())

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

  const fetchEvents = useCallback(async (signal?: AbortSignal) => {
    setLoading(true)
    try {
      const params =
        tab === "my"
          ? undefined
          : {
              is_active: tabs.find((t) => t.key === tab)?.is_active,
              search: dSearch,
              type: dType,
              location: dLocation,
            }

      const res =
        tab === "my"
          ? await axios.get("/events/my", { signal })
          : await axios.get("/events", { params, signal })

      setEvents(Array.isArray(res.data) ? res.data : [])
    } catch (err: any) {
      if (err?.name !== "CanceledError" && err?.code !== "ERR_CANCELED") {
        setEvents([])
      }
    } finally {
      setLoading(false)
    }
  }, [tab, dSearch, dType, dLocation])

  useEffect(() => {
    const ctrl = new AbortController()
    fetchEvents(ctrl.signal)
    return () => ctrl.abort()
  }, [fetchEvents])

  const handleTabChange = (_: any, newValue: typeof tab) => setTab(newValue)

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
      const res = await axios.post("/events/upload_image", formData, {
        headers: { "Content-Type": "multipart/form-data" },
      })
      setEventData((prev) => ({ ...prev, image_url: res.data.url }))
    } finally {
      setImageUploading(false)
    }
  }

  const handleCreateEvent = async () => {
    try {
      const res = await axios.post("/events", {
        ...eventData,
        starts_at: eventData.starts_at,
        ends_at: eventData.ends_at,
      })
      closeCreate()
      setTab("active")
      setEvents((prev) => [res.data, ...prev])
      window.scrollTo({ top: 0, behavior: "smooth" })
    } catch {}
  }

  const handleRefresh = () => {
    if (!loading) fetchEvents()
  }

  const starts = new Date(eventData.starts_at).getTime()
  const ends = new Date(eventData.ends_at).getTime()
  const dateError = !!(eventData.starts_at && eventData.ends_at && ends < starts)

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

  const renderMobileCards = () => (
    <Stack spacing={2} mt={1}>
      {loading &&
        Array.from({ length: 3 }).map((_, i) => (
          <Box key={i} sx={{ p: 0 }}>
            <Skeleton variant="rectangular" height={160} sx={{ borderRadius: 2 }} />
            <Skeleton height={28} sx={{ mt: 1 }} />
            <Skeleton height={20} width="85%" />
          </Box>
        ))}
      {!loading && Array.isArray(events) &&
        events.map((event) => (
          <EventCard key={event.id} {...event} onChange={handleRefresh} />
        ))}
      {!loading && Array.isArray(events) && events.length === 0 && (
        <Typography fontSize={20} color="text.secondary" align="center" mt={8}>
          Нет мероприятий
        </Typography>
      )}
    </Stack>
  )

  return (
    <Layout>
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
            Мероприятия
          </Typography>
        </Box>

        {(user?.role === "admin" || user?.role === "teacher") && (
          <Box sx={{ display: "flex", justifyContent: "flex-start", mb: isMobile ? 1.3 : 2 }}>
            <Button
              variant="contained"
              sx={{ fontWeight: 600, fontSize: 16, px: 2.5, borderRadius: 2 }}
              onClick={() => setCreateOpen(true)}
              disabled={imageUploading || loading}
            >
              Создать мероприятие
            </Button>
          </Box>
        )}

        <Tabs
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
          {tabs.map((t) => (
            <Tab
              key={t.key}
              value={t.key}
              label={t.label}
              sx={{ minHeight: 45, fontWeight: 600, fontSize: isMobile ? 16 : 20, textTransform: "none" }}
            />
          ))}
        </Tabs>

        <Stack
          direction="row"
          spacing={1.5}
          alignItems="center"
          mb={isMobile ? 2 : 5}
          mt={isMobile ? 1 : 2}
        >
          <TextField
            label="Поиск"
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
                  boxShadow: "0 0 0 3px rgba(0,94,162,.18)"
                }
              }
            }}
            InputLabelProps={{
              sx: {
                color: "var(--secondary-text)",
                "&.Mui-focused": { color: "var(--nav-link)" }
              }
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
                      aria-label="Очистить поиск"
                      edge="end"
                      onClick={() => setSearch("")}
                      size="small"
                      sx={{ color: "var(--secondary-text)", "&:hover": { color: "var(--nav-link)" } }}
                    >
                      <ClearIcon fontSize="small" />
                    </IconButton>
                  ) : null}
                  <IconButton
                    aria-label="Фильтры"
                    edge="end"
                    onClick={(e) => setFilterAnchor(e.currentTarget)}
                    size="small"
                    sx={{ color: "var(--secondary-text)", "&:hover": { color: "var(--nav-link)" } }}
                  >
                    <Badge
                      color="primary"
                      variant={filtersActive ? "dot" : "standard"}
                      overlap="circular"
                      sx={{
                        "& .MuiBadge-badge": {
                          bgcolor: "var(--nav-link)"
                        }
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
          PaperProps={{ sx: { p: 2, borderRadius: 2, minWidth: 260, bgcolor: "var(--card-bg)", border: "1px solid var(--glass-border)" } }}
        >
          <Stack spacing={1.5}>
            <TextField
              label="Тип"
              variant="outlined"
              size="small"
              value={type}
              onChange={(e) => setType(e.target.value)}
              sx={{
                "& .MuiOutlinedInput-root": {
                  backgroundColor: "var(--card-bg)",
                  "& fieldset": { borderColor: "var(--btn-border)" },
                  "&:hover fieldset": { borderColor: "var(--nav-link)" },
                  "&.Mui-focused fieldset": { borderColor: "var(--nav-link)" }
                }
              }}
            />
            <TextField
              label="Место"
              variant="outlined"
              size="small"
              value={location}
              onChange={(e) => setLocation(e.target.value)}
              sx={{
                "& .MuiOutlinedInput-root": {
                  backgroundColor: "var(--card-bg)",
                  "& fieldset": { borderColor: "var(--btn-border)" },
                  "&:hover fieldset": { borderColor: "var(--nav-link)" },
                  "&.Mui-focused fieldset": { borderColor: "var(--nav-link)" }
                }
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
                Сбросить
              </Button>
              <Button variant="contained" onClick={() => setFilterAnchor(null)}>
                Готово
              </Button>
            </Stack>
          </Stack>
        </Popover>

        {isMobile ? (
          renderMobileCards()
        ) : (
          <Box
            sx={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))",
              gap: { xs: 2, sm: 3 },
              minHeight: "180px",
            }}
          >
            {loading &&
              Array.from({ length: 6 }).map((_, i) => (
                <Box key={i}>
                  <Skeleton variant="rectangular" height={200} sx={{ borderRadius: 2 }} />
                  <Skeleton height={32} sx={{ mt: 1 }} />
                  <Skeleton height={20} width="80%" />
                  <Skeleton height={20} width="60%" />
                </Box>
              ))}

            {!loading && Array.isArray(events) &&
              events.map((event) => (
                <Box key={event.id} sx={{ display: "flex", width: "100%", height: "100%" }}>
                  <EventCard {...event} onChange={handleRefresh} />
                </Box>
              ))}

            {!loading && Array.isArray(events) && events.length === 0 && (
              <Box sx={{ width: "100%", textAlign: "center", mt: 7, mb: 7 }}>
                <Typography fontSize={24} className="events-empty-text">
                  Нет мероприятий
                </Typography>
              </Box>
            )}
          </Box>
        )}

        <Dialog open={createOpen} onClose={closeCreate}>
          <DialogTitle>Создать мероприятие</DialogTitle>
          <DialogContent>
            <Stack spacing={2} mt={1} minWidth={isMobile ? "auto" : 340} mb={2}>
              <TextField
                label="Название"
                value={eventData.title}
                onChange={(e) => setEventData({ ...eventData, title: e.target.value })}
                fullWidth
              />
              <TextField
                label="Описание"
                value={eventData.description}
                onChange={(e) => setEventData({ ...eventData, description: e.target.value })}
                multiline
                rows={3}
                fullWidth
              />
              <TextField
                label="Тип"
                value={eventData.event_type}
                onChange={(e) => setEventData({ ...eventData, event_type: e.target.value })}
                fullWidth
              />
              <TextField
                label="Место"
                value={eventData.location}
                onChange={(e) => setEventData({ ...eventData, location: e.target.value })}
                fullWidth
              />
              <TextField
                label="Спикер"
                value={eventData.speaker}
                onChange={(e) => setEventData({ ...eventData, speaker: e.target.value })}
                fullWidth
              />

              <Button component="label" variant="outlined" disabled={imageUploading}>
                {imageUploading
                  ? "Загрузка..."
                  : eventData.image_url
                  ? "Изображение выбрано"
                  : "Загрузить изображение"}
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
                  <img
                    src={createPreview}
                    alt="preview"
                    style={{ maxHeight: 140, borderRadius: 8, border: "1px solid #eee" }}
                  />
                </Box>
              )}
              {!createPreview && eventData.image_url && (
                <Box mt={1}>
                  <img
                    src={resolveMediaUrl(eventData.image_url, BACKEND_ORIGIN)}
                    alt="event"
                    style={{ maxHeight: 140, borderRadius: 8, border: "1px solid #eee" }}
                  />
                </Box>
              )}

              <TextField
                label="Начало"
                type="datetime-local"
                value={eventData.starts_at}
                onChange={(e) => setEventData({ ...eventData, starts_at: e.target.value })}
                InputLabelProps={{ shrink: true }}
                fullWidth
              />
              <TextField
                label="Окончание"
                type="datetime-local"
                value={eventData.ends_at}
                onChange={(e) => setEventData({ ...eventData, ends_at: e.target.value })}
                InputLabelProps={{ shrink: true }}
                error={dateError}
                helperText={dateError ? "Окончание не может быть раньше начала" : " "}
                fullWidth
              />

              <Box display="flex" gap={2} mt={2}>
                <Button
                  variant="contained"
                  onClick={handleCreateEvent}
                  disabled={
                    !eventData.title ||
                    !eventData.starts_at ||
                    !eventData.ends_at ||
                    !eventData.location ||
                    imageUploading ||
                    dateError
                  }
                >
                  Создать
                </Button>
                <Button variant="outlined" color="secondary" onClick={closeCreate}>
                  Отмена
                </Button>
              </Box>
            </Stack>
          </DialogContent>
        </Dialog>
      </Box>
    </Layout>
  )
}

export default Events