/**
 * EventCard — logic-only layer.
 * Computes all state via useEventCardLogic, then delegates rendering
 * to EventCardView (lazy-loaded).
 *
 * Pattern source: components/news/NewsCard.tsx
 * PERF-27-02-KEPT: custom areEqual comparator (React Compiler can't infer for memo'd components)
 */

import { memo, lazy, Suspense, type FC } from "react"
import type { Event } from "@/types/Event"
import { useEventCardLogic } from "@/hooks/useEventCardLogic"
import { useTranslation } from "react-i18next"
import { inferEventCategory } from "@/features/events/categories"
import { EventCardSkeleton } from "./EventCardSkeleton"

const EventCardView = lazy(() =>
  import("./EventCardView").then((m) => ({ default: m.EventCardView }))
)

interface EventCardProps extends Partial<Event> {
  id: string
  animationIndex?: number
  onChange?: () => void
  maxWidth?: string
}

const EventCardComponent: FC<EventCardProps> = (props) => {
  const { id, title, speaker, location, description, starts_at, ends_at, event_type, event_type_en } = props
  const { t } = useTranslation(["events", "common"])

  const {
    user,
    spotlight,
    menuId,
    timeStatus,
    eventEnded,
    cardImageUrl,
    snackbar,
    setSnackbar,
    loading,
    menuAnchor,
    setMenuAnchor,
    editOpen,
    setEditOpen,
    confirmDeleteOpen,
    setConfirmDeleteOpen,
    editData,
    setEditData,
    newImage,
    setNewImage,
    imageLoading,
    previewUrl,
    registration,
    handleEdit,
    handleDelete,
  } = useEventCardLogic(props)

  const category = inferEventCategory(event_type ?? event_type_en)
  const isAdmin = user?.role === "admin" || user?.role === "teacher"

  return (
    <Suspense fallback={<EventCardSkeleton />}>
      <EventCardView
        id={id}
        title={title || ""}
        speaker={speaker ?? undefined}
        startsAt={starts_at || ""}
        endsAt={ends_at ?? undefined}
        location={location ?? undefined}
        description={description ?? undefined}
        imageUrl={cardImageUrl || undefined}
        participantCount={registration.participantCount}
        isRegistered={registration.isRegistered}
        isEnded={eventEnded}
        isAdmin={isAdmin}
        loading={loading || registration.isLoading}
        error={snackbar}
        hoveringDisabled={editOpen}
        timeStatus={timeStatus.status}
        category={category}
        editOpen={editOpen}
        confirmDeleteOpen={confirmDeleteOpen}
        editData={editData as Record<string, unknown>}
        spotlight={spotlight}
        menuAnchor={menuAnchor}
        setMenuAnchor={setMenuAnchor}
        menuId={menuId}
        onEditOpen={() => setEditOpen(true)}
        onEditClose={() => setEditOpen(false)}
        onDeleteOpen={() => setConfirmDeleteOpen(true)}
        onDeleteClose={() => setConfirmDeleteOpen(false)}
        onDeleteConfirm={handleDelete}
        onEditSave={handleEdit}
        editDraft={editData as Record<string, unknown>}
        setEditDraft={setEditData as (d: Record<string, unknown>) => void}
        imageLoading={imageLoading}
        newImage={newImage}
        setNewImage={setNewImage}
        previewUrl={previewUrl}
        onErrorClose={() => setSnackbar("")}
        t={{
          deleteTitle: t("events:card.dialogs.delete.title"),
          deleteDesc: t("events:card.dialogs.delete.description"),
          confirm: t("common:buttons.delete"),
          cancel: t("common:buttons.cancel"),
        }}
      />
    </Suspense>
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

// PERF-27-02-KEPT: custom areEqual comparator
export default memo(EventCardComponent, areEventCardPropsEqual)
