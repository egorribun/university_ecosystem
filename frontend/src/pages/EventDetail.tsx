/**
 * EventDetail — full-page orchestrator for event detail view.
 * Uses TanStack Query, view transition morph, reading progress bar,
 * structured sections, related events, prev/next navigation.
 *
 * Pattern source: pages/NewsDetail.tsx
 */

import { useState, useEffect, useCallback } from "react"
import { useParams, useNavigate } from "@tanstack/react-router"
import { Info as InfoIcon, ArrowLeft as ArrowBackIcon } from "lucide-react"
import { useReducedMotion } from "framer-motion"
import { useAuth } from "@/contexts/AuthContext"
import { useTranslation } from "react-i18next"
import { Button, ConfirmDialog } from "@/components/ui"
import Snackbar from "@/components/ui/Snackbar"
import useMediaQuery from "@/hooks/useMediaQuery"
import { breakpoints } from "@/theme/tokens"
import { cn } from "@/utils/cn"
import { useEventDetailQuery, useEventNavigation } from "@/api/hooks/events"
import { useSwipe } from "@/hooks/useSwipe"
import { useRelatedEvents } from "@/hooks/useRelatedEvents"
import { useEventRegistration } from "@/hooks/useEventRegistration"
import { inferEventCategory } from "@/features/events/categories"
import { setEventsHeroId } from "@/utils/eventsTransition"
import { useQueryClient } from "@tanstack/react-query"
import api from "@/api/client"
import { logError } from "@/app/logger"

// Presentational components
import { EventDetailHeader } from "@/components/events/EventDetailHeader"
import { EventDetailHero } from "@/components/events/EventDetailHero"
import { EventDetailBody } from "@/components/events/EventDetailBody"
import { EventDetailNavigation } from "@/components/events/EventDetailNavigation"
import { RelatedEvents } from "@/components/events/RelatedEvents"
import { EventDetailSkeleton } from "@/components/events/EventDetailSkeleton"
import { EventsBackdrop } from "@/components/events/EventsBackdrop"

