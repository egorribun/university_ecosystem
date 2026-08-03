import { memo, useState, useEffect, type MouseEvent } from "react"
import { Button, Tooltip } from "@/components/ui"
import { Users as PeopleAltIcon, QrCode as QrCodeIcon } from "lucide-react"
import { useTranslation } from "react-i18next"
import { EventQrDialog } from "@/components/events/EventQrDialog"

interface EventActionsProps {
  eventId: string
  isActive: boolean
  isEnded: boolean
  isRegistered: boolean
  participantCount: number
  qrToken?: string
  loading: boolean
  onRegister: (e: MouseEvent) => void
  onUnregister: (e: MouseEvent) => void
  userRole?: string
}

const qrOpenKey = (eventId: string) => `event:qr_open:${eventId}`

export const EventActions = memo(function EventActions({
  eventId,
  isActive,
  isEnded,
  isRegistered,
  participantCount,
  qrToken,
  loading,
  onRegister,
  onUnregister,
  userRole,
}: EventActionsProps) {
  const { t } = useTranslation(["events"])
  const [qrOpen, setQrOpen] = useState(false)

  // QR Dialog persistence logic
  useEffect(() => {
    try {
      const wasOpen = sessionStorage.getItem(qrOpenKey(eventId)) === "1"
      if (wasOpen && qrToken) {
        setQrOpen(true)
      }
    } catch {
      // ignore
    }
  }, [eventId, qrToken])

  useEffect(() => {
    try {
      if (qrOpen) sessionStorage.setItem(qrOpenKey(eventId), "1")
      else sessionStorage.removeItem(qrOpenKey(eventId))
    } catch {
      // ignore
    }
  }, [qrOpen, eventId])

  return (
    <div className="mt-auto">
      <div className="mb-4 flex items-center gap-2 group/part">
        <div className="flex h-10 w-10 items-center justify-center rounded-full bg-warning-bg/(--opacity-dim) text-warning-text">
          <Tooltip content={t("events:form.participants")}>
            <PeopleAltIcon
              size={19}
              className="text-brand transition-transform group-hover/part:scale-110"
            />
          </Tooltip>
        </div>
        <span className="text-body-sm text-text-primary">
          {t("events:card.participants", { count: participantCount })}
        </span>
      </div>

      {isEnded && (
        <span className="inline-flex mb-4 py-1.5 px-3 rounded-lg bg-error-bg/(--opacity-dim) border border-error-border/(--opacity-soft) text-sm font-semibold text-error-text">
          {t("events:card.statuses.ended")}
        </span>
      )}

      {isActive && !isEnded && !isRegistered && userRole !== "admin" && userRole !== "teacher" && (
        <Button
          variant="solid"
          onClick={onRegister}
          disabled={loading}
          className="mt-2 font-bold relative overflow-hidden shadow-premium-lift transition-shadow animate-pulse-shadow"
        >
          {t("events:card.actions.register")}
        </Button>
      )}

      {isActive && !isEnded && isRegistered && (
        <div className="mt-4 flex flex-wrap items-center gap-4">
          <Button variant="outline" onClick={onUnregister} disabled={loading}>
            {t("events:card.actions.unregister")}
          </Button>

          {qrToken && (
            <>
              <Tooltip content={t("events:card.actions.openQr")}>
                <Button
                  variant="gradient"
                  size="lg"
                  onClick={(e) => {
                    e.stopPropagation()
                    setQrOpen(true)
                  }}
                  className="p-4! sm:p-5! rounded-fluid-lg shadow-premium-lift group/qr"
                >
                  <QrCodeIcon className="w-8 h-8 text-[var(--text-inverse)] drop-shadow-sm relative z-decor" />
                </Button>
              </Tooltip>

              <EventQrDialog open={qrOpen} onClose={() => setQrOpen(false)} qr={qrToken} />
            </>
          )}
        </div>
      )}
    </div>
  )
})

export default EventActions
