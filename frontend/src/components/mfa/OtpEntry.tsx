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
import { ShieldAlert } from "lucide-react"

type OtpEntryProps = {
  method?: "totp" | "email_otp"
  loading?: boolean
  error?: string | null
  helperText?: string | null
  onSubmit: (code: string) => Promise<void> | void
}

const OTP_LENGTH = 6
const EMPTY_DIGITS = (): string[] => Array.from({ length: OTP_LENGTH }, () => "")

export const OtpEntry = ({
  method = "totp",
  loading,
  error,
  helperText,
  onSubmit,
}: OtpEntryProps) => {
  const { t } = useTranslation("auth")
  const [digits, setDigits] = useState<string[]>(EMPTY_DIGITS)
  const [localError, setLocalError] = useState<string | null>(null)
  const [focusedIndex, setFocusedIndex] = useState<number | null>(null)
  const inputRefs = useRef<(HTMLInputElement | null)[]>([])
  const helperId = useId()
  const errorId = useId()
  const code = digits.join("")

  const focusInput = useCallback((index: number) => {
    const input = inputRefs.current[index]
    if (input) input.focus()
  }, [])

  const submitCode = useCallback(async () => {
    if (loading || code.length !== OTP_LENGTH) {
      setLocalError(t("mfa.otp.validation.required"))
      return
    }
    setLocalError(null)
    await onSubmit(code)
  }, [code, loading, onSubmit, t])

  const handleChange = (index: number, value: string) => {
    const sanitized = value.replace(/\D/g, "")

    if (sanitized.length === 0) {
      setDigits((prev) => {
        const next = [...prev]
        next[index] = ""
        return next
      })
      return
    }

    if (sanitized.length === 1) {
      setDigits((prev) => {
        const next = [...prev]
        next[index] = sanitized
        return next
      })

      if (index < OTP_LENGTH - 1) {
        focusInput(index + 1)
      }
    } else {
      setDigits((prev) => {
        const next = [...prev]
        const available = OTP_LENGTH - index
        sanitized
          .slice(0, available)
          .split("")
          .forEach((digit, offset) => {
            next[index + offset] = digit
          })
        return next
      })

      const lastIndex = Math.min(index + sanitized.length, OTP_LENGTH - 1)
      focusInput(lastIndex)
    }
  }

  const handleKeyDown = (index: number, event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Backspace") {
      if (digits[index] === "") {
        if (index > 0) {
          event.preventDefault()
          focusInput(index - 1)
        }
      }
    } else if (event.key === "ArrowLeft" && index > 0) {
      event.preventDefault()
      focusInput(index - 1)
    } else if (event.key === "ArrowRight" && index < OTP_LENGTH - 1) {
      event.preventDefault()
      focusInput(index + 1)
    }
  }

  const handlePaste = (event: ClipboardEvent<HTMLInputElement>) => {
    event.preventDefault()
    const pastedData = event.clipboardData.getData("text")
    const sanitized = pastedData.replace(/\D/g, "").slice(0, OTP_LENGTH)

    if (sanitized.length > 0) {
      setDigits(Array.from({ length: OTP_LENGTH }, (_, offset) => sanitized.charAt(offset)))
      const lastIndex = Math.min(sanitized.length - 1, OTP_LENGTH - 1)
      focusInput(lastIndex)
    }
  }

  const derivedError = localError || error
  const derivedHelperText = derivedError ? null : (helperText ?? null)
  const describedBy = derivedError ? errorId : derivedHelperText ? helperId : undefined

  useEffect(() => {
    if (!error) return
    setDigits(EMPTY_DIGITS)
    focusInput(0)
  }, [error, focusInput])

  useEffect(() => {
    if (code.length === OTP_LENGTH && !loading && !localError && !error) {
      void onSubmit(code)
    }
  }, [code, loading, onSubmit, localError, error])

  useEffect(() => {
    // Auto-focus the first input on initial render
    if (digits.every((d) => d === "")) {
      focusInput(0)
    }
    // We only want this on mount for the "fresh" state
  }, [digits, focusInput])

  return (
    <div className="w-full">
      <div className="flex flex-col gap-6 items-stretch">
        <h3 className="text-lg font-black tracking-tight text-center text-text-primary">
          {t(`mfa.otp.methods.${method}`)}
        </h3>

        <p className="text-sm text-center text-(--text-secondary) font-medium leading-relaxed">
          {t(`mfa.otp.descriptions.${method}`)}
        </p>

        <div
          className="flex gap-2 sm:gap-3 justify-center"
          aria-describedby={describedBy}
          role="group"
        >
          {digits.map((digit, index) => (
            <input
              key={`otp-digit-${index}`}
              ref={(el) => {
                inputRefs.current[index] = el
              }}
              type="text"
              inputMode="numeric"
              maxLength={1}
              value={digit}
              // eslint-disable-next-line jsx-a11y/no-autofocus
              autoFocus={index === 0}
              disabled={Boolean(loading)}
              aria-label={t(`mfa.otp.methods.${method}`) + " - digit " + (index + 1)}
              onChange={(e) => handleChange(index, e.target.value)}
              onKeyDown={(e) => handleKeyDown(index, e)}
              onPaste={index === 0 ? handlePaste : undefined}
              onFocus={() => setFocusedIndex(index)}
              onBlur={() => setFocusedIndex(null)}
              className={cn(
                "w-11 h-14 sm:w-14 sm:h-18 text-center text-2xl font-black rounded-2xl",
                "bg-(--bg-surface-raised)/(--opacity-medium) text-text-primary border-2 transition-all duration-base",
                "focus:outline-none backdrop-blur-md shadow-sm",
                derivedError
                  ? "border-(--error-border)/(--opacity-medium) focus:border-(--error-border) focus:ring-4 focus:ring-(--error-border)/(--opacity-subtle)"
                  : focusedIndex === index
                    ? "border-(--brand-main) ring-4 ring-(--brand-main)/(--opacity-subtle) scale-105 shadow-(--brand-main)/(--opacity-subtle) shadow-lg"
                    : digit
                      ? "border-brand-main/(--opacity-medium) bg-brand-main/(--opacity-faint)"
                      : "border-(--glass-border)/(--opacity-dim) hover:border-(--glass-border)/(--opacity-medium) hover:bg-(--bg-surface-hover)/(--opacity-faint)",
                "disabled:opacity-dim disabled:cursor-not-allowed disabled:grayscale"
              )}
              aria-invalid={derivedError ? "true" : "false"}
            />
          ))}
        </div>

        {derivedError ? (
          <div className="flex items-center justify-center gap-2 animate-bounce">
            <ShieldAlert className="h-4 w-4 text-error-text" />
            <p id={errorId} className="text-xs font-bold text-error-text">
              {derivedError}
            </p>
          </div>
        ) : derivedHelperText ? (
          <p
            id={helperId}
            className="text-xs font-bold text-center text-(--text-secondary) opacity-medium"
          >
            {derivedHelperText}
          </p>
        ) : null}

        {loading && (
          <div className="flex justify-center items-center py-4">
            <div className="h-8 w-8 rounded-full border-4 border-(--brand-main)/(--opacity-subtle) border-t-(--brand-main) animate-spin" />
          </div>
        )}

        <div className="flex justify-center pt-2">
          <Button
            variant="solid"
            onClick={() => void submitCode()}
            disabled={loading || code.length !== OTP_LENGTH}
            className="w-full max-w-xs h-14 rounded-2xl font-black shadow-lg shadow-(--brand-main)/(--opacity-dim)"
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