export default function EventDetail() {
  const { id } = useParams({ strict: false }) as { id: string }
  const navigate = useNavigate()
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const prefersReducedMotion = useReducedMotion() ?? false
  const isNarrow = useMediaQuery(`(max-width: ${breakpoints.content})`)
  const { t, i18n } = useTranslation(["events", "common"])
  const language: "en" | "ru" = i18n.language?.startsWith("en") ? "en" : "ru"

  /* ── Data fetching ── */
  const { data: event, isLoading, error } = useEventDetailQuery(id)
  const { prevId, nextId, prevTitle, nextTitle } = useEventNavigation(id)

  /* ── Swipe gesture for prev/next navigation ── */
  const swipeHandlers = useSwipe({
    onSwipeLeft: () => {
      if (nextId) navigate({ to: "/events/$id", params: { id: nextId } })
    },
    onSwipeRight: () => {
      if (prevId) navigate({ to: "/events/$id", params: { id: prevId } })
    },
    threshold: 48,
    timeout: 500,
  })
  const category = inferEventCategory(event?.event_type ?? event?.event_type_en)
  const relatedEvents = useRelatedEvents(id, category)

  /* ── Registration ── */
  const registration = useEventRegistration({
    eventId: id,
    user: user ?? null,
    initialRegistered: event?.is_registered ?? false,
    initialParticipantCount: event?.participant_count ?? 0,
    initialQrToken: event?.my_qr_token ?? undefined,
  })

  /* ── View transition: set hero ID for back-nav morph ── */
  useEffect(() => {
    if (id) setEventsHeroId(id)
  }, [id])

  /* ── Local state ── */
  const [snackbar, setSnackbar] = useState("")
  const [_editOpen, setEditOpen] = useState(false)
  const [confirmDeleteOpen, setConfirmDeleteOpen] = useState(false)
  const [deleting, setDeleting] = useState(false)

  const isAdmin = user?.role === "admin" || user?.role === "teacher"

  const refreshEvent = useCallback(async () => {
    await queryClient.invalidateQueries({ queryKey: ["events", "detail", id] })
  }, [queryClient, id])

  /* ── Actions ── */
  const handleBack = () => {
    const canGoBack =
      window.history?.state &&
      typeof window.history.state.idx === "number" &&
      window.history.state.idx > 0
    if (canGoBack) window.history.back()
    else navigate({ to: "/events" })
  }

  const handleShare = useCallback(async () => {
    try {
      if (navigator.share) {
        await navigator.share({
          title: event?.title ?? "",
          url: window.location.href,
        })
      } else {
        await navigator.clipboard.writeText(window.location.href)
        setSnackbar(t("events:detail.messages.linkCopied", { defaultValue: "Link copied" }))
      }
    } catch {
      // User cancelled share or clipboard failed — silent
    }
  }, [event?.title, t])

  const handleDelete = useCallback(async () => {
    setDeleting(true)
    try {
      await api.delete(`/events/${id}`)
      void queryClient.invalidateQueries({ queryKey: ["events"] })
      navigate({ to: "/events" })
    } catch (err) {
      logError("[EventDetail] Delete failed:", err)
      setSnackbar(t("events:card.messages.deleteFailure"))
    } finally {
      setDeleting(false)
      setConfirmDeleteOpen(false)
    }
  }, [id, queryClient, navigate, t])

  /* ── Loading state ── */
  if (isLoading) {
    return (
      <EventDetailSkeleton
        isNarrow={isNarrow}
        prefersReducedMotion={prefersReducedMotion}
      />
    )
  }

  /* ── Error / not found state ── */
  if (error || !event) {
    return (
      <div className="events-theme mx-auto max-w-[42rem] px-4 py-12 text-center">
        <div className="mb-4 inline-flex h-16 w-16 items-center justify-center rounded-full bg-surface-elevated text-text-secondary">
          <InfoIcon size={32} />
        </div>
        <h2 className="mb-2 text-xl font-semibold text-text-primary">
          {t("events:detail.messages.notFound")}
        </h2>
        <Button variant="outline" onClick={() => navigate({ to: "/events" })}>
          {t("common:buttons.back")}
        </Button>
      </div>
    )
  }

  /* ── Render ── */
  return (
    <div className="events-theme aurora-mesh relative w-full min-h-(--h-screen-offset)">
      {/* Reading progress bar (CSS scroll-driven + Firefox JS fallback) */}
      <div className="events-reading-progress" />

      {/* Backdrop decoratives */}
      <EventsBackdrop isNarrow={isNarrow} prefersReducedMotion={prefersReducedMotion} />

      {/* Content */}
      <article
        className="relative z-base max-w-4xl mx-auto px-4 py-6 sm:px-6 md:px-10 lg:px-14"
        {...swipeHandlers}
      >
        {/* Back button */}
        <Button
          onClick={handleBack}
          leadingIcon={<ArrowBackIcon size={18} />}
          variant="glass"
          size="sm"
          className={cn("mb-6 font-semibold", "md:sticky md:top-3 md:z-overlay")}
        >
          {t("common:buttons.back")}
        </Button>

        {/* Header — title, meta, actions */}
        <EventDetailHeader
          title={event.title ?? ""}
          eventType={event.event_type ?? undefined}
          eventTypeEn={event.event_type_en ?? undefined}
          participantCount={registration.participantCount}
          startsAt={event.starts_at ?? undefined}
          endsAt={event.ends_at ?? undefined}
          location={event.location ?? undefined}
          speaker={event.speaker ?? undefined}
          isRegistered={registration.isRegistered}
          isEnded={!event.is_active}
          isAdmin={isAdmin}
          registering={registration.isLoading}
          onShare={() => void handleShare()}
          onRegister={registration.register}
          onUnregister={registration.unregister}
          onEditOpen={() => setEditOpen(true)}
          onDeleteOpen={() => setConfirmDeleteOpen(true)}
        />

        {/* Hero image with view transition + lightbox */}
        {event.image_url && (
          <div className="mt-6">
            <EventDetailHero
              imageUrl={event.image_url}
              title={event.title ?? ""}
            />
          </div>
        )}

        {/* Description */}
        {event.description && (
          <div className="mt-8">
            <p className="whitespace-pre-line text-base leading-relaxed text-text-primary max-w-[65ch]">
              {event.description}
            </p>
          </div>
        )}

        {/* Body — About editor + Files */}
        <div className="mt-8">
          <EventDetailBody
            event={event}
            language={language}
            isAdmin={isAdmin}
            onRefresh={refreshEvent}
            onError={setSnackbar}
            onSuccess={setSnackbar}
          />
        </div>

        {/* Related events */}
        <RelatedEvents items={relatedEvents} />

        {/* Prev/Next navigation */}
        <EventDetailNavigation
          prevId={prevId}
          nextId={nextId}
          prevTitle={prevTitle}
          nextTitle={nextTitle}
        />
      </article>

      {/* Delete confirmation */}
      <ConfirmDialog
        open={confirmDeleteOpen}
        title={t("events:card.dialogs.delete.title")}
        message={t("events:card.dialogs.delete.description")}
        confirmText={t("common:buttons.delete")}
        cancelText={t("common:buttons.cancel")}
        variant="danger"
        onConfirm={() => void handleDelete()}
        onCancel={() => setConfirmDeleteOpen(false)}
        isLoading={deleting}
      />

      {/* Snackbar */}
      <Snackbar open={!!snackbar} message={snackbar} onClose={() => setSnackbar("")} />
    </div>
  )
}
