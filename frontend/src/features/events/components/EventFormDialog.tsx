/**
 * Unified event form dialog — wraps EventCreateDialog for now.
 * Full create/edit unification will come in Phase 2 when card decomposition
 * brings the edit flow into the feature layer.
 */
import { EventCreateDialog } from "@/components/events/EventCreateDialog"
import { logError } from "@/app/logger"
import { captureActiveTelemetryContext } from "@/utils/telemetryContext"

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
        const telemetryContext = captureActiveTelemetryContext()
        try {
          const { createEvent } = await import("@/api/events")
          await telemetryContext.run(() => createEvent(draft))
        } catch (err) {
          logError("[EventFormDialog] createEvent failed:", err)
          throw err
        }

        try {
          await telemetryContext.run(onSuccess)
        } catch (err) {
          // The create already committed. Refresh failures must not keep the
          // form open as though the create request itself had failed.
          logError("[EventFormDialog] refresh after create failed:", err)
        }
      }}
      language={language}
    />
  )
}
