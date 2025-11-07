import { FormEvent, useEffect, useId, useMemo, useState } from "react"
import { useTranslation } from "react-i18next"
import type { MfaMethod } from "@/types/Mfa"
import { Alert, Button } from "@/components/ui"
import { cn } from "@/utils/cn"

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
  const inputId = useId()

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
  const hasMultipleMethods = availableMethods.length > 1
  const errorId = derivedError ? `${inputId}-error` : undefined
  const helperId = !derivedError && helperText ? `${inputId}-helper` : undefined

  const inputBaseClass = cn(
    "w-full rounded-ue-lg border border-[color:color-mix(in_srgb,var(--page-text)_12%,transparent)]",
    "bg-[color:color-mix(in_srgb,var(--card-bg)_96%,white_4%)] px-4 py-2.5 text-[1.05rem] font-semibold tracking-[0.58em] text-page-foreground",
    "placeholder:tracking-normal placeholder:text-[color:color-mix(in_srgb,var(--placeholder-fg)_78%,transparent)]",
    "focus:outline-none focus:ring-2 focus:ring-[color:color-mix(in_srgb,var(--nav-link)_42%,transparent)] focus:border-transparent",
    "transition-[border-color,box-shadow,background-color] duration-200 ease-out",
    "font-mono uppercase leading-tight selection:bg-[color:color-mix(in_srgb,var(--nav-link)_28%,transparent)] selection:text-white"
  )
  const inputErrorClass =
    "border-[color:rgba(248,113,113,0.55)] focus:ring-[color:rgba(248,113,113,0.52)] bg-[color:rgba(248,113,113,0.08)]"

  const methodToggleBase =
    "flex-1 rounded-ue-lg px-3 py-2 text-sm font-semibold tracking-tight transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:color-mix(in_srgb,var(--nav-link)_45%,transparent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[color:color-mix(in_srgb,var(--card-bg)_94%,white_6%)]"
  const methodToggleActive =
    "bg-btn-gradient text-white shadow-surface hover:bg-btn-gradient-hover hover:shadow-surface-strong"
  const methodToggleInactive =
    "border border-[color:color-mix(in_srgb,var(--page-text)_12%,transparent)] bg-[color:color-mix(in_srgb,var(--card-bg)_94%,white_6%)] text-[color:color-mix(in_srgb,var(--secondary-text)_85%,transparent)] hover:border-[color:color-mix(in_srgb,var(--nav-link)_28%,transparent)] hover:text-nav-link"

  return (
    <form className="w-full" onSubmit={handleSubmit} noValidate>
      <div className="flex flex-col gap-4">
        {hasMultipleMethods ? (
          <div
            role="tablist"
            aria-label={t("mfa.otp.methodToggle")}
            className={cn(
              "flex w-full gap-2 rounded-ue-xl border border-[color:color-mix(in_srgb,var(--page-text)_12%,transparent)]",
              "bg-[color:color-mix(in_srgb,var(--card-bg)_95%,var(--nav-link)_5%)] p-1 shadow-[inset_0_1px_0_rgba(255,255,255,0.12)]"
            )}
          >
            {availableMethods.map((method) => (
              <button
                key={method}
                type="button"
                role="tab"
                aria-selected={activeMethod === method}
                className={cn(
                  methodToggleBase,
                  activeMethod === method ? methodToggleActive : methodToggleInactive
                )}
                onClick={() => {
                  if (method === activeMethod) return
                  setActiveMethod(method)
                  setCode("")
                  setLocalError(null)
                }}
              >
                {titles[method]}
              </button>
            ))}
          </div>
        ) : (
          <p className="text-center text-[1.05rem] font-semibold text-page-foreground">
            {titles[activeMethod]}
          </p>
        )}

        <p className="text-sm font-medium text-[color:color-mix(in_srgb,var(--page-text)_72%,transparent)]">
          {description}
        </p>

        <label className="flex flex-col gap-2">
          <span className="text-xs font-semibold uppercase tracking-wide text-[color:color-mix(in_srgb,var(--secondary-text)_85%,transparent)]">
            {titles[activeMethod]}
          </span>
          <input
            id={inputId}
            type="text"
            value={code}
            onChange={(event) => setCode(event.target.value)}
            placeholder={placeholders[activeMethod]}
            inputMode={activeMethod === "totp" ? "numeric" : "text"}
            autoFocus
            disabled={Boolean(loading)}
            aria-invalid={derivedError ? "true" : undefined}
            aria-describedby={errorId ?? helperId}
            className={cn(inputBaseClass, derivedError && inputErrorClass)}
          />
        </label>

        {derivedError ? (
          <p
            id={errorId}
            role="alert"
            className="text-sm font-semibold text-[color:rgba(248,113,113,0.92)]"
          >
            {derivedError}
          </p>
        ) : helperText ? (
          <p
            id={helperId}
            className="text-sm text-[color:color-mix(in_srgb,var(--page-text)_68%,transparent)]"
          >
            {helperText}
          </p>
        ) : null}

        <Button type="submit" loading={Boolean(loading)} fullWidth>
          {loading ? t("mfa.otp.submitting") : t("mfa.otp.submit")}
        </Button>

        {activeMethod === "recovery" ? (
          <Alert tone="warning" role="status">
            {t("mfa.otp.recoveryWarning")}
          </Alert>
        ) : null}
      </div>
    </form>
  )
}

export default OtpEntry
