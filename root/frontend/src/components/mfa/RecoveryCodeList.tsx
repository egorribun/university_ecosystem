import { Fragment, useCallback, useState } from "react"
import { Copy } from "lucide-react"
import { useTranslation } from "react-i18next"

export type RecoveryCodeEntry = {
  code: string
  usedAt?: string | null
}

type RecoveryCodeListProps = {
  codes: RecoveryCodeEntry[]
  allowCopy?: boolean
}

export const RecoveryCodeList = ({ codes, allowCopy = true }: RecoveryCodeListProps) => {
  const { t } = useTranslation("auth")
  const [copied, setCopied] = useState(false)

  const handleCopyAll = useCallback(async () => {
    if (!allowCopy) return
    try {
      if (typeof navigator === "undefined" || !navigator.clipboard) {
        throw new Error("clipboard unsupported")
      }
      const payload = codes.map((entry) => entry.code).join("\n")
      await navigator.clipboard.writeText(payload)
      setCopied(true)
      setTimeout(() => setCopied(false), 2500)
    } catch (error) {
      if (import.meta.env.DEV) {
        console.warn("Failed to copy recovery codes", error)
      }
      setCopied(false)
    }
  }, [allowCopy, codes])

  if (!codes.length) {
    return (
      <div className="flex items-center gap-2 px-4 py-2 rounded-lg border-2 border-blue-500 text-blue-500 bg-transparent">
        <span className="flex-1">{t("mfa.recovery.empty")}</span>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-4 items-stretch">
      <div className="flex flex-col sm:flex-row gap-3 items-start sm:items-center">
        <h3 className="text-base font-semibold text-page-text">{t("mfa.recovery.title")}</h3>
        {allowCopy ? (
          <button
            onClick={() => void handleCopyAll()}
            className="inline-flex items-center gap-2 px-3 py-1.5 text-sm font-bold rounded-lg border-2 border-primary text-primary hover:bg-primary/10 transition-colors"
          >
            <Copy className="w-4 h-4" />
            {copied ? t("mfa.recovery.copied") : t("mfa.recovery.copyAll")}
          </button>
        ) : null}
      </div>
      <p className="text-sm text-page-text/70">{t("mfa.recovery.instructions")}</p>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        {codes.map((entry, index) => (
          <Fragment key={entry.code}>
            <div
              className={`
                rounded-xl border border-glass-border bg-page-text/[0.04] px-4 py-3
                font-mono tracking-wider text-base text-center
                ${entry.usedAt ? "text-page-text/50" : "text-page-text"}
              `}
            >
              {entry.code}
            </div>
            {(index + 1) % 2 === 0 ? (
              <hr className="border-t border-glass-border sm:hidden" />
            ) : null}
          </Fragment>
        ))}
      </div>
      <div className="flex items-center gap-2 px-4 py-2 rounded-lg border-2 border-yellow-500 text-yellow-500 bg-transparent">
        <span className="flex-1">{t("mfa.recovery.warning")}</span>
      </div>
    </div>
  )
}

export default RecoveryCodeList
