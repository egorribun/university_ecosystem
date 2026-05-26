/**
 * EventDetail — full-page orchestrator for event detail view.
 * Uses TanStack Query, view transition morph, reading progress bar,
 * structured sections, related events, prev/next navigation.
 *
 * Pattern source: pages/NewsDetail.tsx
 */

import { useState, useEffect, useCallback, useRef } from "react"
import { useParams, useNavigate } from "@tanstack/react-router"
import { Info as InfoIcon, ArrowLeft as ArrowBackIcon } from "lucide-react"
import { useAuth } from "@/contexts/AuthContext"
import { useTranslation } from "react-i18next"
import { Button, ConfirmDialog } from "@/components/ui"
import Snackbar from "@/components/ui/Snackbar"
import { SEO } from "@/components/ui/SEO"
import useMediaQuery from "@/hooks/useMediaQuery"
import { breakpoints } from "@/theme/tokens"
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
import { EventDetailEditDialog } from "@/components/events/EventDetailEditDialog"
import { EventsBackdrop } from "@/components/events/EventsBackdrop"

export default function EventDetail() {
  const { id } = useParams({ strict: false }) as { id: string }
  const navigate = useNavigate()
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const prefersReducedMotion = useMediaQuery("(prefers-reduced-motion: reduce)")
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
  const [editOpen, setEditOpen] = useState(false)
  const [confirmDeleteOpen, setConfirmDeleteOpen] = useState(false)
  const [deleting, setDeleting] = useState(false)

  const isAdmin = user?.role === "admin" || user?.role === "teacher"

  const refreshEvent = useCallback(async () => {
    await queryClient.invalidateQueries({ queryKey: ["events", "detail", id] })
  }, [queryClient, id])

  /* ── Firefox fallback: JS-driven reading progress bar ── */
  const progressRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    let ticking = false
    const onScroll = () => {
      if (ticking) return
      ticking = true
      requestAnimationFrame(() => {
        if (progressRef.current) {
          const max = document.documentElement.scrollHeight - window.innerHeight
          const pct = max > 0 ? Math.min(window.scrollY / max, 1) : 0
          progressRef.current.style.transform = `scaleX(${pct})`
        }
        ticking = false
      })
    }
    window.addEventListener("scroll", onScroll, { passive: true })
    return () => window.removeEventListener("scroll", onScroll)
  }, [])

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
        setSnackbar(t("events:detail.messages.linkCopied"))
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
    return <EventDetailSkeleton isNarrow={isNarrow} prefersReducedMotion={prefersReducedMotion} />
  }

  /* ── Error / not found state ── */
  if (error || !event) {
    return (
      <div className="events-theme aurora-mesh relative min-h-[60vh] flex items-center justify-center px-4">
        <EventsBackdrop isNarrow={isNarrow} prefersReducedMotion={prefersReducedMotion} />
        <div className="relative z-[1] glass-layer-surface glass-noise rounded-2xl p-8 sm:p-10 max-w-[28rem] text-center space-y-4">
          <div
            className="mb-2 inline-flex h-16 w-16 items-center justify-center rounded-full bg-surface-elevated text-text-secondary"
            aria-hidden="true"
          >
            <InfoIcon size={32} />
          </div>
          <p className="text-lg font-semibold text-text-primary">
            {t("events:detail.messages.notFound")}
          </p>
          <Button variant="glass" onClick={() => navigate({ to: "/events" })}>
            {t("common:buttons.back")}
          </Button>
        </div>
      </div>
    )
  }

  /* ── Render ── */
  return (
    <>
      {/* Reading progress — CSS scroll-driven animation (JS fallback for Firefox) */}
      <div ref={progressRef} className="events-reading-progress" aria-hidden="true" />

      <div
        className="events-theme aurora-mesh relative min-h-screen overflow-clip touch-pan-y"
        {...swipeHandlers}
      >
        {/* Backdrop decoratives */}
        <EventsBackdrop isNarrow={isNarrow} prefersReducedMotion={prefersReducedMotion} />

        {/* Content */}
        <div className="relative z-[1] px-4 sm:px-6 md:px-10 lg:px-14 pb-20 pt-6 sm:pt-8">
          <SEO
            title={event.title ?? ""}
            description={(event.description ?? "").replace(/\s+/g, " ").trim().slice(0, 160)}
            image={event.image_url ?? undefined}
          />

          <Button
            onClick={handleBack}
            leadingIcon={<ArrowBackIcon size={18} />}
            variant="glass"
            className="mb-6"
          >
            {t("common:buttons.back")}
          </Button>

          <article className="max-w-4xl 2xl:max-w-5xl space-y-8">
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
            {event.image_url && <EventDetailHero imageUrl={event.image_url} />}

            {/* Description */}
            {event.description && (
              <p className="whitespace-pre-line text-base leading-relaxed text-text-primary max-w-[65ch]">
                {event.description}
              </p>
            )}

            {/* Body — About editor + Files */}
            <EventDetailBody
              event={event}
              language={language}
              isAdmin={isAdmin}
              onRefresh={refreshEvent}
              onError={setSnackbar}
              onSuccess={setSnackbar}
            />

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
        </div>
      </div>

      {/* Edit dialog (wired to editOpen state set by header's onEditOpen) */}
      {isAdmin && (
        <EventDetailEditDialog
          open={editOpen}
          onClose={() => setEditOpen(false)}
          event={event}
          onSuccess={(msg) => setSnackbar(msg)}
          onError={(msg) => setSnackbar(msg)}
        />
      )}

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
    </>
  )
}
