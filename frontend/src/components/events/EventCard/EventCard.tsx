import { memo, lazy, Suspense, type FC } from "react"
import type { Event } from "@/types/Event"


import { cn } from "@/utils/cn"
import { SpotlightOverlay } from "@/components/ui/Spotlight"
import { motion as motionTokens } from "@/theme/tokens"
import { motion } from "framer-motion"
import { EASING } from "@/utils/motion"

import { Snackbar, ContentCard, ConfirmDialog } from "@/components/ui"
import { useEventCardLogic } from "@/hooks/useEventCardLogic"

// Sub-components
import { EventMedia } from "./EventMedia"
import { EventInfo } from "./EventInfo"
import { EventActions } from "./EventActions"

const EventEditDialog = lazy(() =>
  import("@/components/events/EventEditDialog").then((m) => ({ default: m.EventEditDialog }))
)
const EventAdminActions = lazy(() =>
  import("./EventAdminActions").then((m) => ({ default: m.EventAdminActions }))
)

interface EventCardProps extends Partial<Event> {
  id: string
  animationIndex?: number
  onChange?: () => void
  maxWidth?: string
}

// Animation Constants
const STAGGER_BATCH_SIZE = 10
const HOVER_Y_OFFSET = -4

const EventCardComponent: FC<EventCardProps> = (props) => {
  const {
    id,
    title,
    speaker,
    location,
    description,
    starts_at,
    ends_at,
    event_type,
    is_active,
    animationIndex = 0,
  } = props

  const {
    user,
    t,
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
    cardImageReady,
    setCardImageReady,
    previewUrl,

    registration,
    handleEdit,
    handleDelete,
    navigate: navigateToDetails,
  } = useEventCardLogic(props)

  return (
    <motion.article
      layout
      initial={{ opacity: 0, y: 16, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{
        duration: motionTokens.durationMedium,
        delay: (animationIndex % STAGGER_BATCH_SIZE) * motionTokens.staggerDelay,
        ease: EASING.premium,
      }}
      whileHover={{
        y: HOVER_Y_OFFSET,
        transition: { duration: motionTokens.durationFast, ease: EASING.premium },
      }}
      className="w-full outline-none"
      tabIndex={editOpen ? -1 : 0}
      aria-labelledby={`event-title-${id}`}
      aria-describedby={`event-location-${id}`}
      onKeyDown={(e) => {
        if (!editOpen && (e.key === "Enter" || e.key === " ")) {
          e.preventDefault()
          navigateToDetails()
        }
      }}
    >
      <ContentCard
        hoverable={!editOpen}
        className={cn(
          "card-glass group w-full transform-gpu will-change-transform rounded-fluid-lg hover:shadow-premium-lift",
          editOpen ? "cursor-default" : "card-interactive"
        )}
        onMouseMove={spotlight.onMouseMove}
      >
        <SpotlightOverlay
          mouseX={spotlight.mouseX}
          mouseY={spotlight.mouseY}
          className="z-hide rounded-3xl"
        />

        {/* Admin Menu */}
        {user && (user.role === "admin" || user.role === "teacher") && (
          <ContentCard.Actions className="absolute top-3 right-3 z-surface">
            <Suspense fallback={<div className="w-8 h-8 rounded-full bg-glass animate-pulse" />}>
              <EventAdminActions
                menuAnchor={menuAnchor}
                setMenuAnchor={setMenuAnchor}
                onEdit={() => setEditOpen(true)}
                onDelete={() => setConfirmDeleteOpen(true)}
                menuId={menuId}
              />
            </Suspense>
          </ContentCard.Actions>
        )}

        <ContentCard.Body className="p-fluid-card-p flex flex-col h-full">
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
            titleId={`event-title-${id}`}
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
            isRegistered={registration.isRegistered}
            participantCount={registration.participantCount}
            qrToken={registration.qrToken}
            loading={loading || registration.isLoading}
            onRegister={registration.register}
            onUnregister={registration.unregister}
            userRole={user?.role}
          />
        </ContentCard.Body>

        {/* Dialogs */}
        <Suspense fallback={null}>
          <EventEditDialog
            open={editOpen}
            onClose={() => setEditOpen(false)}
            draft={editData}
            setDraft={setEditData}
            onSave={handleEdit}
            loading={loading}
            imageLoading={imageLoading}
            dateError={false}
            normalizedTitle={title || ""}
            normalizedLocation={location || ""}
            newImage={newImage}
            setNewImage={setNewImage}
            previewUrl={previewUrl}
          />
        </Suspense>

        <ConfirmDialog
          open={confirmDeleteOpen}
          title={t("events:card.dialogs.delete.title")}
          message={t("events:card.dialogs.delete.description")}
          confirmText={t("common:buttons.delete")}
          cancelText={t("common:buttons.cancel")}
          variant="danger"
          onConfirm={handleDelete}
          onCancel={() => setConfirmDeleteOpen(false)}
          isLoading={loading}
        />

        <Snackbar open={!!snackbar} message={snackbar} onClose={() => setSnackbar("")} />
      </ContentCard>
    </motion.article>
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
