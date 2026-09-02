import { useCallback, useMemo, useState, lazy, Suspense } from "react"
import { Copy, Check } from "lucide-react"
import { useTranslation } from "react-i18next"

const QRCodeSVG = lazy(() => import("qrcode.react").then((m) => ({ default: m.QRCodeSVG })))

type TotpQrDisplayProps = {
  otpauthUrl: string
  secret: string
  label?: string | null
}

const QR_SIZE = 192
const COPY_FEEDBACK_MS = 2500

export const TotpQrDisplay = ({ otpauthUrl, secret, label }: TotpQrDisplayProps) => {
  const { t } = useTranslation("auth")
  const [copied, setCopied] = useState(false)
  const [showTooltip, setShowTooltip] = useState(false)

  const normalizedSecret = useMemo(() => secret.replace(/\s+/g, "").toUpperCase(), [secret])

  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(normalizedSecret)
      setCopied(true)
      setTimeout(() => setCopied(false), COPY_FEEDBACK_MS)
    } catch {
      // Ignored
      setCopied(false)
    }
  }, [normalizedSecret])

  return (
    <div className="flex flex-col gap-4 items-center text-center">
      <h3 className="text-lg font-semibold text-text-primary">{t("mfa.totp.scanHeading")}</h3>
      {label ? (
        <p className="text-sm text-(--text-secondary)">{t("mfa.totp.accountLabel", { label })}</p>
      ) : null}
      <div
        className="p-4 rounded-lg border border-glass-border bg-surface shadow-sm min-h-56 flex items-center justify-center"
        role="img"
        aria-label={t("mfa.totp.qrAriaLabel")}
      >
        <Suspense
          fallback={<div className="w-48 h-48 animate-pulse bg-(--border-subtle) rounded" />}
        >
          {/*
            QR codes require high-contrast colors for reliable scanning.
            These values are accessibility-compliant and scanner-tested.
          */}
          <QRCodeSVG
            value={otpauthUrl}
            size={QR_SIZE}
            includeMargin
            bgColor="#FFFFFF"
            fgColor="#0F172A"
          />
        </Suspense>
      </div>
      <div className="flex flex-row items-center gap-2 w-full max-w-xs">
        <div className="relative flex-1">
          <label
            htmlFor="totp-manual-code"
            className="block text-xs font-medium text-text-primary mb-1 px-1 bg-(--bg-surface)"
          >
            {t("mfa.totp.manualHeading")}
          </label>
          <input
            id="totp-manual-code"
            type="text"
            readOnly
            value={normalizedSecret}
            className="w-full px-3 py-1.5 text-sm rounded-lg border border-(--text-primary)/(--opacity-dim) bg-(--bg-surface) text-text-primary font-mono tracking-wider text-center select-all cursor-text"
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
              ${copied ? "text-success-text hover:bg-success-bg/(--opacity-subtle)" : "text-brand hover:bg-brand/(--opacity-subtle)"}
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
