import React, {
  memo,
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  lazy,
  Suspense,
  type FC,
} from "react"
import { useNavigate } from "react-router-dom"
import { isAxiosError } from "axios"
import api from "../api/client"
import type { Event } from "@/types/Event"
import { Trash2 as DeleteIcon } from "lucide-react"
import { useAuth } from "../contexts/AuthContext"
import { motion } from "framer-motion"
import { cn } from "@/utils/cn"
import { useTranslation } from "react-i18next"
import Dialog from "@/components/Dialog"
import { useSpotlight, SpotlightOverlay } from "@/components/ui/Spotlight"
import useMediaQuery from "@/hooks/useMediaQuery"
import { breakpoints } from "@/theme/tokens"

import dayjs from "dayjs"
import utc from "dayjs/plugin/utc"
import timezone from "dayjs/plugin/timezone"
import relativeTime from "dayjs/plugin/relativeTime"
import "dayjs/locale/ru"

import { Button, Snackbar } from "@/components/ui"
import { useEventRegistration } from "@/hooks/useEventRegistration"

// Sub-components
import { EventMedia } from "./events/EventCard/EventMedia"
import { EventInfo } from "./events/EventCard/EventInfo"
import { EventActions } from "./events/EventCard/EventActions"

const EventEditDialog = lazy(() =>
  import("@/components/events/EventEditDialog").then((m) => ({ default: m.EventEditDialog }))
)
const EventAdminActions = lazy(() =>
  import("./events/EventCard/EventAdminActions").then((m) => ({ default: m.EventAdminActions }))
)

dayjs.extend(utc)
dayjs.extend(timezone)
dayjs.extend(relativeTime)

interface EventCardProps extends Partial<Event> {
  id: string
  animationIndex?: number
  onChange?: () => void
  maxWidth?: string
}

type EventEditDraft = Partial<Event>

const normalizeDate = (d?: string) => (d ? d.replace("T", " ").replace("Z", "") : "")

