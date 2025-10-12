import {
  FC,
  memo,
  useState,
  useEffect,
  useRef,
  useMemo,
  useCallback,
  useLayoutEffect,
  type MouseEvent as ReactMouseEvent,
} from "react"
import { useNavigate } from "react-router-dom"
import { isAxiosError } from "axios"
import api from "../api/client"
import {
  Typography, Button, Box, Stack, TextField,
  Dialog, DialogTitle, DialogContent, DialogActions,
  IconButton, Menu, MenuItem, useMediaQuery, Tooltip, Snackbar
} from "@mui/material"
import type { DialogProps } from "@mui/material/Dialog"
import PeopleAltIcon from "@mui/icons-material/PeopleAlt"
import PlaceIcon from "@mui/icons-material/Place"
import EventIcon from "@mui/icons-material/Event"
import MoreVertIcon from "@mui/icons-material/MoreVert"
import DeleteIcon from "@mui/icons-material/Delete"
import EditIcon from "@mui/icons-material/Edit"
import CloseIcon from "@mui/icons-material/Close"
import { useAuth } from "../contexts/AuthContext"
import SmartImage from "@/components/SmartImage"

import dayjs from "dayjs"
import utc from "dayjs/plugin/utc"
import timezone from "dayjs/plugin/timezone"
dayjs.extend(utc)
dayjs.extend(timezone)

type EventCardProps = {
  id: number
  title: string
  description: string
  event_type?: string
  location: string
  starts_at: string
  ends_at: string
  created_by: number
  participant_count: number
  files: any[]
  is_active: boolean
  is_registered?: boolean
  my_qr_code?: string
  speaker?: string
  image_url?: string
  onChange?: () => void
}

const normalizeDate = (dt: string) => (dt.length === 16 ? dt + ":00" : dt)

const formatLocalDateTime = (s?: string) => {
  if (!s) return "—"
  const norm = s.replace(" ", "T")
  const withSec = norm.length === 16 ? norm + ":00" : norm
  const d = dayjs(withSec)
  return d.isValid() ? d.format("DD.MM.YYYY HH:mm") : "—"
}

const qrKey = (eventId: number, user: any) => `qr:${eventId}:${user?.id ?? user?.user_id ?? "me"}`
const qrOpenKey = (eventId: number) => `qr:open:${eventId}`

