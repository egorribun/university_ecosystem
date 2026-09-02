/**
 * EventCardView — pure presentation layer for the event card.
 * Handles: spotlight overlay, quick-view popover, admin menu,
 * category badge, hero with parallax, content with actions, dialogs.
 * Pattern source: components/news/NewsCardView.tsx
 */

import { Snackbar, ConfirmDialog } from "@/components/ui"
import { SpotlightOverlay } from "@/components/ui/Spotlight"
import { cn } from "@/utils/cn"
import { m, type MotionValue } from "framer-motion"
import { Suspense, lazy, useState, useCallback, useRef } from "react"
import type { FC, MouseEvent } from "react"
import EventCardContent from "./EventCardContent"
import EventCardHero from "./EventCardHero"
import { EventQuickView } from "../EventQuickView"
import { EventCategoryBadge } from "../EventCategoryBadge"
import type { EventCategory } from "@/features/events/categories"
import { clearEventsHeroId } from "@/utils/eventsTransition"

const EventAdminActions = lazy(() =>
  import("./EventAdminActions").then((m) => ({ default: m.EventAdminActions }))
)
const EventEditDialog = lazy(() =>
  import("@/components/events/EventEditDialog").then((m) => ({ default: m.EventEditDialog }))
)

export interface EventCardViewProps {
  id: string
  title: string
  speaker?: string
  startsAt: string
  endsAt?: string
  location?: string
  description?: string
  imageUrl?: string
  participantCount: number
  isRegistered: boolean
  isEnded: boolean
  isAdmin: boolean
  loading: boolean
  error: string
  hoveringDisabled: boolean
  timeStatus: "live" | "soon" | "none"
  category: EventCategory
  editOpen: boolean
  confirmDeleteOpen: boolean
  editData: Record<string, unknown>
  spotlight: {
    mouseX: MotionValue<number>
    mouseY: MotionValue<number>
    onMouseMove: (e: MouseEvent<HTMLDivElement>) => void
  }
  /* Edit/delete actions */
  menuAnchor: HTMLElement | null
  setMenuAnchor: (el: HTMLElement | null) => void
  menuId: string
  onEditOpen: () => void
  onEditClose: () => void
  onDeleteOpen: () => void
  onDeleteClose: () => void
  onDeleteConfirm: () => void
  onEditSave: () => void
  editDraft: Record<string, unknown>
  setEditDraft: (d: Record<string, unknown>) => void
  imageLoading: boolean
  newImage: File | null
  setNewImage: (f: File | null) => void
  previewUrl: string | null
  onErrorClose: () => void
  t: {
    deleteTitle: string
    deleteDesc: string
    confirm: string
    cancel: string
  }
  /** Forwarded to EventCardHero for LCP prioritization (Wave 113 PERF-113-01) */
  priority?: boolean
}

