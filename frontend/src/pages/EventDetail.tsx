import { useState, useEffect, useCallback } from "react"
import { useParams, useNavigate } from "react-router-dom"
import {
  Users as PeopleAltIcon,
  Info as InfoIcon,
  ArrowLeft as ArrowBackIcon,
  X as XIcon,
} from "lucide-react"
import { useAuth } from "../contexts/AuthContext"
import Layout from "../components/Layout"
import SmartImage from "@/components/SmartImage"
import type { Event } from "@/types/Event"
import { useTranslation } from "react-i18next"
import dayjs from "dayjs"
import utc from "dayjs/plugin/utc"
import timezone from "dayjs/plugin/timezone"
import { Button, Badge, GlassCard } from "@/components/ui"
import useMediaQuery from "@/hooks/useMediaQuery"
import { breakpoints } from "@/theme/tokens"
import { cn } from "@/utils/cn"
import { EventAboutEditor } from "@/components/events/EventAboutEditor"
import { EventFileManager } from "@/components/events/EventFileManager"
import api from "@/api/client"

dayjs.extend(utc)
dayjs.extend(timezone)

const formatLocalDateTime = (s?: string) => {
  if (!s) return "—"
  const norm = s.replace(" ", "T")
  const withSec = norm.length === 16 ? norm + ":00" : norm
  const d = dayjs(withSec)
  return d.isValid() ? d.format("DD.MM.YYYY HH:mm") : "—"
}

const formatDateSafe = (v?: string) => formatLocalDateTime(v)

const isCanceledRequestError = (err: unknown): boolean => {
  if (typeof err !== "object" || err === null) {
    return false
  }

  const record = err as Record<string, unknown>
  const name = record.name
  const code = record.code

  return (
    (typeof name === "string" && name === "CanceledError") ||
    (typeof code === "string" && code === "ERR_CANCELED")
  )
}

const SNACKBAR_AUTO_HIDE_DURATION = 2500

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
    }, SNACKBAR_AUTO_HIDE_DURATION)
    return () => clearTimeout(timer)
  }, [open, message, onClose])

  if (!open || !message) return null

  return (
    <div className="fixed bottom-6 left-1/2 z-overlay -translate-x-1/2 animate-in slide-in-from-bottom-4 fade-in">
      <div className="flex items-center gap-3 rounded-2xl border border-glass-border bg-surface/(--opacity-heavy) px-5 py-3.5 text-sm font-semibold text-text-primary shadow-premium backdrop-blur-md">
        <span>{message}</span>
        <button onClick={onClose} className="rounded-full p-1 hover:bg-white/(--opacity-dim)">
          <XIcon size={16} />
        </button>
      </div>
    </div>
  )
}

