/**
 * Unified event form dialog — wraps EventCreateDialog for now.
 * Full create/edit unification will come in Phase 2 when card decomposition
 * brings the edit flow into the feature layer.
 */
import { EventCreateDialog } from "@/components/events/EventCreateDialog"

interface EventFormDialogProps {
  open: boolean
  onClose: () => void
  onSuccess: () => void
  language: "ru" | "en"
}

export const EventFormDialog = ({ open, onClose, onSuccess, language }: EventFormDialogProps) => {
  return (
    <EventCreateDialog
      open={open}
      onClose={onClose}
      onCreated={async (draft) => {
        // The createEvent call is handled by the parent EventsFeature
        // For now, delegate directly to the legacy dialog's onCreated
        // which will be unified in a later wave
        const { createEvent } = await import("@/api/events")
        try {
          await createEvent(draft)
          onClose()
          onSuccess()
          window.scrollTo({ top: 0, behavior: "smooth" })
        } catch {
          // Error handling is in the legacy dialog; will be moved to snackbar in Phase 5
        }
      }}
      language={language}
    />
  )
}
