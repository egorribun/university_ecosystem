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
import type { Event } from "@/types/Event"
import PeopleAltIcon from "@mui/icons-material/PeopleAlt"
import PlaceIcon from "@mui/icons-material/Place"
import EventIcon from "@mui/icons-material/Event"
import MoreVertIcon from "@mui/icons-material/MoreVert"
import DeleteIcon from "@mui/icons-material/Delete"
import EditIcon from "@mui/icons-material/Edit"
import QrCodeIcon from "@mui/icons-material/QrCode"
import { useAuth } from "../contexts/AuthContext"
import SmartImage from "@/components/SmartImage"
import { motion } from "framer-motion"
import { cn } from "@/utils/cn"
import { useTranslation } from "react-i18next"
import { Button, Badge, Tooltip } from "@/components/ui"
import Dialog from "@/components/Dialog"
import { useSpotlight, SpotlightOverlay } from "@/components/ui/Spotlight"
import useMediaQuery from "@/hooks/useMediaQuery"

import dayjs from "dayjs"
import utc from "dayjs/plugin/utc"
import timezone from "dayjs/plugin/timezone"
import { EventEditDialog, type EventEditDraft } from "./events/EventEditDialog"
import { EventQrDialog } from "./events/EventQrDialog"

dayjs.extend(utc)
dayjs.extend(timezone)

type EventCardProps = {
  id: string
  title: string
  description?: string | null
  title_en?: string | null
  description_en?: string | null
  event_type?: string | null
  event_type_en?: string | null
  location?: string | null
  location_en?: string | null
  starts_at: string
  ends_at: string
  created_by: string | unknown
  participant_count: number
  files?: Event["files"]
  is_active: boolean
  is_registered?: boolean | null
  my_qr_token?: string | null
  speaker?: string | null
  image_url?: string | null
  about?: string | null
  about_en?: string | null
  onChange?: () => void
  maxWidth?: number | string
  animationIndex?: number
}

const normalizeDate = (dt: string) => (dt.length === 16 ? dt + ":00" : dt)

const formatLocalDateTime = (s?: string) => {
  if (!s) return "—"
  const norm = s.replace(" ", "T")
  const withSec = norm.length === 16 ? norm + ":00" : norm
  const d = dayjs(withSec)
  return d.isValid() ? d.format("DD.MM.YYYY HH:mm") : "—"
}

const getTimeStatus = (
  starts_at: string,
  ends_at: string
): { status: "soon" | "live" | "ended" | "upcoming"; timeText?: string } => {
  const now = dayjs()
  const start = dayjs(starts_at.replace(" ", "T"))
  const end = dayjs(ends_at.replace(" ", "T"))

  if (!start.isValid() || !end.isValid()) return { status: "upcoming" }

  if (now.isAfter(end)) return { status: "ended" }
  if (now.isAfter(start) && now.isBefore(end)) return { status: "live" }

  const hoursUntil = start.diff(now, "hour")
  const minutesUntil = start.diff(now, "minute")

  if (hoursUntil < 24 && hoursUntil >= 1) {
    return { status: "soon", timeText: `${hoursUntil}ч` }
  }
  if (minutesUntil < 60 && minutesUntil > 0) {
    return { status: "soon", timeText: `${minutesUntil}мин` }
  }

  return { status: "upcoming" }
}

const qrKey = (eventId: string, user: any) => `qr:${eventId}:${user?.id ?? user?.user_id ?? "me"}`
const qrOpenKey = (eventId: string) => `qr:open:${eventId}`
const regKey = (eventId: string, userId: number | string | undefined) =>
  `event:reg:${eventId}:${userId ?? "anon"}`

function Snackbar({
  open,
  message,
  onClose,
}: {
  open: boolean
  message: string
  onClose: () => void
}) {
  useEffect(() => {
    if (!open || !message) return
    const timer = setTimeout(() => {
      onClose()
    }, 2400)
    return () => clearTimeout(timer)
  }, [open, message, onClose])

  if (!open || !message) return null

  return (
    <div className="fixed bottom-6 left-1/2 z-50 -translate-x-1/2 animate-in slide-in-from-bottom-4 fade-in">
      <div className="rounded-[1.25rem] border border-[color:color-mix(in_srgb,white_12%,var(--nav-link)_88%)] bg-[color:color-mix(in_srgb,var(--card-bg)_98%,white_2%)] px-5 py-3.5 text-sm font-semibold text-[color:var(--page-text)] shadow-[0_8px_24px_rgba(0,0,0,0.12),0_2px_8px_rgba(0,0,0,0.08)] backdrop-blur-md">
        {message}
      </div>
    </div>
  )
}