export const EventCardView: FC<EventCardViewProps> = ({
  id,
  title,
  speaker,
  startsAt,
  endsAt,
  location,
  description,
  imageUrl,
  participantCount,
  isRegistered,
  isEnded,
  isAdmin,
  loading,
  error,
  hoveringDisabled,
  timeStatus,
  category,
  editOpen,
  confirmDeleteOpen,
  editData: _editData,
  spotlight,
  menuAnchor,
  setMenuAnchor,
  menuId,
  onEditOpen,
  onEditClose,
  onDeleteOpen,
  onDeleteClose,
  onDeleteConfirm,
  onEditSave,
  editDraft,
  setEditDraft,
  imageLoading,
  newImage,
  setNewImage,
  previewUrl,
  onErrorClose,
  t,
  priority,
}) => {
  /* ── Quick-view hover state ── */
  const articleRef = useRef<HTMLElement>(null)
  const [quickViewVisible, setQuickViewVisible] = useState(false)
  const [quickViewPosition, setQuickViewPosition] = useState<"top" | "bottom">("top")

  const showQuickView = useCallback(() => {
    if (hoveringDisabled) return
    const article = articleRef.current
    const rect = article ? article.getBoundingClientRect() : undefined
    setQuickViewPosition(rect && rect.top < 280 ? "bottom" : "top")
    setQuickViewVisible(true)
  }, [hoveringDisabled])
  const hideQuickView = () => setQuickViewVisible(false)

  /* ── View Transition: mark hero for morphing on navigation ── */
  const [transitioning, setTransitioning] = useState(false)
  const handlePointerDown = useCallback(() => {
    if (!hoveringDisabled) {
      clearEventsHeroId()
      setTransitioning(true)
    }
  }, [hoveringDisabled])
  const handleTransitionReset = () => setTransitioning(false)

  return (
    <m.article
      ref={articleRef}
      onMouseMove={spotlight.onMouseMove}
      onMouseEnter={showQuickView}
      onMouseLeave={() => {
        hideQuickView()
        handleTransitionReset()
      }}
      onPointerDown={handlePointerDown}
      className={cn(
        "events-card-container relative h-full rounded-2xl overflow-hidden card-matte glass-noise dash-border-shimmer group outline-none transition-[transform,box-shadow] duration-slower ease-premium",
        hoveringDisabled
          ? "cursor-default"
          : "cursor-pointer hover:-translate-y-0.5 hover:shadow-lg active:translate-y-0 active:duration-instant"
      )}
      data-testid="event-card"
    >
      {/* Quick-view popover */}
      <EventQuickView
        visible={quickViewVisible}
        title={title}
        description={description || ""}
        startsAt={startsAt}
        endsAt={endsAt}
        location={location}
        participantCount={participantCount}
        category={category}
        position={quickViewPosition}
      />

      {/* Spotlight */}
      <SpotlightOverlay mouseX={spotlight.mouseX} mouseY={spotlight.mouseY} className="z-hide" />

      {/* Admin menu */}
      {isAdmin && (
        <div className="absolute right-3 top-3 z-surface">
          <Suspense fallback={null}>
            <EventAdminActions
              menuAnchor={menuAnchor}
              setMenuAnchor={setMenuAnchor}
              onEdit={onEditOpen}
              onDelete={onDeleteOpen}
              menuId={menuId}
            />
          </Suspense>
        </div>
      )}

      {/* Category badge — top-left */}
      <div className="absolute left-3 top-3 z-surface">
        <EventCategoryBadge category={category} size="sm" />
      </div>

      {/* Hero image with parallax */}
      <div className="relative shrink-0 overflow-hidden h-48 sm:h-52">
        <EventCardHero
          id={id}
          imageUrl={imageUrl}
          title={title}
          startsAt={startsAt}
          endsAt={endsAt}
          timeStatus={timeStatus}
          transitioning={transitioning}
          priority={priority}
        />
      </div>

      {/* Content — title link's before:absolute reaches <article> for full-card click */}
      <div className="flex flex-1 flex-col">
        <EventCardContent
          id={id}
          title={title}
          speaker={speaker}
          startsAt={startsAt}
          endsAt={endsAt}
          location={location}
          description={description}
          participantCount={participantCount}
          isRegistered={isRegistered}
          isEnded={isEnded}
          hoveringDisabled={hoveringDisabled}
        />
      </div>

      {/* Dialogs */}
      <Suspense fallback={null}>
        <EventEditDialog
          open={editOpen}
          onClose={onEditClose}
          draft={editDraft}
          setDraft={setEditDraft}
          onSave={onEditSave}
          loading={loading}
          imageLoading={imageLoading}
          dateError={false}
          normalizedTitle={title}
          normalizedLocation={location || ""}
          newImage={newImage}
          setNewImage={setNewImage}
          previewUrl={previewUrl}
        />
      </Suspense>

      <ConfirmDialog
        open={confirmDeleteOpen}
        title={t.deleteTitle}
        message={t.deleteDesc}
        confirmText={t.confirm}
        cancelText={t.cancel}
        variant="danger"
        onConfirm={onDeleteConfirm}
        onCancel={onDeleteClose}
        isLoading={loading}
      />

      <Snackbar open={!!error} message={error} onClose={onErrorClose} />
    </m.article>
  )
}