const EventCardComponent: FC<EventCardProps> = ({
  id,
  title = "",
  title_en = "",
  description = "",
  description_en = "",
  event_type = "",
  event_type_en = "",
  location = "",
  location_en = "",
  starts_at = "",
  ends_at = "",
  participant_count = 0,
  is_active = true,
  is_registered = false,
  my_qr_token,
  speaker = "",
  image_url = "",
  animationIndex = 0,
  onChange,
}) => {
  const { user } = useAuth()
  const navigate = useNavigate()
  const isMobile = useMediaQuery(`(max-width: ${breakpoints.mobile})`)
  const { t, i18n } = useTranslation(["events", "common"])
  const language = i18n.language?.startsWith("en") ? "en" : "ru"

  const [snackbar, setSnackbar] = useState<string>("")
  const spotlight = useSpotlight()
  const [loading, setLoading] = useState(false)

  // Registration Logic Hook
  const {
    isRegistered,
    participantCount,
    qrToken,
    isLoading: regLoading,
    register,
    unregister,
  } = useEventRegistration({
    eventId: id,
    user,
    initialRegistered: is_registered ?? false,
    initialParticipantCount: participant_count ?? 0,
    initialQrToken: my_qr_token ?? undefined,
    onNotify: setSnackbar,
  })

  // Admin and View Logic
  const [menuAnchor, setMenuAnchor] = useState<null | HTMLElement>(null)
  const [editOpen, setEditOpen] = useState(false)
  const [confirmDeleteOpen, setConfirmDeleteOpen] = useState(false)
  const menuId = useMemo(() => `event-card-menu-${id}`, [id])

  const [editData, setEditData] = useState<EventEditDraft>({
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
    speaker,
    image_url,
  })
  const [newImage, setNewImage] = useState<File | null>(null)
  const [imageLoading, setImageLoading] = useState(false)
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  const [cardImageReady, setCardImageReady] = useState(() => !image_url)

  const timeStatus = useMemo(() => {
    const now = dayjs()
    const start = dayjs(normalizeDate(starts_at).replace(" ", "T"))
    const end = dayjs(normalizeDate(ends_at).replace(" ", "T"))

    if (now.isAfter(start) && now.isBefore(end)) return { status: "live" as const }
    if (now.isBefore(start) && start.diff(now, "hour") < 24) {
      return { status: "soon" as const, timeText: start.fromNow(true) }
    }
    return { status: "none" as const }
  }, [starts_at, ends_at])

  const eventEnded = useMemo(() => {
    const end = dayjs(normalizeDate(ends_at).replace(" ", "T"))
    return end.isValid() && end.isBefore(dayjs())
  }, [ends_at])

  useEffect(() => {
    if (newImage) {
      const url = URL.createObjectURL(newImage)
      setPreviewUrl(url)
      return () => URL.revokeObjectURL(url)
    }
    setPreviewUrl(null)
  }, [newImage])

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
        starts_at: normalizeDate(editData.starts_at),
        ends_at: normalizeDate(editData.ends_at),
        image_url: imgUrl,
      }
      await api.patch(`/events/${id}`, payload)
      setEditOpen(false)
      onChange?.()
      setSnackbar(t("events:card.messages.saveSuccess"))
    } catch {
      setSnackbar(t("events:card.messages.saveFailure"))
    } finally {
      setLoading(false)
    }
  }

  const handleDelete = async () => {
    setLoading(true)
    try {
      await api.delete(`/events/${id}`)
      setConfirmDeleteOpen(false)
      onChange?.()
      setSnackbar(t("events:card.messages.deleteSuccess"))
    } catch {
      setSnackbar(t("events:card.messages.deleteFailure"))
    } finally {
      setLoading(false)
    }
  }

  const navigateToDetails = useCallback(() => navigate(`/events/${id}`), [id, navigate])

  const handleCardClick = (e: React.MouseEvent) => {
    if (editOpen) return
    const target = e.target as HTMLElement
    if (target.closest("button") || target.closest("a") || target.closest('[role="menu"]')) return
    navigateToDetails()
  }

  const cardImageUrl = useMemo(() => previewUrl || image_url || undefined, [image_url, previewUrl])

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 16, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{
        duration: 0.45,
        delay: (animationIndex % 10) * 0.06,
        ease: [0.22, 1, 0.36, 1],
      }}
      whileHover={{ y: -4, transition: { duration: 0.2 } }}
      className="w-full"
      onMouseMove={spotlight.onMouseMove}
    >
      <div
        className={cn(
          "card-glass group relative flex flex-col transition-shadow duration-300 ease-out w-full p-fluid-card-p transform-gpu will-change-transform rounded-fluid-lg bg-glass-elevated border-glass-border-subtle shadow-premium",
          editOpen
            ? "cursor-default"
            : "cursor-pointer hover:shadow-glass-strong active:scale-[0.985]"
        )}
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
          className="z-(--z-hide) rounded-[24px]"
        />

        {/* Admin Menu */}
        {user && (user.role === "admin" || user.role === "teacher") && (
          <Suspense
            fallback={
              <div className="absolute top-3 right-3 w-8 h-8 rounded-full bg-glass animate-pulse" />
            }
          >
            <EventAdminActions
              menuAnchor={menuAnchor}
              setMenuAnchor={setMenuAnchor}
              onEdit={() => setEditOpen(true)}
              onDelete={() => setConfirmDeleteOpen(true)}
              menuId={menuId}
            />
          </Suspense>
        )}

        {/* Media Section */}
        <EventMedia
          imageUrl={cardImageUrl || undefined}
          alt={title || ""}
          eventType={event_type || undefined}
          timeStatus={timeStatus}
          isReady={cardImageReady}
          onReady={() => setCardImageReady(true)}
          onImageClick={navigateToDetails}
        />

        {/* Info Section */}
        <EventInfo
          title={title || ""}
          speaker={speaker || undefined}
          startsAt={starts_at || ""}
          endsAt={ends_at || ""}
          location={location || ""}
          description={description || ""}
        />

        {/* Actions Section */}
        <EventActions
          eventId={id}
          isActive={is_active ?? true}
          isEnded={eventEnded}
          isRegistered={isRegistered}
          participantCount={participantCount}
          qrToken={qrToken}
          loading={loading || regLoading}
          onRegister={register}
          onUnregister={unregister}
          userRole={user?.role}
        />

        {/* Dialogs */}
        <Suspense fallback={null}>
          <EventEditDialog
            open={editOpen}
            onClose={() => setEditOpen(false)}
            draft={editData as any}
            setDraft={setEditData}
            onSave={handleEdit}
            loading={loading}
            imageLoading={imageLoading}
            dateError={false} // Simplified for now
            normalizedTitle={title || ""}
            normalizedLocation={location || ""}
            newImage={newImage}
            setNewImage={setNewImage}
            previewUrl={previewUrl}
          />
        </Suspense>

        <Dialog
          open={confirmDeleteOpen}
          onClose={() => setConfirmDeleteOpen(false)}
          title={t("events:card.dialogs.delete.title")}
          footer={
            <>
              <Button variant="outline" onClick={() => setConfirmDeleteOpen(false)}>
                {t("common:buttons.cancel")}
              </Button>
              <Button
                variant="solid"
                onClick={handleDelete}
                disabled={loading}
                className="bg-error-text hover:bg-error-text/90"
              >
                {t("common:buttons.delete")}
              </Button>
            </>
          }
        >
          <p className="text-(--text-primary)">{t("events:card.dialogs.delete.description")}</p>
        </Dialog>

        <Snackbar open={!!snackbar} message={snackbar} onClose={() => setSnackbar("")} />
      </div>
    </motion.div>
  )
}

const areEventCardPropsEqual = (prev: EventCardProps, next: EventCardProps) =>
  prev.id === next.id &&
  prev.title === next.title &&
  prev.description === next.description &&
  prev.location === next.location &&
  prev.image_url === next.image_url &&
  prev.starts_at === next.starts_at &&
  prev.ends_at === next.ends_at &&
  prev.is_registered === next.is_registered &&
  prev.participant_count === next.participant_count

export default memo(EventCardComponent, areEventCardPropsEqual)
