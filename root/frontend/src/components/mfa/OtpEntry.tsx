import { FormEvent, useEffect, useMemo, useState } from "react"
import { useTranslation } from "react-i18next"
import type { MfaMethod } from "@/types/Mfa"

export type OtpMethod = Extract<MfaMethod, "totp" | "recovery">

type OtpEntryProps = {
  availableMethods: OtpMethod[]
  defaultMethod?: OtpMethod | null
  loading?: boolean
  error?: string | null
  helperText?: string | null
  onSubmit: (method: OtpMethod, code: string) => Promise<void> | void
}

export const OtpEntry = ({
  availableMethods,
  defaultMethod,
  loading,
  error,
  helperText,
  onSubmit,
}: OtpEntryProps) => {
  const { t } = useTranslation("auth")
  const [activeMethod, setActiveMethod] = useState<OtpMethod>(() =>
    defaultMethod && availableMethods.includes(defaultMethod) ? defaultMethod : availableMethods[0]
  )
  const [code, setCode] = useState("")
  const [localError, setLocalError] = useState<string | null>(null)

  useEffect(() => {
    if (defaultMethod && availableMethods.includes(defaultMethod)) {
      setActiveMethod(defaultMethod)
    }
  }, [availableMethods, defaultMethod])

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault()
    const trimmed = code.trim()
    if (!trimmed) {
      setLocalError(t("mfa.otp.validation.required"))
      return
    }
    setLocalError(null)
    await onSubmit(activeMethod, trimmed)
  }

  const placeholders = useMemo(
    () => ({
      totp: t("mfa.otp.placeholders.totp"),
      recovery: t("mfa.otp.placeholders.recovery"),
    }),
    [t]
  )

  const titles = useMemo(
    () => ({
      totp: t("mfa.otp.methods.totp"),
      recovery: t("mfa.otp.methods.recovery"),
    }),
    [t]
  )

  const description = useMemo(() => {
    if (activeMethod === "recovery") {
      return t("mfa.otp.descriptions.recovery")
    }
    return t("mfa.otp.descriptions.totp")
  }, [activeMethod, t])

  const derivedError = localError || error

  return (
    <form onSubmit={handleSubmit} className="w-full">
      <div className="flex flex-col gap-4 items-stretch">
        {availableMethods.length > 1 ? (
          <div
            className="flex w-full border border-primary/30 rounded-lg overflow-hidden"
            role="group"
            aria-label={t("mfa.otp.methodToggle")}
          >
            {availableMethods.map((method) => (
              <button
                key={method}
                type="button"
                onClick={() => {
                  setActiveMethod(method)
                  setCode("")
                  setLocalError(null)
                }}
                className={`
                  flex-1 px-4 py-2 font-semibold transition-colors
                  ${
                    activeMethod === method
                      ? "bg-primary text-white"
                      : "bg-transparent text-primary hover:bg-primary/10"
                  }
                `}
              >
                {titles[method]}
              </button>
            ))}
          </div>
        ) : (
          <h3 className="text-base font-semibold text-center text-page-text">
            {titles[activeMethod]}
          </h3>
        )}

        <p className="text-sm text-page-text/70">{description}</p>

        <div>
          <label
            htmlFor="otp-input"
            className="block text-sm font-medium text-page-text mb-1 px-1 bg-card"
          >
            {titles[activeMethod]}
          </label>
          <input
            id="otp-input"
            autoFocus
            type="text"
            value={code}
            onChange={(e) => setCode(e.target.value)}
            placeholder={placeholders[activeMethod]}
            inputMode={activeMethod === "totp" ? "numeric" : "text"}
            disabled={Boolean(loading)}
            className={`
              w-full px-4 py-2.5 rounded-lg border bg-card text-page-text
              ${derivedError ? "border-red-500" : "border-page-text/25"}
              hover:border-page-text/35
              focus:outline-none focus:ring-3 focus:ring-primary/25 focus:border-primary
              disabled:bg-page-text/[0.06] disabled:border-page-text/20 disabled:cursor-not-allowed
              transition-all duration-200
            `}
          />
        </div>

        {derivedError ? (
          <p className="text-xs text-red-500">{derivedError}</p>
        ) : helperText ? (
          <p className="text-xs text-page-text/60">{helperText}</p>
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

        {activeMethod === "recovery" ? (
          <div className="flex items-center gap-2 px-4 py-2 rounded-lg border-2 border-yellow-500 text-yellow-500 bg-transparent">
            <span className="flex-1">{t("mfa.otp.recoveryWarning")}</span>
          </div>
        ) : null}
      </div>
    </form>
  )
}

export default OtpEntry