const EventCardComponent: FC<EventCardProps> = ({
  id,
  title,
  description,
  event_type,
  location,
  starts_at,
  ends_at,
  participant_count,
  is_active,
  is_registered = false,
  my_qr_code,
  speaker,
  image_url,
  onChange
}) => {
  const { user } = useAuth()
  const navigate = useNavigate()
  const isMobile = useMediaQuery("(max-width: 600px)")

  const [registered, setRegistered] = useState(is_registered)
  const [count, setCount] = useState(participant_count)
  const [loading, setLoading] = useState(false)

  const [qr, setQr] = useState<string | undefined>(undefined)
  const [qrOpen, setQrOpen] = useState(false)
  const [skipNextClick, setSkipNextClick] = useState(false)

  const [menuAnchor, setMenuAnchor] = useState<null | HTMLElement>(null)
  const [editOpen, setEditOpen] = useState(false)
  const [confirmDeleteOpen, setConfirmDeleteOpen] = useState(false)
  const menuId = useMemo(() => `event-card-menu-${id}`, [id])

  const [editData, setEditData] = useState({
    title,
    description,
    event_type: event_type || "",
    location,
    starts_at,
    ends_at,
    speaker: speaker || "",
    image_url: image_url || ""
  })
  const [newImage, setNewImage] = useState<File | null>(null)
  const [imageLoading, setImageLoading] = useState(false)
  const imageInputRef = useRef<HTMLInputElement>(null)
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)

  const [snack, setSnack] = useState<string>("")

  const eventEnded = useMemo(() => {
    const normalizedEnds = normalizeDate(ends_at)
    const endDate = dayjs(normalizedEnds.replace(" ", "T"))
    return endDate.isValid() && endDate.isBefore(dayjs())
  }, [ends_at])

  const syncRegistrationState = useCallback(async (): Promise<
    "registered" | "unregistered" | null
  > => {
    try {
      const res = await api.get(`/events/${id}`)
      const event = res.data
      const nextRegistered = Boolean(event?.is_registered)
      if (typeof event?.participant_count === "number") {
        setCount(event.participant_count)
      }
      if (nextRegistered) {
        const code = event?.my_qr_code
        if (code) {
          setQr(code)
          try {
            localStorage.setItem(qrKey(id, user), code)
          } catch {}
        }
      } else {
        setQr(undefined)
        try {
          localStorage.removeItem(qrKey(id, user))
        } catch {}
      }
      setRegistered(nextRegistered)
      return nextRegistered ? "registered" : "unregistered"
    } catch {
      return null
    }
  }, [id, user])

  useEffect(() => setRegistered(is_registered), [is_registered])
  useEffect(() => setCount(participant_count), [participant_count])

  useEffect(() => {
    if (!registered) {
      setQr(undefined)
      try {
        localStorage.removeItem(qrKey(id, user))
      } catch {}
      return
    }
    if (my_qr_code) {
      setQr(my_qr_code)
      try {
        localStorage.setItem(qrKey(id, user), my_qr_code)
      } catch {}
    }
  }, [registered, my_qr_code, id, user])

  useEffect(() => {
    if (!registered || qr || my_qr_code) return
    try {
      const stored = localStorage.getItem(qrKey(id, user))
      if (stored) setQr(stored)
    } catch {}
  }, [registered, qr, my_qr_code, id, user])

  useLayoutEffect(() => {
    try {
      const wasOpen = sessionStorage.getItem(qrOpenKey(id)) === "1"
      if (wasOpen) {
        const cached = qr || localStorage.getItem(qrKey(id, user))
        if (cached) setQrOpen(true)
      }
    } catch {}
  }, [id])

  useEffect(() => {
    try {
      if (qrOpen) sessionStorage.setItem(qrOpenKey(id), "1")
      else sessionStorage.removeItem(qrOpenKey(id))
    } catch {}
  }, [qrOpen, id])

  useEffect(() => {
    if (newImage) {
      const url = URL.createObjectURL(newImage)
      setPreviewUrl(url)
      return () => URL.revokeObjectURL(url)
    }
    setPreviewUrl(null)
  }, [newImage])

  const resetImagePick = () => {
    if (previewUrl) URL.revokeObjectURL(previewUrl)
    setPreviewUrl(null)
    setNewImage(null)
    if (imageInputRef.current) imageInputRef.current.value = ""
  }

  const openEditDialog = () => {
    setEditData({
      title,
      description,
      event_type: event_type || "",
      location,
      starts_at,
      ends_at,
      speaker: speaker || "",
      image_url: image_url || ""
    })
    resetImagePick()
    setEditOpen(true)
  }

  const closeEditDialog = () => {
    resetImagePick()
    setEditOpen(false)
  }

  const cardImageUrl = useMemo(
    () => (previewUrl ? previewUrl : editData.image_url || undefined),
    [editData.image_url, previewUrl],
  )
  const [cardImageReady, setCardImageReady] = useState(() => !cardImageUrl)

  useEffect(() => {
    setCardImageReady(!cardImageUrl)
  }, [cardImageUrl])

  const handleCardImageReady = useCallback(() => setCardImageReady(true), [])

  const dateError =
    Boolean(editData.starts_at) &&
    Boolean(editData.ends_at) &&
    new Date(normalizeDate(editData.ends_at)).getTime() < new Date(normalizeDate(editData.starts_at)).getTime()

  const handleRegister = async (e?: React.MouseEvent) => {
    if (e) e.stopPropagation()
    setLoading(true)
    try {
      const res = await api.post("/events/attendance", { event_id: id })
      const code: string = res.data.qr_code
      setRegistered(true)
      setQr(code)
      setCount((c) => c + 1)
      setSnack("Вы зарегистрированы на мероприятие")
      try { localStorage.setItem(qrKey(id, user), code) } catch {}
    } catch (error) {
      const shouldResync =
        isAxiosError(error) &&
        (error.code === "ECONNABORTED" || error.code === "ERR_NETWORK" || !error.response ||
          (typeof error.response?.status === "number" && error.response.status >= 500))

      if (shouldResync) {
        const restored = await syncRegistrationState()
        if (restored === "registered") {
          setSnack("Вы зарегистрированы на мероприятие")
          return
        }
      }

      const detail =
        (isAxiosError(error) && typeof error.response?.data?.detail === "string"
          ? error.response?.data?.detail
          : null) || "Не удалось зарегистрироваться"
      setSnack(detail)
    } finally {
      setLoading(false)
    }
  }

  const handleUnregister = async (e?: React.MouseEvent) => {
    if (e) e.stopPropagation()
    setLoading(true)
    try {
      await api.delete("/events/attendance", { data: { event_id: id } })
      setRegistered(false)
      setQr(undefined)
      setCount((c) => Math.max(0, c - 1))
      setSnack("Регистрация отменена")
      try { localStorage.removeItem(qrKey(id, user)) } catch {}
    } catch (error) {
      const shouldResync =
        isAxiosError(error) &&
        (error.code === "ECONNABORTED" || error.code === "ERR_NETWORK" || !error.response ||
          (typeof error.response?.status === "number" && error.response.status >= 500))

      if (shouldResync) {
        const restored = await syncRegistrationState()
        if (restored === "unregistered") {
          setSnack("Регистрация отменена")
          return
        }
      }

      const detail =
        (isAxiosError(error) && typeof error.response?.data?.detail === "string"
          ? error.response?.data?.detail
          : null) || "Не удалось отменить регистрацию"
      setSnack(detail)
    } finally {
      setLoading(false)
    }
  }

  const handleDelete = async () => {
    setLoading(true)
    try {
      await api.delete(`/events/${id}`)
      try { localStorage.removeItem(qrKey(id, user)) } catch {}
      setSnack("Мероприятие удалено")
      onChange && onChange()
    } catch {
      setSnack("Ошибка удаления")
    } finally {
      setLoading(false)
      setConfirmDeleteOpen(false)
    }
  }

  const handleEdit = async () => {
    setLoading(true)
    try {
      let imgUrl = editData.image_url
      if (newImage) {
        setImageLoading(true)
        const data = new FormData()
        data.append("file", newImage)
        const uploadRes = await api.post(`/events/upload_image`, data, {
          headers: { "Content-Type": "multipart/form-data" }
        })
        imgUrl = uploadRes.data.url
        setImageLoading(false)
      }
      const payload = {
        ...editData,
        image_url: imgUrl,
        starts_at: normalizeDate(editData.starts_at),
        ends_at: normalizeDate(editData.ends_at)
      }
      await api.patch(`/events/${id}`, payload)
      setEditData((prev) => ({ ...prev, image_url: imgUrl }))
      closeEditDialog()
      onChange && onChange()
      setSnack("Сохранено")
    } catch {
      setSnack("Не удалось сохранить")
    } finally {
      setLoading(false)
    }
  }

  const navigateToDetails = useCallback(() => navigate(`/events/${id}`), [id, navigate])

  const handleCardClick = (e: React.MouseEvent<HTMLDivElement>) => {
    if (editOpen) return
    if (skipNextClick) {
      setSkipNextClick(false)
      return
    }
    const target = e.target as HTMLElement
    if (
      target.closest("button") ||
      target.closest("a") ||
      target.closest("input") ||
      target.closest(".MuiInputBase-root") ||
      target.closest('[role="menu"]')
    ) {
      return
    }
    navigateToDetails()
  }

  const handleImageChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) setNewImage(file)
  }

  return (
    <Box
      className="event-card"
      sx={{
        width: "100%",
        maxWidth: 700,
        minHeight: 320,
        borderRadius: { xs: "1.1rem", sm: "1.2rem" },
        background: "var(--card-bg)",
        color: "var(--page-text)",
        position: "relative",
        cursor: editOpen ? "default" : "pointer",
        boxShadow: 5,
        transition: "transform 0.25s ease, box-shadow 0.25s ease",
        willChange: "transform",
        p: { xs: 2, sm: 3 },
        overflow: "hidden",
        "&:hover": !editOpen
          ? {
              transform: isMobile ? "none" : "scale(1.03)",
              boxShadow: "0 12px 28px rgba(0,0,0,0.18)"
            }
          : undefined,
        "&:active": {
          transform: editOpen ? "none" : "scale(0.997)"
        },
        "&:focus-visible": {
          outline: "2px solid var(--nav-link)",
          outlineOffset: "2px"
        },
        pointerEvents: qrOpen ? "none" : "auto",
        filter: qrOpen ? "grayscale(0.12) opacity(0.92)" : "none",
        "@media (prefers-reduced-motion: reduce)": {
          transition: "box-shadow 0.25s ease"
        }
      }}
      role="button"
      tabIndex={0}
      onClick={handleCardClick}
      onKeyDown={(e) => {
        if (!editOpen && (e.key === "Enter" || e.key === " ")) {
          e.preventDefault()
          navigateToDetails()
        }
      }}
    >
      {user && (user.role === "admin" || user.role === "teacher") && (
        <>
          <IconButton
            aria-label="Действия"
            aria-controls={menuAnchor ? menuId : undefined}
            aria-haspopup="true"
            aria-expanded={Boolean(menuAnchor) ? "true" : undefined}
            sx={{
              position: "absolute",
              top: 10,
              right: 10,
              zIndex: 2,
              bgcolor: "rgba(255,255,255,0.82)",
              "&:hover": { bgcolor: "#fff" }
            }}
            onClick={(e) => {
              e.stopPropagation()
              setMenuAnchor(e.currentTarget)
            }}
            size="small"
          >
            <MoreVertIcon />
          </IconButton>
          <Menu
            id={menuId}
            anchorEl={menuAnchor}
            open={Boolean(menuAnchor)}
            onClose={(e) => {
              if (e) (e as any).stopPropagation?.()
              setMenuAnchor(null)
            }}
            anchorOrigin={{ vertical: "bottom", horizontal: "right" }}
            transformOrigin={{ vertical: "top", horizontal: "right" }}
            MenuListProps={{ "aria-labelledby": menuId }}
          >
            <MenuItem
              onClick={(e) => {
                e.stopPropagation()
                setMenuAnchor(null)
                openEditDialog()
              }}
            >
              <EditIcon fontSize="small" sx={{ mr: 1 }} />
              Редактировать
            </MenuItem>
            <MenuItem
              onClick={(e) => {
                e.stopPropagation()
                setMenuAnchor(null)
                setConfirmDeleteOpen(true)
              }}
            >
              <DeleteIcon fontSize="small" sx={{ mr: 1 }} color="error" />
              <span style={{ color: "#d32f2f" }}>Удалить</span>
            </MenuItem>
          </Menu>
        </>
      )}

      <Box mb={2} display="flex" justifyContent="center">
        <Box
          sx={{
            width: "100%",
            height: { xs: 200, sm: 220, md: 260 },
            maxHeight: 280,
            borderRadius: 2,
            border: "1px solid #e0e0e0",
            overflow: "hidden",
            position: "relative",
            background: "linear-gradient(135deg, rgba(30,136,229,0.18), rgba(21,101,192,0.1))",
            transition: "transform 0.25s ease",
            "&:hover": { transform: isMobile ? "none" : "scale(1.01)" },
            display: "flex",
            alignItems: "stretch",
            "& img": {
              display: "block",
              width: "100%",
              height: "100%",
              objectFit: "cover",
              objectPosition: "center",
            },
            "&::after": {
              content: '""',
              position: "absolute",
              inset: 0,
              background: "linear-gradient(120deg, rgba(255,255,255,0.28), rgba(255,255,255,0.05))",
              opacity: cardImageReady ? 0 : 1,
              transition: "opacity 280ms ease",
              pointerEvents: "none",
            },
          }}
        >
          <SmartImage
            srcRaw={cardImageUrl}
            alt="Изображение мероприятия"
            sizes="(min-width: 1200px) 560px, (min-width: 900px) 480px, 100vw"
            style={{
              width: "100%",
              height: "100%",
              display: "block",
              objectFit: "cover",
              objectPosition: "center",
            }}
            draggable={false}
            onClick={(e) => {
              e.stopPropagation()
              navigateToDetails()
            }}
            onLoad={handleCardImageReady}
            onError={handleCardImageReady}
          />
        </Box>
      </Box>

      <Typography variant="h5" fontWeight={800} sx={{ mb: 1, lineHeight: 1.15 }}>
        {title}
      </Typography>

      {speaker && (
        <Typography color="secondary" fontSize={15} fontWeight={600} sx={{ mb: 1 }}>
          Спикер: {speaker}
        </Typography>
      )}

      <Box display="flex" gap={1} alignItems="center" sx={{ mb: 1 }}>
        <EventIcon sx={{ fontSize: 20, color: "var(--nav-link)" }} />
        <Typography color="text.secondary" fontSize={16}>
          {formatLocalDateTime(starts_at)} — {formatLocalDateTime(ends_at)}
        </Typography>
      </Box>

      {eventEnded && (
        <Typography color="error.main" fontWeight={700} sx={{ mb: 1 }}>
          Мероприятие завершено
        </Typography>
      )}

      <Box display="flex" gap={1} alignItems="center" sx={{ mb: 1 }}>
        <PlaceIcon sx={{ fontSize: 20, color: "var(--nav-link)" }} />
        <Typography color="text.secondary" fontSize={16}>
          {location}
        </Typography>
      </Box>

      {event_type && (
        <Typography color="primary" fontSize={15} fontWeight={700} sx={{ mb: 1 }}>
          {event_type}
        </Typography>
      )}

      <Typography
        fontSize={16}
        sx={{ mb: 2, display: "-webkit-box", WebkitLineClamp: 5, WebkitBoxOrient: "vertical", overflow: "hidden" }}
      >
        {description}
      </Typography>

      <Box display="flex" gap={1} alignItems="center" sx={{ mb: 2 }}>
        <PeopleAltIcon sx={{ fontSize: 19, color: "var(--nav-link)" }} />
        <Typography fontSize={15}>Участников: {count}</Typography>
      </Box>

      {is_active && !eventEnded && !registered && user?.role !== "admin" && user?.role !== "teacher" && (
        <Button
          variant="contained"
          color="primary"
          sx={{ fontWeight: 700, borderRadius: 2.2, mt: 1 }}
          onClick={(e) => handleRegister(e)}
          disabled={loading}
        >
          Зарегистрироваться
        </Button>
      )}

      {is_active && !eventEnded && registered && (
        <Box display="flex" alignItems="center" gap={2} mt={2}>
          <Button
            variant="outlined"
            color="error"
            sx={{ fontWeight: 700, borderRadius: 2.2 }}
            onClick={(e) => handleUnregister(e)}
            disabled={loading}
          >
            Отменить регистрацию
          </Button>

          {qr && (
            <>
              <Tooltip title="Открыть QR" arrow>
                <SmartImage
                  srcRaw={`https://api.qrserver.com/v1/create-qr-code/?data=${encodeURIComponent(qr)}&size=600x600`}
                  alt="QR"
                  style={{
                    width: "clamp(52px, 8vw, 76px)",
                    height: "clamp(52px, 8vw, 76px)",
                    borderRadius: 8,
                    background: "#fff",
                    cursor: "pointer",
                    display: "block",
                  }}
                  onClick={(e) => {
                    e.stopPropagation()
                    setQrOpen(true)
                  }}
                />
              </Tooltip>

              <Dialog
                open={qrOpen}
                keepMounted
                disableScrollLock
                transitionDuration={{ enter: 0, exit: 0 }}
                onClose={((event, reason) => {
                  if (reason === "backdropClick") {
                    if (
                      event &&
                      typeof event === "object" &&
                      "stopPropagation" in event &&
                      typeof (event as { stopPropagation?: () => void }).stopPropagation === "function"
                    ) {
                      (event as { stopPropagation?: () => void }).stopPropagation?.()
                    }
                    setSkipNextClick(true)
                  }
                  setQrOpen(false)
                }) as DialogProps["onClose"]}
                PaperProps={{
                  onClick: (event: ReactMouseEvent<HTMLDivElement>) => event.stopPropagation(),
                  sx: {
                    borderRadius: 2,
                    p: { xs: 2, sm: 3 },
                    maxWidth: "min(92vw, 92vh)",
                    width: "fit-content",
                    mx: { xs: 2, sm: "auto" },
                  }
                }}
                BackdropProps={{ sx: { backdropFilter: "blur(2px)" } }}
              >
                <Box display="flex" flexDirection="column" alignItems="center">
                  <Box
                    sx={{
                      p: { xs: 1.5, sm: 2.5 },
                      borderRadius: 2,
                      bgcolor: "#fff",
                      boxShadow: 1,
                      width: "100%",
                      maxWidth: "min(76vw, 76vh, 520px)",
                    }}
                  >
                    <Box
                      component="img"
                      src={`https://api.qrserver.com/v1/create-qr-code/?data=${encodeURIComponent(qr)}&size=600x600`}
                      alt="QR"
                      sx={{
                        width: "min(70vw, 70vh, 460px)",
                        maxWidth: "100%",
                        aspectRatio: "1 / 1",
                        display: "block",
                        userSelect: "none",
                      }}
                      loading="eager"
                      decoding="async"
                    />
                  </Box>
                  <Button sx={{ mt: 2 }} variant="outlined" onClick={() => setQrOpen(false)}>
                    Закрыть
                  </Button>
                </Box>
              </Dialog>
            </>
          )}
        </Box>
      )}

      <Dialog
        open={editOpen}
        onClose={closeEditDialog}
        PaperProps={{ sx: { minWidth: 340, bgcolor: "var(--card-bg)", color: "var(--page-text)" } }}
      >
        <DialogTitle sx={{ display: "flex", alignItems: "center", gap: 1 }}>
          <EditIcon fontSize="small" /> Редактировать мероприятие
        </DialogTitle>
        <DialogContent>
          <Stack spacing={2} mt={1}>
            <TextField
              label="Название"
              value={editData.title}
              onChange={(e) => setEditData({ ...editData, title: e.target.value })}
              fullWidth
            />
            <TextField
              label="Описание"
              value={editData.description}
              onChange={(e) => setEditData({ ...editData, description: e.target.value })}
              multiline
              rows={2}
              fullWidth
            />
            <TextField
              label="Тип"
              value={editData.event_type}
              onChange={(e) => setEditData({ ...editData, event_type: e.target.value })}
              fullWidth
            />
            <TextField
              label="Место"
              value={editData.location}
              onChange={(e) => setEditData({ ...editData, location: e.target.value })}
              fullWidth
            />
            <TextField
              label="Начало"
              type="datetime-local"
              value={editData.starts_at.slice(0, 16)}
              onChange={(e) => setEditData({ ...editData, starts_at: e.target.value })}
              InputLabelProps={{ shrink: true }}
              fullWidth
            />
            <TextField
              label="Окончание"
              type="datetime-local"
              value={editData.ends_at.slice(0, 16)}
              onChange={(e) => setEditData({ ...editData, ends_at: e.target.value })}
              InputLabelProps={{ shrink: true }}
              error={dateError}
              helperText={dateError ? "Окончание не может быть раньше начала" : " "}
              fullWidth
            />
            <TextField
              label="Спикер"
              value={editData.speaker}
              onChange={(e) => setEditData({ ...editData, speaker: e.target.value })}
              fullWidth
            />

            <Box>
              <Button
                component="label"
                variant="contained"
                disabled={imageLoading}
                onClick={(e) => e.stopPropagation()}
              >
                {imageLoading ? "Загрузка..." : "Изменить фото"}
                <input
                  type="file"
                  accept="image/*"
                  hidden
                  ref={imageInputRef}
                  onChange={(e) => {
                    const file = e.target.files?.[0]
                    if (file) setNewImage(file)
                  }}
                  onClick={(e) => e.stopPropagation()}
                />
              </Button>
              {cardImageUrl && (
                <Box mt={1}>
                  <SmartImage
                    srcRaw={cardImageUrl}
                    alt="Предпросмотр изображения"
                    style={{
                      width: 220,
                      maxHeight: 140,
                      objectFit: "cover",
                      borderRadius: 10,
                      border: "1px solid #ddd",
                      display: "block",
                    }}
                  />
                </Box>
              )}
            </Box>
          </Stack>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button variant="outlined" color="secondary" onClick={closeEditDialog} startIcon={<CloseIcon />}>
            Отмена
          </Button>
          <Button
            variant="contained"
            onClick={handleEdit}
            disabled={loading || imageLoading || dateError}
          >
            Сохранить
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog open={confirmDeleteOpen} onClose={() => setConfirmDeleteOpen(false)}>
        <DialogTitle>Удалить мероприятие?</DialogTitle>
        <DialogContent>
          <Typography>Действие необратимо. Подтвердите удаление.</Typography>
        </DialogContent>
        <DialogActions>
          <Button variant="outlined" color="secondary" onClick={() => setConfirmDeleteOpen(false)}>
            Отмена
          </Button>
          <Button variant="contained" color="error" onClick={handleDelete} disabled={loading}>
            <DeleteIcon sx={{ mr: 1 }} /> Удалить
          </Button>
        </DialogActions>
      </Dialog>

      <Snackbar
        open={!!snack}
        message={snack}
        autoHideDuration={2400}
        onClose={() => setSnack("")}
        anchorOrigin={{ vertical: "bottom", horizontal: "center" }}
      />
    </Box>
  )
}

const areEventCardPropsEqual = (prev: EventCardProps, next: EventCardProps) =>
  prev.id === next.id &&
  prev.title === next.title &&
  prev.description === next.description &&
  prev.event_type === next.event_type &&
  prev.location === next.location &&
  prev.starts_at === next.starts_at &&
  prev.ends_at === next.ends_at &&
  prev.participant_count === next.participant_count &&
  prev.is_active === next.is_active &&
  prev.is_registered === next.is_registered &&
  prev.my_qr_code === next.my_qr_code &&
  prev.speaker === next.speaker &&
  prev.image_url === next.image_url &&
  prev.onChange === next.onChange &&
  prev.files === next.files

export default memo(EventCardComponent, areEventCardPropsEqual)