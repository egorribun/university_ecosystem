import { useState, useEffect } from "react"
import axios from "@/api/client"
import { Link } from "react-router-dom"
import { useTranslation, Trans } from "react-i18next"
import { Button, TextField, SectionCard, Chip } from "@/components/settings"
import { motion, AnimatePresence } from "framer-motion"
import { ChevronLeft, Send as SendIcon, CheckCircle2 } from "lucide-react"
import { useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"

import { suggestEmailDomain } from "@/utils/authUtils"
import { resetPasswordSchema, type ResetPasswordValues } from "@/features/auth/schemas"

const FORGOT_URL = "/password/forgot"
const RESEND_COOLDOWN_SEC = 30

export default function ForgotPassword() {
  const { t } = useTranslation(["auth"])
  const [emailSuggestion, setEmailSuggestion] = useState<string | null>(null)
  const [cooldown, setCooldown] = useState(0)
  const [isSuccess, setIsSuccess] = useState(false)

  const {
    register,
    handleSubmit,
    setValue,
    watch,
    trigger,
    formState: { errors, isSubmitting },
    reset,
  } = useForm<ResetPasswordValues>({
    resolver: zodResolver(resetPasswordSchema),
    defaultValues: {
      email: "",
    },
    mode: "onBlur",
  })

  // Watch email for suggestions and UI logic
  const email = watch("email")

  useEffect(() => {
    if (!cooldown) return
    const id = setInterval(() => setCooldown((s) => Math.max(0, s - 1)), 1000)
    return () => clearInterval(id)
  }, [cooldown])

  const onBlurEmail = async () => {
    await trigger("email")
    if (email) {
      const s = suggestEmailDomain(email)
      setEmailSuggestion(s && s !== email ? s : null)
    }
  }

  const applySuggestion = () => {
    if (emailSuggestion) {
      setValue("email", emailSuggestion, { shouldValidate: true })
      setEmailSuggestion(null)
    }
  }

  const onSubmit = async (data: ResetPasswordValues) => {
    if (cooldown > 0) return

    try {
      await axios.post(FORGOT_URL, { email: data.email })
      // Even if API fails (security reasons), we often show success or generic message.
      // But here we'll assume success for the UX flow if no error thrown.
      // If the backend throws for non-existent email, we might want to catch that.
      // The original code caught all errors and ignored them ("Ignore errors, message is same for security").

      setCooldown(RESEND_COOLDOWN_SEC)
      setIsSuccess(true)
    } catch {
      // Ignore errors for security, pretend it worked
      setCooldown(RESEND_COOLDOWN_SEC)
      setIsSuccess(true)
    }
  }

  const resetRequest = () => {
    setIsSuccess(false)
    reset()
    setCooldown(0)
    setEmailSuggestion(null)
  }

  return (
    <div className="min-h-screen bg-page text-text-primary flex items-center justify-center p-6 relative overflow-hidden">
      {/* Background decorative elements */}
      <div className="absolute top-0 left-0 w-full h-full pointer-events-none opacity-dim">
<<<<<<< HEAD
        <div
          className="absolute bg-(--glow-spotlight-primary) rounded-full blur-(--glow-blur-massive)"
          style={{ top: "-10%", left: "-5%", width: "40%", height: "40%" }}
        />
        <div
          className="absolute bg-(--glow-spotlight-secondary) rounded-full blur-(--glow-blur-massive)"
          style={{ bottom: "-10%", right: "-5%", width: "40%", height: "40%" }}
        />
=======
        <div className="absolute top-[-10%] left-[-5%] w-2/5 h-2/5 bg-(--glow-spotlight-primary) rounded-full blur-(--glow-blur-massive)" />
        <div className="absolute bottom-[-10%] right-[-5%] w-2/5 h-2/5 bg-(--glow-spotlight-secondary) rounded-full blur-(--glow-blur-massive)" />
>>>>>>> origin/main
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
                {isSuccess
                  ? t("auth:forgot.successSent")
                  : t("auth:forgot.subtitle")}
              </p>
            </div>

            <AnimatePresence mode="wait">
              {isSuccess ? (
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
                  <form onSubmit={handleSubmit(onSubmit)} autoComplete="off" className="space-y-6">
                    <div className="space-y-3">
                      <TextField
                        id="forgot-email-input"
                        label={t("auth:fields.email")}
                        {...register("email")}
                        value={email}
                        type="email"
                        onBlur={onBlurEmail}
                        fullWidth
                        autoComplete="email"
                        error={!!errors.email}
                        helperText={errors.email?.message ? t(errors.email.message) : ""}
                        disabled={isSubmitting || cooldown > 0}
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

                    {errors.root?.message && (
                      <div
                        className="min-h-6 text-center text-sm font-semibold text-error-text animate-bounce"
                        aria-live="assertive"
                      >
                        {errors.root.message}
                      </div>
                    )}

                    <div className="space-y-4 pt-2">
                      <Button
                        id="forgot-submit-btn"
                        type="submit"
                        variant="solid"
                        className="w-full h-14 rounded-lg text-base font-black shadow-premium hover:shadow-glass hover:-translate-y-0.5 active:translate-y-0"
                        disabled={isSubmitting || cooldown > 0}
                        loading={isSubmitting}
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
