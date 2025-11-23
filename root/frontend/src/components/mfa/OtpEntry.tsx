import { useId, useState, useRef, KeyboardEvent, ClipboardEvent, useCallback, useEffect } from "react"
import { Button } from "@mui/material"
import { useTranslation } from "react-i18next"

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
    // Only allow digits
    const sanitized = value.replace(/\D/g, "")

    if (sanitized.length === 0) {
      // Clear current input
      const newDigits = [...digits]
      newDigits[index] = ""
      setDigits(newDigits)
      return
    }

    if (sanitized.length === 1) {
      // Single digit input
      const newDigits = [...digits]
      newDigits[index] = sanitized
      setDigits(newDigits)

      // Auto-advance to next input
      if (index < 5) {
        inputRefs.current[index + 1]?.focus()
      }
    } else if (sanitized.length > 1) {
      // Multiple digits (paste or fast typing)
      const newDigits = [...digits]
      for (let i = 0; i < sanitized.length && index + i < 6; i++) {
        newDigits[index + i] = sanitized[i]
      }
      setDigits(newDigits)

      // Focus last filled input or the last one
      const lastIndex = Math.min(index + sanitized.length, 5)
      inputRefs.current[lastIndex]?.focus()
    }
  }

  const handleKeyDown = (index: number, event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Backspace") {
      if (digits[index] === "") {
        // Move to previous input if current is empty
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

      // Focus last filled input
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

  return (
    <div className="w-full">
      <div className="flex flex-col gap-6 items-stretch">
        <h3 className="text-base font-semibold text-center text-page-text">
          {t("mfa.otp.methods.totp")}
        </h3>

        <p className="text-sm text-center text-page-text/70">{t("mfa.otp.descriptions.totp")}</p>

        <div
          className="flex gap-2 justify-center"
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
              className={`
                w-12 h-14 sm:w-14 sm:h-16 text-center text-2xl font-bold rounded-xl
                bg-card text-page-text border-2 transition-all duration-200
                ${
                  derivedError
                    ? "border-red-500 focus:border-red-500 focus:ring-red-500/25"
                    : focusedIndex === index
                      ? "border-primary ring-4 ring-primary/25 scale-105"
                      : digit
                        ? "border-primary/50"
                        : "border-page-text/20 hover:border-page-text/30"
                }
                focus:outline-none
                disabled:bg-page-text/[0.06] disabled:border-page-text/15 disabled:cursor-not-allowed
                shadow-sm hover:shadow-md
                ${focusedIndex === index ? "shadow-lg shadow-primary/20" : ""}
              `}
              aria-invalid={derivedError ? "true" : "false"}
            />
          ))}
        </div>

        {derivedError ? (
          <p id={errorId} className="text-xs text-center text-red-500 animate-shake">
            {derivedError}
          </p>
        ) : derivedHelperText ? (
          <p id={helperId} className="text-xs text-center text-page-text/60">
            {derivedHelperText}
          </p>
        ) : null}

        {loading && (
          <div className="flex justify-center items-center py-3">
            <div className="animate-spin rounded-full h-6 w-6 border-2 border-primary border-t-transparent" />
          </div>
        )}

        <div className="flex justify-center">
          <Button
            variant="contained"
            color="primary"
            onClick={() => void submitCode()}
            disabled={loading || code.length !== 6}
          >
            {loading ? t("mfa.otp.submitting") : t("mfa.otp.submit")}
          </Button>
        </div>
      </div>
    </div>
  )
}

export default OtpEntry