export default function EventDetail() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { user } = useAuth()
  const isMobile = useMediaQuery(`(max-width: ${breakpoints.content})`)
  const { t, i18n } = useTranslation(["events", "common"])
  const language = i18n.language?.startsWith("en") ? "en" : "ru"

  const [event, setEvent] = useState<Event | null>(null)
  const [loading, setLoading] = useState(true)
  const [snackbar, setSnackbar] = useState("")

  const [heroPos, setHeroPos] = useState<"50% 18%" | "50% 38%" | "50% 50%" | string>("50% 38%")
  const handleHeroLoad: React.ReactEventHandler<HTMLImageElement> = (e) => {
    const img = e.currentTarget
    const w = img.naturalWidth || 0
    const h = img.naturalHeight || 0
    if (!w || !h) return
    const r = w / h
    if (r < 0.9) setHeroPos("50% 18%")
    else if (r > 2) setHeroPos("50% 50%")
    else setHeroPos("50% 38%")
  }

  const imageUrl = event?.image_url || ""

  useEffect(() => {
    setHeroPos("50% 38%")
  }, [imageUrl])

  const fetchEvent = useCallback(
    async (signal?: AbortSignal) => {
      const res = await api.get<Event>(`/events/${id}`, signal ? { signal } : undefined)
      return res.data
    },
    [id]
  )

  const refreshEvent = useCallback(
    async (signal?: AbortSignal) => {
      setLoading(true)
      try {
        const data = await fetchEvent(signal)
        if (!signal?.aborted) {
          setEvent(data)
        }
        return data
      } catch (err) {
        if (!isCanceledRequestError(err) && !signal?.aborted) {
          setSnackbar(t("events:detail.messages.loadFailed"))
        }
        throw err
      } finally {
        if (!signal?.aborted) {
          setLoading(false)
        }
      }
    },
    [fetchEvent, t]
  )

  useEffect(() => {
    const controller = new AbortController()
    refreshEvent(controller.signal).catch(() => {})
    return () => controller.abort()
  }, [refreshEvent])

  const handleBack = () => {
    const canGoBack =
      window.history?.state &&
      typeof window.history.state.idx === "number" &&
      window.history.state.idx > 0
    if (canGoBack) navigate(-1)
    else navigate("/events")
  }

  if (loading) {
    return (
      <Layout>
      <Layout>
        <div className="flex min-h-(--h-hero-md) w-full items-center justify-center">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-brand border-t-transparent" />
        </div>
      </Layout>
      </Layout>
    )
  }

  if (!event) {
    return (
      <Layout>
        <div className="mx-auto max-w-2xl px-4 py-12 text-center">
          <div className="mb-4 inline-flex h-16 w-16 items-center justify-center rounded-full bg-surface-elevated text-text-secondary">
            <InfoIcon size={32} />
          </div>
          <h2 className="mb-2 text-xl font-semibold text-text-primary">
            {t("events:detail.messages.notFound")}
          </h2>
          <Button variant="outline" onClick={() => navigate("/events")}>
            {t("common:buttons.back")}
          </Button>
        </div>
      </Layout>
    )
  }

  const BackButtonComponent = (
    <Button
      onClick={handleBack}
      leadingIcon={<ArrowBackIcon size={20} />}
      className={cn(
        "mb-6 w-full font-bold sm:w-auto",
        "bg-linear-to-r from-(--primary-main) via-(--primary-main) to-(--primary-main) text-white",
        "shadow-premium ring-1 ring-white/(--opacity-subtle)",
        "transition-all duration-base transform-gpu",
        "hover:scale-105 hover:shadow-glass-strong",
        "active:scale-95",
        "md:sticky md:top-3 md:z-overlay"
      )}
    >
      {t("common:buttons.back")}
    </Button>
  )

  if (isMobile) {
    return (
      <Layout>
        <div className="w-full min-h-(--h-screen-offset) bg-page px-4 py-4 sm:px-6 md:px-8 lg:px-12">
          {BackButtonComponent}
          <div className="space-y-6">
            <h1 className="text-fluid-h2 font-extrabold text-text-primary sm:text-fluid-h1">
              {event.title}
            </h1>
            <div className="flex flex-wrap items-center gap-2">
              {event.event_type && (
                <Badge size="sm" className="bg-(--primary-main) text-white">
                  {event.event_type}
                </Badge>
              )}
              <Badge
                size="sm"
                leadingIcon={<PeopleAltIcon size={16} className="text-(--primary-main)" />}
                className="border-glass-border bg-brand/(--opacity-faint) text-brand"
              >
                {t("events:card.participants", { count: event.participant_count || 0 })}
              </Badge>
            </div>
            <p className="text-(--fs-base) font-semibold text-text-primary">
              {event.description}
            </p>
            <div className="space-y-2">
              <p className="text-base font-semibold text-text-primary">
                {t("events:detail.fields.location")}: <strong>{event.location}</strong>
              </p>
              <p className="text-base text-text-primary">
                {t("events:detail.fields.date")}:{" "}
                <strong>
                  {formatDateSafe(event.starts_at)} — {formatDateSafe(event.ends_at)}
                </strong>
              </p>
              {event.speaker && (
                <p className="text-(--fs-base) text-text-primary">
                  {t("events:detail.fields.speaker")}: <strong>{event.speaker}</strong>
                </p>
              )}
            </div>
            {imageUrl && (
              <GlassCard intensity="low" radius="md" className="relative w-full aspect-video">
                <SmartImage
                  srcRaw={imageUrl}
                  alt={t("events:alt.image")}
                  onLoad={handleHeroLoad}
                  className="absolute inset-0 block h-full w-full object-cover"
                  style={{ objectPosition: heroPos }}
                />
              </GlassCard>
            )}
            <div>
              <EventAboutEditor
                event={event}
                language={language}
                canEdit={(user?.role === "admin" || user?.role === "teacher") ?? false}
                onUpdate={async () => {
                  await refreshEvent()
                }}
                onError={setSnackbar}
                onSuccess={setSnackbar}
              />

              <EventFileManager
                event={event}
                canEdit={(user?.role === "admin" || user?.role === "teacher") ?? false}
                onUpdate={async () => {
                  await refreshEvent()
                }}
                onError={setSnackbar}
                onSuccess={setSnackbar}
              />
            </div>

            <Snackbar open={!!snackbar} message={snackbar} onClose={() => setSnackbar("")} />
          </div>
        </div>
      </Layout>
    )
  }

  return (
    <Layout>
      <div className="flex w-full min-h-(--h-screen-offset) flex-col bg-page px-4 py-4 sm:px-6 md:px-8 lg:px-12">
        {BackButtonComponent}
        <div className="flex flex-row gap-8 items-start">
          <div className="w-[45%] space-y-6">
            {imageUrl && (
              <GlassCard intensity="low" radius="3xl" className="relative w-full aspect-21/9 rounded-4xl">
                <SmartImage
                  srcRaw={imageUrl}
                  alt={t("events:alt.image")}
                  onLoad={handleHeroLoad}
                  className="absolute inset-0 block h-full w-full object-cover"
                  style={{ objectPosition: heroPos }}
                />
              </GlassCard>
            )}
            <div className="h-px bg-(--glass-border)" />
            <div>
              <EventAboutEditor
                event={event}
                language={language}
                canEdit={(user?.role === "admin" || user?.role === "teacher") ?? false}
                onUpdate={async () => {
                  await refreshEvent()
                }}
                onError={setSnackbar}
                onSuccess={setSnackbar}
              />
            </div>
          </div>

          <div className="flex-1 min-w-0 space-y-4">
            <h1 className="text-4xl font-extrabold text-text-primary sm:text-5xl">
              {event.title}
            </h1>
            <div className="flex flex-wrap items-center gap-3">
              {event.event_type && (
                <Badge size="md" className="bg-(--primary-main) text-white">
                  {event.event_type}
                </Badge>
              )}
              <Badge
                size="md"
                leadingIcon={<PeopleAltIcon size={18} className="text-(--primary-main)" />}
                className="border-(--glass-border) bg-(--primary-main)/(--opacity-faint) text-(--primary-main)"
              >
                {t("events:card.participants", { count: event.participant_count || 0 })}
              </Badge>
            </div>
            <div className="h-px bg-(--glass-border)" />
            <p className="whitespace-pre-line text-(--fs-lg) font-semibold leading-relaxed text-text-primary">
              {event.description}
            </p>
            <div className="h-px bg-(--glass-border)" />
            <p className="text-base font-semibold text-text-primary">
              {t("events:detail.fields.location")}: <strong>{event.location}</strong>
            </p>
            <p className="text-base text-text-primary">
              {t("events:detail.fields.date")}:{" "}
              <strong>
                {formatDateSafe(event.starts_at)} — {formatDateSafe(event.ends_at)}
              </strong>
            </p>
            {event.speaker && (
              <p className="text-base text-text-primary">
                {t("events:detail.fields.speaker")}: <strong>{event.speaker}</strong>
              </p>
            )}

            <EventFileManager
              event={event}
              canEdit={(user?.role === "admin" || user?.role === "teacher") ?? false}
              onUpdate={async () => {
                await refreshEvent()
              }}
              onError={setSnackbar}
              onSuccess={setSnackbar}
            />
          </div>
        </div>

        <Snackbar open={!!snackbar} message={snackbar} onClose={() => setSnackbar("")} />
      </div>
    </Layout>
  )
}
