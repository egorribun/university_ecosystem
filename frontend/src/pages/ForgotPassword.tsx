import { useActionState, useEffect, useMemo, useRef, useState } from "react"
import axios from "@/api/client"
import { Link } from "react-router-dom"
import { useTranslation, Trans } from "react-i18next"
import { Button, TextField, SectionCard, Chip } from "@/components/settings"
import { motion, AnimatePresence } from "framer-motion"
import { ChevronLeft, Send as SendIcon, CheckCircle2 } from "lucide-react"
import { suggestEmailDomain } from "@/utils/authUtils"

const emailRe = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

const FORGOT_URL = "/password/forgot"
const RESEND_COOLDOWN_SEC = 30

type ForgotState = {
  status: "idle" | "success" | "error"
  email?: string
  error?: string
}

export default function ForgotPassword() {
  const { t } = useTranslation(["auth"])
  const [email, setEmail] = useState("")
  const [emailSuggestion, setEmailSuggestion] = useState<string | null>(null)
  const [cooldown, setCooldown] = useState(0)
  const emailInputRef = useRef<HTMLInputElement | null>(null)
  const emailValid = useMemo(() => email.length === 0 || emailRe.test(email), [email])

  useEffect(() => {
    if (!cooldown) return
    const id = setInterval(() => setCooldown((s) => Math.max(0, s - 1)), 1000)
    return () => clearInterval(id)
  }, [cooldown])

  const onBlurEmail = () => {
    const s = suggestEmailDomain(email)
    setEmailSuggestion(s && s !== email ? s : null)
  }

  const applySuggestion = () => {
    if (emailSuggestion) {
      setEmail(emailSuggestion)
      setEmailSuggestion(null)
    }
  }

  const [forgotState, forgotAction, forgotPending] = useActionState(
    async (_prev: ForgotState, input: FormData) => {
      if (input.get("__reset__") === "1") {
        return { status: "idle" as const }
      }

      const value = String(input.get("email") ?? "").trim()
      if (!emailRe.test(value)) {
        return { status: "error" as const, error: t("auth:messages.invalidEmail") }
      }

      setEmail(value)

      try {
        await axios.post(FORGOT_URL, { email: value })
      } catch {
        // Ignore errors, message is same for security
      }

      setCooldown(RESEND_COOLDOWN_SEC)
      return { status: "success" as const, email: value }
    },
    { status: "idle" as const }
  )

  const forgotStatus = forgotState.status
  const forgotErrorMessage = forgotStatus === "error" ? (forgotState.error ?? "") : ""
  const canSubmit = emailRe.test(email) && !forgotPending && cooldown === 0

  useEffect(() => {
    if (!forgotPending && forgotStatus === "error") {
      emailInputRef.current?.focus()
    }
  }, [forgotPending, forgotStatus])

  const resetRequest = () => {
    const marker = new FormData()
    marker.append("__reset__", "1")
    forgotAction(marker)
    setCooldown(0)
    setEmail("")
    setEmailSuggestion(null)
    emailInputRef.current?.focus()
  }

  return (
    <div className="min-h-screen bg-page text-text-primary flex items-center justify-center p-6 relative overflow-hidden">
      {/* Background decorative elements */}
      <div className="absolute top-0 left-0 w-full h-full pointer-events-none opacity-dim">
        <div className="absolute top-[-10%] left-[-5%] w-2/5 h-2/5 bg-(--glow-spotlight-primary) rounded-full blur-(--glow-blur-massive)" />
        <div className="absolute bottom-[-10%] right-[-5%] w-2/5 h-2/5 bg-(--glow-spotlight-secondary) rounded-full blur-(--glow-blur-massive)" />
      </div>

      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="w-full max-w-(--layout-max-dialog) z-modal"
      >
        <SectionCard className="p-8 sm:p-10 border-glass-border shadow-glass backdrop-blur-2xl rounded-4xl">
          <div className="space-y-8">
            <div className="text-center space-y-2">
              <h1 className="text-3xl font-black tracking-tight text-text-primary sm:text-4xl">
                {t("auth:forgot.title")}
              </h1>
              <p className="text-sm text-(--text-secondary) font-medium">
                {forgotStatus === "success"
                  ? t("auth:forgot.successSent")
                  : t("auth:forgot.subtitle")}
              </p>
            </div>

            <AnimatePresence mode="wait">
              {forgotStatus === "success" ? (
                <motion.div
                  key="success"
                  initial={{ opacity: 0, scale: 0.95 }}
                  animate={{ opacity: 1, scale: 1 }}
                  className="space-y-6 pt-4"
                >
                  <div className="flex justify-center">
                    <div className="h-20 w-20 rounded-lg bg-success-bg/(--opacity-dim) flex items-center justify-center text-success-text">
                      <CheckCircle2 className="h-10 w-10" />
                    </div>
                  </div>
                  <div className="text-center space-y-4">
                    <p className="text-body-sm leading-relaxed text-(--text-secondary)">
                      <Trans
                        ns="auth"
                        i18nKey="forgot.success"
                        values={{ email }}
                        components={{
                          strong: <span className="font-extrabold text-text-primary" />,
                        }}
                      />
                    </p>
                    <p className="text-xs font-bold text-brand uppercase tracking-widest opacity-strong">
                      {t("auth:forgot.successHint")}
                    </p>
                  </div>

                  <div className="space-y-3 pt-4">
                    <Button
                      id="forgot-back-to-login"
                      as={Link}
                      to="/login"
                      variant="solid"
                      className="w-full h-12 rounded-lg"
                    >
                      {t("auth:actions.backToLogin")}
                    </Button>
                    <Button
                      id="forgot-another-attempt"
                      variant="ghost"
                      onClick={resetRequest}
                      disabled={cooldown > 0}
                      className="w-full text-(--text-secondary) hover:text-text-primary"
                    >
                      {t("auth:forgot.enterAnother")}
                      {cooldown > 0 ? ` (${cooldown}s)` : ""}
                    </Button>
                  </div>
                </motion.div>
              ) : (
                <motion.div
                  key="form"
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  className="space-y-6"
                >
                  <form action={forgotAction} autoComplete="off" className="space-y-6">
                    <div className="space-y-3">
                      <TextField
                        id="forgot-email-input"
                        label={t("auth:fields.email")}
                        name="email"
                        type="email"
                        value={email}
                        onChange={(e) => setEmail(e.target.value)}
                        onBlur={onBlurEmail}
                        fullWidth
                        autoComplete="email"
                        error={!emailValid && email.length > 0}
                        helperText={
                          !emailValid && email.length > 0 ? t("auth:messages.invalidFormat") : ""
                        }
                        ref={emailInputRef}
                        disabled={forgotPending || cooldown > 0}
                        className="rounded-lg h-14"
                      />

                      {emailSuggestion && (
                        <motion.div initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }}>
                          <Chip
                            label={t("auth:messages.emailSuggestion", {
                              suggestion: emailSuggestion,
                            })}
                            onClick={applySuggestion}
                            color="primary"
                            className="cursor-pointer hover:bg-brand/(--opacity-subtle) transition-colors"
                          />
                        </motion.div>
                      )}
                    </div>

                    {forgotErrorMessage && (
                      <div
                        className="min-h-6 text-center text-sm font-semibold text-error-text animate-bounce"
                        aria-live="assertive"
                      >
                        {forgotErrorMessage}
                      </div>
                    )}

                    <div className="space-y-4 pt-2">
                      <Button
                        id="forgot-submit-btn"
                        type="submit"
                        variant="solid"
                        className="w-full h-14 rounded-lg text-base font-black shadow-premium hover:shadow-glass hover:-translate-y-0.5 active:translate-y-0"
                        disabled={!canSubmit}
                        loading={forgotPending}
                        startIcon={<SendIcon className="h-5 w-5" />}
                      >
                        {t("auth:forgot.sendLink")}
                      </Button>

                      <div className="pt-2 text-center">
                        <Link
                          to="/login"
                          className="inline-flex items-center gap-2 text-sm font-bold text-(--text-secondary) hover:text-brand transition-colors group"
                        >
                          <ChevronLeft className="h-4 w-4 transition-transform group-hover:-translate-x-1" />
                          {t("auth:actions.backToLogin")}
                        </Link>
                      </div>
                    </div>
                  </form>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </SectionCard>
      </motion.div>
    </div>
  )
}
