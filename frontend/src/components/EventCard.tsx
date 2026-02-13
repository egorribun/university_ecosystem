import { memo, lazy, Suspense, type FC } from "react"
import type { Event } from "@/types/Event"

import { motion } from "framer-motion"
import { cn } from "@/utils/cn"
import Dialog from "@/components/Dialog"
import { SpotlightOverlay } from "@/components/ui/Spotlight"
import { motion as motionTokens } from "@/theme/tokens"
import { EASING } from "@/utils/motion"

import { Button, Snackbar } from "@/components/ui"
import { useEventCardLogic } from "@/hooks/useEventCardLogic"

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

interface EventCardProps extends Partial<Event> {
  id: string
  animationIndex?: number
  onChange?: () => void
  maxWidth?: string
}

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
    onCardClick,
  } = useEventCardLogic(props)

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 16, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{
        duration: motionTokens.durationMedium,
        delay: (animationIndex % 10) * motionTokens.staggerDelay,
        ease: EASING.premium,
      }}
      whileHover={{
        y: -4,
        transition: { duration: motionTokens.durationFast, ease: EASING.premium },
      }}
      className="w-full"
      onMouseMove={spotlight.onMouseMove}
    >
      <div
        className={cn(
          "card-glass group relative flex flex-col transition-shadow duration-300 ease-out w-full p-fluid-card-p transform-gpu will-change-transform rounded-fluid-lg bg-glass-elevated border-glass-border-subtle shadow-premium",
          editOpen ? "cursor-default" : "card-interactive"
        )}
        role="button"
        tabIndex={0}
        onClick={onCardClick}
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
          className="z-(--z-hide) rounded-3xl"
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
          isRegistered={registration.isRegistered}
          participantCount={registration.participantCount}
          qrToken={registration.qrToken}
          loading={loading || registration.isLoading}
          onRegister={registration.register}
          onUnregister={registration.unregister}
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
            dateError={false}
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
                className="bg-error-text hover:bg-error-text/(--opacity-heavy)"
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
