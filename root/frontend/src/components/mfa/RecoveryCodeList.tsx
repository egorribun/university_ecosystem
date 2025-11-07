import { Fragment, useCallback, useState } from "react"
import ContentCopyIcon from "@mui/icons-material/ContentCopy"
import { useTranslation } from "react-i18next"
import { Alert, Button } from "@/components/ui"
import { cn } from "@/utils/cn"

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
      <Alert tone="info" role="status">
        {t("mfa.recovery.empty")}
      </Alert>
    )
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-start">
        <p className="text-[1.05rem] font-semibold text-page-foreground">
          {t("mfa.recovery.title")}
        </p>
        {allowCopy ? (
          <Button
            variant="outline"
            size="sm"
            leadingIcon={<ContentCopyIcon fontSize="small" />}
            onClick={() => void handleCopyAll()}
            className={cn(
              "w-full sm:w-auto",
              copied
                ? "border-[color:rgba(16,185,129,0.55)] bg-[rgba(16,185,129,0.14)] text-[color:rgba(6,95,70,0.92)] hover:bg-[rgba(16,185,129,0.18)]"
                : "hover:bg-[color:color-mix(in_srgb,var(--nav-link)_12%,transparent)]"
            )}
          >
            {copied ? t("mfa.recovery.copied") : t("mfa.recovery.copyAll")}
          </Button>
        ) : null}
      </div>
      <p className="text-sm text-[color:color-mix(in_srgb,var(--page-text)_68%,transparent)]">
        {t("mfa.recovery.instructions")}
      </p>
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        {codes.map((entry, index) => (
          <Fragment key={entry.code}>
            <div
              className={cn(
                "rounded-ue-lg border border-[color:color-mix(in_srgb,var(--page-text)_12%,transparent)]",
                "bg-[color:color-mix(in_srgb,var(--card-bg)_95%,white_5%)] px-3 py-2 text-center font-mono text-[1.05rem] tracking-[0.28em] transition-all duration-200",
                entry.usedAt
                  ? "text-[color:color-mix(in_srgb,var(--page-text)_50%,transparent)] opacity-80"
                  : "text-page-foreground"
              )}
            >
              {entry.code}
            </div>
            {(index + 1) % 2 === 0 ? (
              <div className="col-span-full h-px bg-[color:color-mix(in_srgb,var(--page-text)_8%,transparent)] sm:hidden" />
            ) : null}
          </Fragment>
        ))}
      </div>
      <Alert tone="warning" role="status">
        {t("mfa.recovery.warning")}
      </Alert>
    </div>
  )
}

export default RecoveryCodeList
