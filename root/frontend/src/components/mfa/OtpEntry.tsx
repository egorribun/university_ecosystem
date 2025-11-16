import { FormEvent, useState } from "react"
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
  const derivedHelperText = derivedError ? null : helperText ?? null

  return (
    <form onSubmit={handleSubmit} className="w-full">
      <div className="flex flex-col gap-4 items-stretch">
        <h3 className="text-base font-semibold text-center text-page-text">
          {t("mfa.otp.methods.totp")}
        </h3>

        <p className="text-sm text-page-text/70">{t("mfa.otp.descriptions.totp")}</p>

        <div>
          <label
            htmlFor="otp-input"
            className="block text-sm font-medium text-page-text mb-1 px-1 bg-card"
          >
            {t("mfa.otp.methods.totp")}
          </label>
          <input
            id="otp-input"
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
          />
        </div>

        {derivedError ? (
          <p className="text-xs text-red-500">{derivedError}</p>
        ) : derivedHelperText ? (
          <p className="text-xs text-page-text/60">{derivedHelperText}</p>
        ) : null}

        <button
          type="submit"
          disabled={Boolean(loading)}
          className="
            w-full px-6 py-3 text-base font-bold rounded-lg
            bg-primary text-white hover:bg-primary/90
            shadow-md hover:shadow-lg
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