const EventCardComponent: FC<EventCardProps> = ({
  id,
  title,
  title_en,
  description,
  description_en,
  event_type,
  event_type_en,
  location,
  location_en,
  starts_at,
  ends_at,
  participant_count,
  is_active,
  is_registered = false,
  my_qr_token,
  speaker,
  image_url,
  about,
  about_en,
  onChange,
  maxWidth,
  animationIndex = 0,
}) => {
  const { user } = useAuth()
  const navigate = useNavigate()
  const isMobile = useMediaQuery("(max-width: 600px)")
  const { t, i18n } = useTranslation(["events", "common"])
  const language = i18n.language?.startsWith("en") ? "en" : "ru"

  // Time status for indicators
  const timeStatus = useMemo(() => getTimeStatus(starts_at, ends_at), [starts_at, ends_at])

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
  const menuRef = useRef<HTMLDivElement>(null)

  const [editData, setEditData] = useState<EventEditDraft>({
    title: title ?? "",
    title_en: title_en ?? "",
    description: description ?? "",
    description_en: description_en ?? "",
    event_type: event_type ?? "",
    event_type_en: event_type_en ?? "",
    location: location ?? "",
    location_en: location_en ?? "",
    starts_at,
    ends_at,
    speaker: speaker ?? "",
    image_url: image_url ?? "",
  })
  const [newImage, setNewImage] = useState<File | null>(null)
  const [imageLoading, setImageLoading] = useState(false)
  const imageInputRef = useRef<HTMLInputElement>(null)
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)

  const [snack, setSnack] = useState<string>("")
  const spotlight = useSpotlight()

  useEffect(() => {
    if (!menuAnchor) return
    const handleClickOutside = (event: MouseEvent) => {
      if (
        menuRef.current &&
        !menuRef.current.contains(event.target as Node) &&
        menuAnchor &&
        !menuAnchor.contains(event.target as Node)
      ) {
        setMenuAnchor(null)
      }
    }
    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setMenuAnchor(null)
      }
    }
    document.addEventListener("mousedown", handleClickOutside)
    document.addEventListener("keydown", handleEscape)
    return () => {
      document.removeEventListener("mousedown", handleClickOutside)
      document.removeEventListener("keydown", handleEscape)
    }
  }, [menuAnchor])

  const getLocalizedEditValue = (field: "title" | "description" | "event_type" | "location") => {
    const key = (language === "en" ? `${field}_en` : field) as keyof EventEditDraft
    return editData[key]
  }

  const updateLocalizedEditValue = (
    field: "title" | "description" | "event_type" | "location",
    value: string
  ) => {
    const key = (language === "en" ? `${field}_en` : field) as keyof EventEditDraft
    setEditData((prev) => ({ ...prev, [key]: value }))
  }

  const normalizedEditTitle = editData.title.trim() || editData.title_en.trim()
  const normalizedEditLocation = editData.location.trim() || editData.location_en.trim()

  const eventEnded = useMemo(() => {
    const normalizedEnds = normalizeDate(ends_at)
    const endDate = dayjs(normalizedEnds.replace(" ", "T"))
    return endDate.isValid() && endDate.isBefore(dayjs())
  }, [ends_at])

  const syncRegistrationState = useCallback(async (): Promise<
    "registered" | "unregistered" | null
  > => {
    try {
      const res = await api.get<Event>(`/events/${id}`)
      const event = res.data
      const nextRegistered = Boolean(event?.is_registered)
      if (typeof event?.participant_count === "number") {
        setCount(event.participant_count)
      }
      if (nextRegistered) {
        const code = event?.my_qr_token
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

  // Restore cached registration state on mount
  useEffect(() => {
    if (!user?.id) return
    try {
      const cached = localStorage.getItem(regKey(id, user.id))
      if (cached === "1" && !is_registered) {
        setRegistered(true)
      }
    } catch {}
  }, [id, user?.id, is_registered])

  // Persist registration state to localStorage
  useEffect(() => {
    if (!user?.id) return
    try {
      if (registered) {
        localStorage.setItem(regKey(id, user.id), "1")
      } else {
        localStorage.removeItem(regKey(id, user.id))
      }
    } catch {}
  }, [registered, id, user?.id])

  useEffect(() => {
    if (!registered) {
      setQr(undefined)
      try {
        localStorage.removeItem(qrKey(id, user))
      } catch {}
      return
    }
    if (my_qr_token) {
      setQr(my_qr_token)
      try {
        localStorage.setItem(qrKey(id, user), my_qr_token)
      } catch {}
    }
  }, [registered, my_qr_token, id, user])

  useEffect(() => {
    if (!registered || qr || my_qr_token) return
    try {
      const stored = localStorage.getItem(qrKey(id, user))
      if (stored) setQr(stored)
    } catch {}
  }, [registered, qr, my_qr_token, id, user])

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
      title: title ?? "",
      title_en: title_en ?? "",
      description: description ?? "",
      description_en: description_en ?? "",
      event_type: event_type ?? "",
      event_type_en: event_type_en ?? "",
      location: location ?? "",
      location_en: location_en ?? "",
      starts_at,
      ends_at,
      speaker: speaker ?? "",
      image_url: image_url ?? "",
    })
    resetImagePick()
    setEditOpen(true)
  }

  const closeEditDialog = () => {
    resetImagePick()
    setEditOpen(false)
  }

  const cardImageUrl = useMemo(
    () => (previewUrl ? previewUrl : image_url || undefined),
    [image_url, previewUrl]
  )
  const [cardImageReady, setCardImageReady] = useState(() => !cardImageUrl)

  useEffect(() => {
    setCardImageReady(!cardImageUrl)
  }, [cardImageUrl])

  const handleCardImageReady = useCallback(() => setCardImageReady(true), [])

  const dateError =
    Boolean(editData.starts_at) &&
    Boolean(editData.ends_at) &&
    new Date(normalizeDate(editData.ends_at)).getTime() <
      new Date(normalizeDate(editData.starts_at)).getTime()

  const handleRegister = async (e?: React.MouseEvent) => {
    if (e) e.stopPropagation()
    setLoading(true)
    try {
      const res = await api.post<{ qr_code: string }>("/events/attendance", { event_id: id })
      const code: string = res.data.qr_code
      setRegistered(true)
      setQr(code)
      setCount((c) => c + 1)
      setSnack(t("events:card.messages.registerSuccess"))
      try {
        localStorage.setItem(qrKey(id, user), code)
      } catch {}
    } catch (error) {
      const shouldResync =
        isAxiosError(error) &&
        (error.code === "ECONNABORTED" ||
          error.code === "ERR_NETWORK" ||
          !error.response ||
          (typeof error.response?.status === "number" && error.response.status >= 500))

      if (shouldResync) {
        const restored = await syncRegistrationState()
        if (restored === "registered") {
          setSnack(t("events:card.messages.registerSuccess"))
          return
        }
      }

      const detail =
        (isAxiosError(error) && typeof error.response?.data?.detail === "string"
          ? error.response?.data?.detail
          : null) || t("events:card.messages.registerFailure")
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
      setSnack(t("events:card.messages.unregisterSuccess"))
      try {
        localStorage.removeItem(qrKey(id, user))
      } catch {}
    } catch (error) {
      const shouldResync =
        isAxiosError(error) &&
        (error.code === "ECONNABORTED" ||
          error.code === "ERR_NETWORK" ||
          !error.response ||
          (typeof error.response?.status === "number" && error.response.status >= 500))

      if (shouldResync) {
        const restored = await syncRegistrationState()
        if (restored === "unregistered") {
          setSnack(t("events:card.messages.unregisterSuccess"))
          return
        }
      }

      const detail =
        (isAxiosError(error) && typeof error.response?.data?.detail === "string"
          ? error.response?.data?.detail
          : null) || t("events:card.messages.unregisterFailure")
      setSnack(detail)
    } finally {
      setLoading(false)
    }
  }

  const handleDelete = async () => {
    setLoading(true)
    try {
      await api.delete(`/events/${id}`)
      try {
        localStorage.removeItem(qrKey(id, user))
      } catch {}
      setSnack(t("events:card.messages.deleteSuccess"))
      onChange && onChange()
    } catch {
      setSnack(t("events:card.messages.deleteFailure"))
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
        const uploadRes = await api.post<{ url: string }>(`/events/upload_image`, data, {
          headers: { "Content-Type": "multipart/form-data" },
        })
        imgUrl = uploadRes.data.url
        setImageLoading(false)
      }
      const payload = {
        ...editData,
        title: normalizedEditTitle,
        location: normalizedEditLocation,
        image_url: imgUrl,
        starts_at: normalizeDate(editData.starts_at),
        ends_at: normalizeDate(editData.ends_at),
      }
      await api.patch(`/events/${id}`, payload)
      setEditData((prev) => ({ ...prev, image_url: imgUrl }))
      closeEditDialog()
      onChange && onChange()
      setSnack(t("events:card.messages.saveSuccess"))
    } catch {
      setSnack(t("events:card.messages.saveFailure"))
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
      target.closest('[role="menu"]')
    ) {
      return
    }
    navigateToDetails()
  }

  const hoveringDisabled = editOpen || qrOpen

  const entranceEase = [0.22, 1, 0.36, 1] as const

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 16, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{
        duration: 0.45,
        delay: (animationIndex % 10) * 0.06,
        ease: entranceEase,
      }}
      whileHover={{ y: -4, transition: { duration: 0.2 } }}
      className="w-full"
      onMouseMove={spotlight.onMouseMove}
    >
      <div
        className={cn(
          "card-glass group relative flex flex-col transition-[box-shadow] duration-300 ease-out w-full p-5 transform-gpu will-change-transform",
          hoveringDisabled
            ? "cursor-default"
            : "cursor-pointer hover:shadow-glass-strong active:scale-[0.985]"
        )}
        style={{ width: "100%" }}
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
        <SpotlightOverlay
          mouseX={spotlight.mouseX}
          mouseY={spotlight.mouseY}
          className="z-0 rounded-[24px]"
        />
        {/* Admin menu */}
        {user && (user.role === "admin" || user.role === "teacher") && (
          <>
            <button
              type="button"
              aria-label={t("events:card.aria.actions")}
              aria-controls={menuAnchor ? menuId : undefined}
              aria-haspopup="true"
              aria-expanded={Boolean(menuAnchor) ? "true" : undefined}
              className="absolute top-2.5 right-2.5 z-[2] rounded-full bg-white/82 p-1.5 text-[color:var(--page-text)] shadow-surface transition-colors hover:bg-white"
              onClick={(e) => {
                e.stopPropagation()
                setMenuAnchor(e.currentTarget)
              }}
            >
              <MoreVertIcon className="h-5 w-5" />
            </button>
            {menuAnchor && (
              <div
                ref={menuRef}
                className="absolute right-0 top-12 z-50 min-w-[160px] rounded-ue-lg border border-[color:var(--glass-border)] bg-[color:var(--card-bg)] shadow-surface-strong"
              >
                <div className="py-1">
                  <button
                    type="button"
                    className="flex w-full items-center gap-2 px-4 py-2 text-sm text-[color:var(--page-text)] transition-colors hover:bg-[color:var(--option-bg)]"
                    onClick={(e) => {
                      e.stopPropagation()
                      setMenuAnchor(null)
                      openEditDialog()
                    }}
                  >
                    <EditIcon className="h-4 w-4" />
                    {t("common:buttons.edit")}
                  </button>
                  <button
                    type="button"
                    className="flex w-full items-center gap-2 px-4 py-2 text-sm text-red-500 transition-colors hover:bg-[color:var(--option-bg)]"
                    onClick={(e) => {
                      e.stopPropagation()
                      setMenuAnchor(null)
                      setConfirmDeleteOpen(true)
                    }}
                  >
                    <DeleteIcon className="h-4 w-4" />
                    {t("common:buttons.delete")}
                  </button>
                </div>
              </div>
            )}
          </>
        )}

        {/* Image */}
        <div className="mb-4">
          <div
            className={cn(
              "relative w-full overflow-hidden rounded-[14px]",
              "aspect-[16/9] max-h-[200px]",
              "bg-gradient-to-br from-[color:color-mix(in_srgb,var(--nav-link)_20%,var(--card-bg)_80%)] to-[color:color-mix(in_srgb,var(--nav-link)_10%,var(--card-bg)_90%)]",
              "border border-[color:color-mix(in_srgb,var(--nav-link)_12%,transparent_88%)]"
            )}
          >
            <SmartImage
              srcRaw={cardImageUrl}
              alt={t("events:alt.image")}
              sizes="(min-width: 1200px) 400px, (min-width: 900px) 350px, 100vw"
              className="block h-full w-full object-cover object-center"
              draggable={false}
              onClick={(e) => {
                e.stopPropagation()
                navigateToDetails()
              }}
              onLoad={handleCardImageReady}
              onError={handleCardImageReady}
            />
            {/* Gradient overlay for depth */}
            <div className="absolute inset-0 bg-gradient-to-t from-black/20 via-transparent to-white/5 pointer-events-none" />
            {/* Event type badge on image */}
            {event_type && (
              <div className="absolute top-3 left-3 px-3 py-1.5 rounded-lg bg-black/50 backdrop-blur-md border border-white/20 shadow-lg">
                <span className="text-xs font-semibold text-white">{event_type}</span>
              </div>
            )}
            {/* Status indicators */}
            {timeStatus.status === "live" && (
              <div className="absolute top-3 right-3 px-3 py-1.5 rounded-lg bg-green-500/90 backdrop-blur-sm shadow-lg flex items-center gap-1.5">
                <span className="relative flex h-2 w-2">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-white opacity-75" />
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-white" />
                </span>
                <span className="text-xs font-bold text-white">LIVE</span>
              </div>
            )}
            {timeStatus.status === "soon" && timeStatus.timeText && (
              <div className="absolute top-3 right-3 px-3 py-1.5 rounded-lg bg-amber-500/90 backdrop-blur-sm shadow-lg flex items-center gap-1.5">
                <span className="text-xs font-bold text-white">⏱ Через {timeStatus.timeText}</span>
              </div>
            )}
            {!cardImageReady && (
              <div className="absolute inset-0 bg-gradient-to-br from-[color:color-mix(in_srgb,var(--nav-link)_15%,var(--card-bg)_85%)] to-[color:var(--card-bg)] animate-pulse" />
            )}
          </div>
        </div>

        {/* Title */}
        <h3 className="mb-2 text-xl font-extrabold leading-tight text-[color:var(--page-text)] sm:text-2xl">
          {title}
        </h3>

        {/* Speaker */}
        {speaker && (
          <p className="mb-2 text-[15px] font-semibold text-[color:var(--secondary-text)]">
            {t("events:form.speaker")}: {speaker}
          </p>
        )}

        {/* Date */}
        <div className="mb-2 flex items-center gap-2 group/date">
          <Tooltip content={t("events:form.dates")}>
            <EventIcon className="h-5 w-5 text-[color:var(--nav-link)] transition-transform group-hover/date:scale-110" />
          </Tooltip>
          <span className="text-base text-[color:var(--secondary-text)]">
            {formatLocalDateTime(starts_at)} — {formatLocalDateTime(ends_at)}
          </span>
        </div>

        {/* Location */}
        <div className="mb-2 flex items-center gap-2 group/loc">
          <Tooltip content={t("events:form.location")}>
            <PlaceIcon className="h-5 w-5 text-[color:var(--nav-link)] transition-transform group-hover/loc:scale-110" />
          </Tooltip>
          <span className="text-base text-[color:var(--secondary-text)]">{location}</span>
        </div>

        {/* Divider */}
        <div className="my-3 h-px bg-gradient-to-r from-transparent via-[color:color-mix(in_srgb,var(--nav-link)_20%,transparent_80%)] to-transparent" />

        {/* Description */}
        <p className="mb-4 line-clamp-3 text-base text-[color:var(--page-text)] flex-grow-0">
          {description}
        </p>

        <div className="mt-auto">
          {/* Participants */}
          <div className="mb-4 flex items-center gap-2 group/part">
            <Tooltip content={t("events:form.participants")}>
              <PeopleAltIcon className="h-[19px] w-[19px] text-[color:var(--nav-link)] transition-transform group-hover/part:scale-110" />
            </Tooltip>
            <span className="text-[15px] text-[color:var(--page-text)]">
              {t("events:card.participants", { count })}
            </span>
          </div>

          {/* Ended status - at bottom in red */}
          {eventEnded && (
            <span className="inline-flex mb-4 py-1.5 px-3 rounded-lg bg-red-500/10 border border-red-500/30 text-sm font-semibold text-red-500">
              {t("events:card.statuses.ended")}
            </span>
          )}

          {/* Register button */}
          {is_active &&
            !eventEnded &&
            !registered &&
            user?.role !== "admin" &&
            user?.role !== "teacher" && (
              <Button
                variant="solid"
                onClick={(e) => handleRegister(e)}
                disabled={loading}
                className="mt-2 font-bold relative overflow-hidden shadow-[0_4px_16px_-4px_color-mix(in_srgb,var(--nav-link)_40%,transparent_60%)] hover:shadow-[0_6px_20px_-4px_color-mix(in_srgb,var(--nav-link)_50%,transparent_50%)] transition-shadow animate-pulse-shadow"
              >
                {t("events:card.actions.register")}
              </Button>
            )}

          {/* Unregister and QR */}
          {is_active && !eventEnded && registered && (
            <div className="mt-4 flex flex-wrap items-center gap-4">
              <Button variant="outline" onClick={(e) => handleUnregister(e)} disabled={loading}>
                {t("events:card.actions.unregister")}
              </Button>

              {qr && (
                <>
                  <Tooltip content={t("events:card.actions.openQr")}>
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation()
                        setQrOpen(true)
                      }}
                      className="relative flex items-center justify-center p-3 sm:p-4 rounded-xl sm:rounded-2xl bg-gradient-to-br from-[color:var(--nav-link)] to-[color:color-mix(in_srgb,var(--nav-link)_80%,#3b82f6_20%)] hover:from-[color:color-mix(in_srgb,var(--nav-link)_90%,white_10%)] hover:to-[color:color-mix(in_srgb,var(--nav-link)_70%,#3b82f6_30%)] border border-white/20 shadow-[0_4px_16px_-4px_color-mix(in_srgb,var(--nav-link)_50%,transparent_50%),inset_0_1px_0_rgba(255,255,255,0.15)] transition-all duration-300 hover:scale-105 hover:shadow-[0_8px_24px_-4px_color-mix(in_srgb,var(--nav-link)_60%,transparent_40%)] active:scale-95 group/qr overflow-hidden"
                    >
                      {/* Shimmer effect */}
                      <div className="absolute inset-0 bg-gradient-to-r from-transparent via-white/10 to-transparent -translate-x-full group-hover/qr:translate-x-full transition-transform duration-700 ease-out" />
                      <QrCodeIcon className="w-7 h-7 sm:w-8 sm:h-8 text-white drop-shadow-sm relative z-10" />
                    </button>
                  </Tooltip>

                  <EventQrDialog
                    open={qrOpen}
                    onClose={() => {
                      setSkipNextClick(true)
                      setQrOpen(false)
                    }}
                    qr={qr}
                  />
                </>
              )}
            </div>
          )}
        </div>

        <EventEditDialog
          open={editOpen}
          onClose={closeEditDialog}
          draft={editData}
          setDraft={setEditData}
          onSave={handleEdit}
          loading={loading}
          imageLoading={imageLoading}
          dateError={dateError}
          normalizedTitle={normalizedEditTitle}
          normalizedLocation={normalizedEditLocation}
          newImage={newImage}
          setNewImage={setNewImage}
          previewUrl={previewUrl}
        />

        {/* Delete confirmation dialog */}
        <Dialog
          open={confirmDeleteOpen}
          onClose={() => setConfirmDeleteOpen(false)}
          title={t("events:card.dialogs.delete.title")}
          footer={
            <>
              <Button
                variant="outline"
                onClick={() => setConfirmDeleteOpen(false)}
                className="w-full sm:w-auto"
              >
                {t("common:buttons.cancel")}
              </Button>
              <Button
                variant="solid"
                onClick={handleDelete}
                disabled={loading}
                leadingIcon={<DeleteIcon />}
                className="w-full bg-red-500 hover:bg-red-600 sm:w-auto"
              >
                {t("common:buttons.delete")}
              </Button>
            </>
          }
          footerClassName="flex-col-reverse gap-3 sm:flex-row"
        >
          <p className="text-[color:var(--page-text)]">
            {t("events:card.dialogs.delete.description")}
          </p>
        </Dialog>

        <Snackbar open={!!snack} message={snack} onClose={() => setSnack("")} />
      </div>
    </motion.div>
  )
}

const areEventCardPropsEqual = (prev: EventCardProps, next: EventCardProps) =>
  prev.id === next.id &&
  prev.title === next.title &&
  prev.title_en === next.title_en &&
  prev.description === next.description &&
  prev.description_en === next.description_en &&
  prev.event_type === next.event_type &&
  prev.event_type_en === next.event_type_en &&
  prev.location === next.location &&
  prev.location_en === next.location_en &&
  prev.starts_at === next.starts_at &&
  prev.ends_at === next.ends_at &&
  prev.participant_count === next.participant_count &&
  prev.is_active === next.is_active &&
  prev.is_registered === next.is_registered &&
  prev.my_qr_token === next.my_qr_token &&
  prev.speaker === next.speaker &&
  prev.image_url === next.image_url &&
  prev.about === next.about &&
  prev.about_en === next.about_en &&
  prev.onChange === next.onChange &&
  prev.files === next.files

export default memo(EventCardComponent, areEventCardPropsEqual)
