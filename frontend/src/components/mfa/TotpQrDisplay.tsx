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
      <h3 className="text-lg font-semibold text-(--text-primary)">{t("mfa.totp.scanHeading")}</h3>
      {label ? (
        <p className="text-sm text-(--text-secondary)">{t("mfa.totp.accountLabel", { label })}</p>
      ) : null}
      <div className="p-4 rounded-lg border border-glass-border bg-surface shadow-sm min-h-[224px] flex items-center justify-center">
        <Suspense
          fallback={
            <div className="w-[192px] h-[192px] animate-pulse bg-(--border-subtle) rounded" />
          }
        >
          {/*
            QR codes require high-contrast colors for reliable scanning.
            These values are accessibility-compliant and scanner-tested.
            Do not replace with CSS variables.
          */}
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
            className="block text-xs font-medium text-(--text-primary) mb-1 px-1 bg-card"
          >
            {t("mfa.totp.manualHeading")}
          </label>
          <input
            id="totp-manual-code"
            type="text"
            readOnly
            value={normalizedSecret}
            className="w-full px-3 py-1.5 text-sm rounded-lg border-(--text-primary)/25 bg-card text-(--text-primary) font-mono tracking-wider text-center select-all cursor-text"
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
              ${copied ? "text-success-text hover:bg-success-bg/10" : "text-brand hover:bg-brand/10"}
            `}
          >
            {copied ? <Check className="w-5 h-5" /> : <Copy className="w-5 h-5" />}
          </button>
          {showTooltip && (
            <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 px-2 py-1 text-xs text-white bg-(--text-primary) rounded whitespace-nowrap pointer-events-none">
              {copied ? t("mfa.totp.copied") : t("mfa.totp.copySecret")}
            </div>
          )}
        </div>
      </div>
      <p className="text-sm text-(--text-secondary)">{t("mfa.totp.instructions")}</p>
    </div>
  )
}

export default TotpQrDisplay
