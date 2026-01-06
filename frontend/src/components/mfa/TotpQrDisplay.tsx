import { useCallback, useMemo, useState, lazy, Suspense } from "react"
import { Copy, Check } from "lucide-react"
import { useTranslation } from "react-i18next"

const QRCodeSVG = lazy(() => import("qrcode.react").then((m) => ({ default: m.QRCodeSVG })))

type TotpQrDisplayProps = {
  otpauthUrl: string
  secret: string
  label?: string | null
}

export const TotpQrDisplay = ({ otpauthUrl, secret, label }: TotpQrDisplayProps) => {
  const { t } = useTranslation("auth")
  const [copied, setCopied] = useState(false)
  const [showTooltip, setShowTooltip] = useState(false)

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
    <div className="flex flex-col gap-4 items-center text-center">
      <h3 className="text-lg font-semibold text-page-text">{t("mfa.totp.scanHeading")}</h3>
      {label ? (
        <p className="text-sm text-page-text/70">{t("mfa.totp.accountLabel", { label })}</p>
      ) : null}
      <div className="p-4 rounded-lg border border-glass-border bg-white shadow-sm dark:bg-white min-h-[224px] flex items-center justify-center">
        <Suspense
          fallback={<div className="w-[192px] h-[192px] animate-pulse bg-gray-100 rounded" />}
        >
          <QRCodeSVG
            value={otpauthUrl}
            size={192}
            includeMargin
            bgColor="#ffffff"
            fgColor="#111827"
          />
        </Suspense>
      </div>
      <div className="flex flex-row items-center gap-2 w-full max-w-[320px]">
        <div className="relative flex-1">
          <label
            htmlFor="totp-manual-code"
            className="block text-xs font-medium text-page-text mb-1 px-1 bg-card"
          >
            {t("mfa.totp.manualHeading")}
          </label>
          <input
            id="totp-manual-code"
            type="text"
            value={normalizedSecret}
            readOnly
            className="w-full px-3 py-1.5 text-sm rounded-lg border border-page-text/25 bg-card text-page-text font-mono tracking-wider"
          />
        </div>
        <div className="relative mt-5">
          <button
            onClick={() => void handleCopy()}
            onMouseEnter={() => setShowTooltip(true)}
            onMouseLeave={() => setShowTooltip(false)}
            aria-label={t("mfa.totp.copySecret") ?? ""}
            className={`
              p-2 rounded-lg transition-colors
              ${copied ? "text-green-500 hover:bg-green-500/10" : "text-primary hover:bg-primary/10"}
            `}
          >
            {copied ? <Check className="w-5 h-5" /> : <Copy className="w-5 h-5" />}
          </button>
          {showTooltip && (
            <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 px-2 py-1 text-xs text-white bg-gray-800 rounded whitespace-nowrap pointer-events-none">
              {copied ? t("mfa.totp.copied") : t("mfa.totp.copySecret")}
            </div>
          )}
        </div>
      </div>
      <p className="text-sm text-page-text/70">{t("mfa.totp.instructions")}</p>
    </div>
  )
}

export default TotpQrDisplay
