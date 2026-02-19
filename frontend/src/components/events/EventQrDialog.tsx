import { useTranslation } from "react-i18next"
import { Button } from "@/components/ui"
import Dialog from "@/components/Dialog"
import SmartImage from "@/components/SmartImage"

type EventQrDialogProps = {
  open: boolean
  onClose: () => void
  qr: string
}

export function EventQrDialog({ open, onClose, qr }: EventQrDialogProps) {
  const { t } = useTranslation()

  return (
    <Dialog open={open} onClose={onClose} title="" size="sm">
      <div className="space-y-4">
<<<<<<< HEAD
        <div
          className="mx-auto w-full rounded-2xl bg-surface p-6 shadow-glass"
          style={{ maxWidth: "min(80vw, 80vh, 400px)" }}
        >
          <img
            src={`https://api.qrserver.com/v1/create-qr-code/?data=${encodeURIComponent(
=======
        <div className="mx-auto w-full max-w-[min(80vw,80vh,25rem)] rounded-2xl bg-surface p-6 shadow-glass">
          <SmartImage
            srcRaw={`https://api.qrserver.com/v1/create-qr-code/?data=${encodeURIComponent(
>>>>>>> origin/main
              qr
            )}&size=600x600`}
            alt={t("events:card.alt.qr")}
            className="block h-auto w-full aspect-square select-none"
            loading="eager"
          />
        </div>
        <Button variant="outline" onClick={onClose} className="w-full">
          {t("events:card.actions.closeQr")}
        </Button>
      </div>
    </Dialog>
  )
}
