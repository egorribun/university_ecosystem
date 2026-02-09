import { useActionState, useEffect, useMemo, useRef, useState } from "react"
import axios from "../api/client"
import { Link } from "react-router-dom"
import { useTranslation, Trans } from "react-i18next"
import useMediaQuery from "@/hooks/useMediaQuery"
import { cn } from "@/utils/cn"
import { Button, TextField, SectionCard, Chip } from "@/components/settings"
import { motion, AnimatePresence } from "framer-motion"
import { Mail as EmailIcon, ChevronLeft, Send as SendIcon, CheckCircle2 } from "lucide-react"
import { Input } from "@/components/ui"
import { breakpoints } from "@/theme/tokens"

const emailRe = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
const COMMON_EMAIL_DOMAINS = [
  "gmail.com",
  "googlemail.com",
  "yahoo.com",
  "outlook.com",
  "hotmail.com",
  "live.com",
  "icloud.com",
  "mail.ru",
  "bk.ru",
  "list.ru",
  "inbox.ru",
  "yandex.ru",
  "yandex.com",
  "rambler.ru",
  "proton.me",
]

function levenshtein(a: string, b: string) {
  const m = a.length,
    n = b.length
  if (!m) return n
  if (!n) return m
  const dp = Array.from({ length: m + 1 }, () => new Array(n + 1).fill(0))
  for (let i = 0; i <= m; i++) dp[i][0] = i
  for (let j = 0; j <= n; j++) dp[0][j] = j
  for (let i = 1; i <= m; i++) {
    for (let j = 1; j <= n; j++) {
      const cost = a[i - 1] === b[j - 1] ? 0 : 1
      dp[i][j] = Math.min(dp[i - 1][j] + 1, dp[i][j - 1] + 1, dp[i - 1][j - 1] + cost)
    }
  }
  return dp[m][n]
}

function suggestEmailDomain(email: string) {
  const at = email.indexOf("@")
  if (at < 0) return null
  const local = email.slice(0, at).trim()
  const dom = email
    .slice(at + 1)
    .trim()
    .toLowerCase()
  if (!local || !dom) return null
  if (COMMON_EMAIL_DOMAINS.includes(dom)) return null
  let best: { d: string; dist: number } | null = null
  for (const cand of COMMON_EMAIL_DOMAINS) {
    const dist = levenshtein(dom, cand)
    if (dist <= 2 && (!best || dist < best.dist)) best = { d: cand, dist }
  }
  return best ? `${local}@${best.d}` : null
}

const FORGOT_URL = "/password/forgot"

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
  const isMobile = useMediaQuery(`(max-width: ${breakpoints.mobile})`)
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

      setCooldown(30)
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
    <div className="min-h-screen bg-(--bg-page) text-(--text-primary) flex items-center justify-center p-6 relative overflow-hidden">
      {/* Background decorative elements */}
      <div className="absolute top-0 left-0 w-full h-full pointer-events-none opacity-20">
        <div className="absolute top-[-10%] left-[-5%] w-[40%] h-[40%] bg-brand/30 rounded-full blur-[120px]" />
        <div className="absolute bottom-[-10%] right-[-5%] w-[40%] h-[40%] bg-brand/20 rounded-full blur-[120px]" />
      </div>

      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="w-full max-w-[440px] z-10"
      >
        <SectionCard className="p-8 sm:p-10 border-glass-border shadow-2xl backdrop-blur-2xl">
          <div className="space-y-8">
            <div className="text-center space-y-2">
              <h1 className="text-3xl font-black tracking-tight text-(--text-primary) sm:text-4xl">
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
                    <div className="h-20 w-20 rounded-3xl bg-emerald-500/10 flex items-center justify-center text-emerald-500">
                      <CheckCircle2 className="h-10 w-10" />
                    </div>
                  </div>
                  <div className="text-center space-y-4">
                    <p className="text-[15px] leading-relaxed text-(--text-secondary)">
                      <Trans
                        ns="auth"
                        i18nKey="forgot.success"
                        values={{ email }}
                        components={{
                          strong: <span className="font-extrabold text-(--text-primary)" />,
                        }}
                      />
                    </p>
                    <p className="text-xs font-bold text-brand uppercase tracking-widest opacity-70">
                      {t("auth:forgot.successHint")}
                    </p>
                  </div>

                  <div className="space-y-3 pt-4">
                    <Button
                      as={Link}
                      to="/login"
                      variant="solid"
                      className="w-full h-12 rounded-2xl"
                    >
                      {t("auth:actions.backToLogin")}
                    </Button>
                    <Button
                      variant="ghost"
                      onClick={resetRequest}
                      disabled={cooldown > 0}
                      className="w-full text-(--text-secondary) hover:text-(--text-primary)"
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
                        id="email"
                        label={t("auth:fields.email")}
                        name="email"
                        type="email"
                        value={email}
                        onChange={(e) => setEmail(e.target.value)}
                        onBlur={onBlurEmail}
                        autoFocus
                        fullWidth
                        autoComplete="email"
                        error={!emailValid && email.length > 0}
                        helperText={
                          !emailValid && email.length > 0 ? t("auth:messages.invalidFormat") : ""
                        }
                        ref={emailInputRef}
                        disabled={forgotPending || cooldown > 0}
                        className="rounded-2xl h-14"
                      />

                      {emailSuggestion && (
                        <motion.div initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }}>
                          <Chip
                            label={t("auth:messages.emailSuggestion", {
                              suggestion: emailSuggestion,
                            })}
                            onClick={applySuggestion}
                            color="primary"
                            variant="outlined"
                            className="cursor-pointer hover:bg-brand/5 transition-colors"
                          />
                        </motion.div>
                      )}
                    </div>

                    {forgotErrorMessage && (
                      <p className="text-sm font-bold text-rose-500 text-center animate-bounce">
                        {forgotErrorMessage}
                      </p>
                    )}

                    <div className="space-y-4 pt-2">
                      <Button
                        type="submit"
                        variant="solid"
                        className="w-full h-14 rounded-2xl text-base font-black shadow-lg shadow-brand/20 transition-all hover:shadow-brand/30 hover:-translate-y-0.5 active:translate-y-0"
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





