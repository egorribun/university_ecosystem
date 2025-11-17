import { FormEvent, useId, useState } from "react"
import { useTranslation } from "react-i18next"

type OtpEntryProps = {
  loading?: boolean
  error?: string | null
  helperText?: string | null
  onSubmit: (code: string) => Promise<void> | void
}

export const OtpEntry = ({ loading, error, helperText, onSubmit }: OtpEntryProps) => {
  const { t } = useTranslation("auth")
  const [code, setCode] = useState("")
  const [localError, setLocalError] = useState<string | null>(null)
  const inputId = useId()
  const helperId = useId()
  const errorId = useId()

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault()
    const trimmed = code.trim()
    if (!trimmed) {
      setLocalError(t("mfa.otp.validation.required"))
      return
    }
    setLocalError(null)
    await onSubmit(trimmed)
  }

  const derivedError = localError || error
  const derivedHelperText = derivedError ? null : (helperText ?? null)
  const describedBy = derivedError
    ? errorId
    : derivedHelperText
      ? helperId
      : undefined

  return (
    <form onSubmit={handleSubmit} className="w-full">
      <div className="flex flex-col gap-4 items-stretch">
        <h3 className="text-base font-semibold text-center text-page-text">
          {t("mfa.otp.methods.totp")}
        </h3>

        <p className="text-sm text-page-text/70">{t("mfa.otp.descriptions.totp")}</p>

        <div>
          <label htmlFor={inputId} className="sr-only">
            {t("mfa.otp.methods.totp")}
          </label>
          <input
            id={inputId}
            autoFocus
            type="text"
            value={code}
            onChange={(e) => setCode(e.target.value)}
            placeholder={t("mfa.otp.placeholders.totp")}
            inputMode="numeric"
            disabled={Boolean(loading)}
            className={`
              w-full px-4 py-2.5 rounded-lg border bg-card text-page-text
              ${derivedError ? "border-red-500" : "border-page-text/25"}
              hover:border-page-text/35
              focus:outline-none focus:ring-2 focus:ring-primary/25 focus:border-primary
              disabled:bg-page-text/[0.06] disabled:border-page-text/20 disabled:cursor-not-allowed
              transition-all duration-200
            `}
            aria-invalid={derivedError ? "true" : "false"}
            aria-describedby={describedBy}
          />
        </div>

        {derivedError ? (
          <p id={errorId} className="text-xs text-red-500">
            {derivedError}
          </p>
        ) : derivedHelperText ? (
          <p id={helperId} className="text-xs text-page-text/60">
            {derivedHelperText}
          </p>
        ) : null}

        <button
          type="submit"
          disabled={Boolean(loading)}
          className="
            w-full px-6 py-3 text-base font-bold rounded-xl text-white
            bg-[color:var(--nav-link)] shadow-[0_14px_34px_rgba(15,79,170,0.26)]
            hover:bg-[color:color-mix(in_srgb,var(--nav-link)_94%,white_6%)]
            focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:color-mix(in_srgb,var(--nav-link)_35%,transparent)]
            focus-visible:ring-offset-2 focus-visible:ring-offset-transparent
            dark:bg-[color:color-mix(in_srgb,var(--nav-link)_88%,rgba(10,18,32,0.92)_12%)]
            dark:hover:bg-[color:color-mix(in_srgb,var(--nav-link)_92%,rgba(10,18,32,0.92)_8%)]
            dark:shadow-[0_18px_38px_rgba(2,6,23,0.55)]
            transition-all duration-200
            disabled:opacity-60 disabled:cursor-not-allowed
          "
        >
          {loading ? t("mfa.otp.submitting") : t("mfa.otp.submit")}
        </button>
      </div>
    </form>
  )
}

export default OtpEntry
