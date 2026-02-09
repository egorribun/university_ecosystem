import {
  useId,
  useState,
  useRef,
  KeyboardEvent,
  ClipboardEvent,
  useCallback,
  useEffect,
} from "react"
import { useTranslation } from "react-i18next"
import { cn } from "@/utils/cn"
import { Button } from "@/components/settings"
import { ShieldAlert, CheckCircle2 } from "lucide-react"

type OtpEntryProps = {
  loading?: boolean
  error?: string | null
  helperText?: string | null
  onSubmit: (code: string) => Promise<void> | void
}

export const OtpEntry = ({ loading, error, helperText, onSubmit }: OtpEntryProps) => {
  const { t } = useTranslation("auth")
  const [digits, setDigits] = useState<string[]>(["", "", "", "", "", ""])
  const [localError, setLocalError] = useState<string | null>(null)
  const [focusedIndex, setFocusedIndex] = useState<number | null>(null)
  const inputRefs = useRef<(HTMLInputElement | null)[]>([])
  const helperId = useId()
  const errorId = useId()
  const code = digits.join("")

  const submitCode = useCallback(async () => {
    if (loading || code.length !== 6) {
      setLocalError(t("mfa.otp.validation.required"))
      return
    }
    setLocalError(null)
    await onSubmit(code)
  }, [code, loading, onSubmit, t])

  const handleChange = (index: number, value: string) => {
    const sanitized = value.replace(/\D/g, "")

    if (sanitized.length === 0) {
      const newDigits = [...digits]
      newDigits[index] = ""
      setDigits(newDigits)
      return
    }

    if (sanitized.length === 1) {
      const newDigits = [...digits]
      newDigits[index] = sanitized
      setDigits(newDigits)

      if (index < 5) {
        inputRefs.current[index + 1]?.focus()
      }
    } else if (sanitized.length > 1) {
      const newDigits = [...digits]
      for (let i = 0; i < sanitized.length && index + i < 6; i++) {
        newDigits[index + i] = sanitized[i]
      }
      setDigits(newDigits)

      const lastIndex = Math.min(index + sanitized.length, 5)
      inputRefs.current[lastIndex]?.focus()
    }
  }

  const handleKeyDown = (index: number, event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Backspace") {
      if (digits[index] === "") {
        if (index > 0) {
          event.preventDefault()
          inputRefs.current[index - 1]?.focus()
        }
      }
    } else if (event.key === "ArrowLeft" && index > 0) {
      event.preventDefault()
      inputRefs.current[index - 1]?.focus()
    } else if (event.key === "ArrowRight" && index < 5) {
      event.preventDefault()
      inputRefs.current[index + 1]?.focus()
    }
  }

  const handlePaste = (event: ClipboardEvent<HTMLInputElement>) => {
    event.preventDefault()
    const pastedData = event.clipboardData.getData("text")
    const sanitized = pastedData.replace(/\D/g, "").slice(0, 6)

    if (sanitized.length > 0) {
      const newDigits = [...digits]
      for (let i = 0; i < 6; i++) {
        newDigits[i] = sanitized[i] || ""
      }
      setDigits(newDigits)
      const lastIndex = Math.min(sanitized.length - 1, 5)
      inputRefs.current[lastIndex]?.focus()
    }
  }

  const derivedError = localError || error
  const derivedHelperText = derivedError ? null : (helperText ?? null)
  const describedBy = derivedError ? errorId : derivedHelperText ? helperId : undefined

  useEffect(() => {
    if (!error) return
    setDigits(["", "", "", "", "", ""])
    inputRefs.current[0]?.focus()
  }, [error])

  useEffect(() => {
    if (code.length === 6 && !loading && !localError && !error) {
      void onSubmit(code)
    }
  }, [code, loading, onSubmit, localError, error])

  return (
    <div className="w-full">
      <div className="flex flex-col gap-6 items-stretch">
        <h3 className="text-lg font-black tracking-tight text-center text-(--text-primary)">
          {t("mfa.otp.methods.totp")}
        </h3>

        <p className="text-sm text-center text-(--text-secondary) font-medium leading-relaxed">
          {t("mfa.otp.descriptions.totp")}
        </p>

        <div
          className="flex gap-2 sm:gap-3 justify-center"
          aria-describedby={describedBy}
          role="group"
        >
          {digits.map((digit, index) => (
            <input
              key={index}
              ref={(el) => {
                inputRefs.current[index] = el
              }}
              type="text"
              inputMode="numeric"
              maxLength={1}
              value={digit}
              autoFocus={index === 0}
              disabled={Boolean(loading)}
              aria-label={index === 0 ? t("mfa.otp.methods.totp") : undefined}
              onChange={(e) => handleChange(index, e.target.value)}
              onKeyDown={(e) => handleKeyDown(index, e)}
              onPaste={index === 0 ? handlePaste : undefined}
              onFocus={() => setFocusedIndex(index)}
              onBlur={() => setFocusedIndex(null)}
              className={cn(
                "w-11 h-14 sm:w-14 sm:h-18 text-center text-2xl font-black rounded-2xl",
                "bg-(--bg-surface-raised)/40 text-(--text-primary) border-2 transition-all duration-300",
                "focus:outline-none backdrop-blur-md shadow-sm",
                derivedError
                  ? "border-rose-500/50 focus:border-rose-500 focus:ring-4 focus:ring-rose-500/10"
                  : focusedIndex === index
                    ? "border-brand ring-4 ring-brand/10 scale-105 shadow-brand/10 shadow-lg"
                    : digit
                      ? "border-brand/40 bg-brand/5"
                      : "border-glass-border/20 hover:border-glass-border/40 hover:bg-(--bg-surface-hover)/5",
                "disabled:opacity-40 disabled:cursor-not-allowed disabled:grayscale"
              )}
              aria-invalid={derivedError ? "true" : "false"}
            />
          ))}
        </div>

        {derivedError ? (
          <div className="flex items-center justify-center gap-2 animate-bounce">
            <ShieldAlert className="h-4 w-4 text-rose-500" />
            <p id={errorId} className="text-xs font-bold text-rose-500">
              {derivedError}
            </p>
          </div>
        ) : derivedHelperText ? (
          <p id={helperId} className="text-xs font-bold text-center text-(--text-secondary) opacity-60">
            {derivedHelperText}
          </p>
        ) : null}

        {loading && (
          <div className="flex justify-center items-center py-4">
            <div className="h-8 w-8 rounded-full border-4 border-brand/10 border-t-brand animate-spin" />
          </div>
        )}

        <div className="flex justify-center pt-2">
          <Button
            variant="solid"
            onClick={() => void submitCode()}
            disabled={loading || code.length !== 6}
            className="w-full max-w-xs h-14 rounded-2xl font-black shadow-lg shadow-brand/20"
            loading={loading}
          >
            {t("mfa.otp.submit")}
          </Button>
        </div>
      </div>
    </div>
  )
}

export default OtpEntry





