import { useState, useEffect } from "react"
import { useTranslation } from "react-i18next"
import { Button } from "@/components/ui"
import Dialog from "@/components/ui/Dialog"
import SmartImage from "@/components/media/SmartImage"
import { cn } from "@/utils/cn"

type EventQrDialogProps = {
  open: boolean
  onClose: () => void
  qr: string
}

export function EventQrDialog({ open, onClose, qr }: EventQrDialogProps) {
  const { t } = useTranslation()
  const [qrLoaded, setQrLoaded] = useState(false)

  // Reset loading state when dialog opens with new QR
  useEffect(() => {
    if (open) setQrLoaded(false)
  }, [open, qr])

  return (
    <Dialog open={open} onClose={onClose} title={t("events:card.dialogs.qr.title")} size="sm">
      <div className="space-y-4">
        <div className="relative mx-auto w-full max-w-[min(80vw,80vh,25rem)] rounded-2xl bg-surface p-6 shadow-glass">
          {!qrLoaded && (
            <div className="absolute inset-6 flex items-center justify-center">
              <div className="h-8 w-8 animate-spin rounded-full border-2 border-brand border-t-transparent" />
            </div>
          )}
          <SmartImage
            srcRaw={`https://api.qrserver.com/v1/create-qr-code/?data=${encodeURIComponent(
              qr
            )}&size=600x600`}
            alt={t("events:card.alt.qr")}
            className={cn(
              "block h-auto w-full aspect-square select-none transition-opacity",
              qrLoaded ? "opacity-100" : "opacity-0"
            )}
            loading="eager"
            onLoad={() => setQrLoaded(true)}
          />
        </div>
        <Button variant="outline" onClick={onClose} className="w-full">
          {t("events:card.actions.closeQr")}
        </Button>
      </div>
    </Dialog>
  )
}
