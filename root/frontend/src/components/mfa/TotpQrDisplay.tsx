import { useCallback, useMemo, useState } from "react"
import ContentCopyIcon from "@mui/icons-material/ContentCopy"
import { QRCodeSVG } from "qrcode.react"
import { useTranslation } from "react-i18next"
import { Button } from "@/components/ui"
import { cn } from "@/utils/cn"

type TotpQrDisplayProps = {
  otpauthUrl: string
  secret: string
  label?: string | null
}

export const TotpQrDisplay = ({ otpauthUrl, secret, label }: TotpQrDisplayProps) => {
  const { t } = useTranslation("auth")
  const [copied, setCopied] = useState(false)

  const normalizedSecret = useMemo(() => secret.replace(/\s+/g, "").toUpperCase(), [secret])

  const handleCopy = useCallback(async () => {
    try {
      if (typeof navigator === "undefined" || !navigator.clipboard) {
        throw new Error("clipboard unsupported")
      }
      await navigator.clipboard.writeText(normalizedSecret)
      setCopied(true)
      setTimeout(() => setCopied(false), 2500)
    } catch (error) {
      if (import.meta.env.DEV) {
        console.warn("Failed to copy secret", error)
      }
      setCopied(false)
    }
  }, [normalizedSecret])

  return (
    <div className="flex flex-col items-center gap-4 text-center">
      <h3 className="text-[1.1rem] font-semibold text-page-foreground">
        {t("mfa.totp.scanHeading")}
      </h3>
      {label ? (
        <p className="text-sm font-medium text-[color:color-mix(in_srgb,var(--page-text)_70%,transparent)]">
          {t("mfa.totp.accountLabel", { label })}
        </p>
      ) : null}

      <div className="rounded-ue-xl border border-[color:color-mix(in_srgb,var(--page-text)_12%,transparent)] bg-[color:color-mix(in_srgb,var(--card-bg)_95%,white_5%)] p-4 shadow-[0_12px_32px_rgba(15,23,42,0.12)]">
        <QRCodeSVG value={otpauthUrl} size={196} />
      </div>

      <div className="flex w-full max-w-[320px] items-center gap-2">
        <div className="flex-1">
          <label className="mb-1 block text-left text-xs font-semibold uppercase tracking-wide text-[color:color-mix(in_srgb,var(--secondary-text)_80%,transparent)]">
            {t("mfa.totp.manualHeading")}
          </label>
          <input
            value={normalizedSecret}
            readOnly
            className={cn(
              "w-full rounded-ue-lg border border-[color:color-mix(in_srgb,var(--page-text)_12%,transparent)]",
              "bg-[color:color-mix(in_srgb,var(--card-bg)_96%,white_4%)] px-3 py-2 text-center font-mono text-sm tracking-[0.32em] text-page-foreground",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:color-mix(in_srgb,var(--nav-link)_42%,transparent)]"
            )}
          />
        </div>
        <Button
          type="button"
          variant="outline"
          size="sm"
          className={cn(
            "min-w-[42px] rounded-ue-md px-2 py-2",
            "hover:bg-[color:color-mix(in_srgb,var(--nav-link)_12%,transparent)]",
            copied
              ? "border-[color:rgba(16,185,129,0.55)] bg-[rgba(16,185,129,0.14)] text-[color:rgba(6,95,70,0.92)] hover:bg-[rgba(16,185,129,0.18)]"
              : "text-nav-link"
          )}
          aria-label={t("mfa.totp.copySecret")}
          onClick={() => void handleCopy()}
        >
          <ContentCopyIcon fontSize="small" />
        </Button>
      </div>

      <p className="text-sm text-[color:color-mix(in_srgb,var(--page-text)_70%,transparent)]">
        {t("mfa.totp.instructions")}
      </p>
    </div>
  )
}

export default TotpQrDisplay
