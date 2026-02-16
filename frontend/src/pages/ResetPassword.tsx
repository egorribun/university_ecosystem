import { useActionState, useEffect, useRef, useState } from "react"
import api from "@/api/client"
import { useParams, useSearchParams, Link } from "react-router-dom"
import { useTranslation } from "react-i18next"
import { motion, AnimatePresence } from "framer-motion"
import {
  Eye as Visibility,
  EyeOff as VisibilityOff,
  ChevronLeft,
  Lock as LockIcon,
  CheckCircle2,
  ShieldCheck,
  AlertTriangle,
} from "lucide-react"

import { Button, TextField, SectionCard, Alert } from "@/components/settings"
import { ProgressBar } from "@/components/ui"

const RESET_URL = "/password/reset"

const MIN_PASSWORD_LENGTH = 8
const STRENGTH_VALUES = [10, 30, 55, 75, 100]

type ResetState = {
  status: "idle" | "success" | "error"
  error?: string
  field?: "password" | "confirm"
}

async function sha1Hex(str: string) {
  const buf = new TextEncoder().encode(str)
  const hash = await crypto.subtle.digest("SHA-1", buf)
  return Array.from(new Uint8Array(hash))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("")
    .toUpperCase()
}

const PWNED_API_URL = "https://api.pwnedpasswords.com/range/"
const HASH_PREFIX_LEN = 5

async function isPwnedPassword(pwd: string) {
  if (!pwd) return false
  const hash = await sha1Hex(pwd)
  const prefix = hash.slice(0, HASH_PREFIX_LEN)
  const suffix = hash.slice(HASH_PREFIX_LEN)
  const resp = await fetch(`${PWNED_API_URL}${prefix}`)
  if (!resp.ok) return false
  const text = await resp.text()
  return text.split("\n").some((line) => line.split(":")[0] === suffix)
}

export default function ResetPassword() {
  const { t } = useTranslation(["auth"])
  const routeParameters = useParams<{ token?: string }>()
  const [searchParameters] = useSearchParams()
  const token = routeParameters.token || searchParameters.get("token") || ""

  const [password, setPassword] = useState("")
  const [confirm, setConfirm] = useState("")
  const [capsPass, setCapsPass] = useState(false)
  const [capsConfirm, setCapsConfirm] = useState(false)
  const [showPass, setShowPass] = useState(false)
  const [showConfirm, setShowConfirm] = useState(false)
  const [strength, setStrength] = useState<number | null>(null)
  const [feedback, setFeedback] = useState<string>("")
  const [pwned, setPwned] = useState(false)
  const passwordRef = useRef<HTMLInputElement | null>(null)
  const confirmRef = useRef<HTMLInputElement | null>(null)

  const minLenOk = password.length >= MIN_PASSWORD_LENGTH
  const matchOk = confirm.length > 0 && password === confirm
  const canSubmit = token && minLenOk && matchOk

  const onPass = async (value: string) => {
    setPassword(value)
    setFeedback("")
    if (!value) {
      setStrength(null)
      setPwned(false)
      return
    }
    try {
      const { zxcvbn, zxcvbnOptions } = await import("@zxcvbn-ts/core")
      const zxcvbnCommon = await import("@zxcvbn-ts/language-common")
      zxcvbnOptions.setOptions(zxcvbnCommon)
      const complexityResult = zxcvbn(value)
      setStrength(complexityResult.score)
      const tips =
        (complexityResult.feedback?.warning || "") +
        (complexityResult.feedback?.suggestions?.length
          ? " · " + complexityResult.feedback.suggestions.join(" · ")
          : "")
      setFeedback(tips)
    } catch {
      setStrength(null)
    }
    try {
      const bad = await isPwnedPassword(value)
      if (value === password) setPwned(bad)
    } catch {
      // ignore
    }
  }

  const [resetState, resetAction, resetPending] = useActionState<ResetState, FormData>(
    async (_previousState, formData) => {
      if (formData.get("__set_error__")) {
        return { status: "error" as const, error: String(formData.get("__set_error__")) }
      }

      const pwd = String(formData.get("password") ?? "")
      const confirmValue = String(formData.get("confirm") ?? "")

      if (!token) {
        return { status: "error" as const, error: t("auth:reset.invalidLink") }
      }

      if (pwd !== confirmValue) {
        return {
          status: "error" as const,
          error: t("auth:register.passwordMismatch"),
          field: "confirm" as const,
        }
      }

      try {
        await api.post(RESET_URL, { token, password: pwd })
        return { status: "success" as const }
      } catch (error: unknown) {
        let errorMessage = t("auth:reset.errorGeneric")
        if (typeof error === "object" && error !== null && "response" in error) {
          const axiosError = error as { response?: { data?: { detail?: string } } }
          errorMessage = axiosError.response?.data?.detail || errorMessage
        }
        return { status: "error" as const, error: errorMessage }
      }
    },
    token
      ? { status: "idle" as const }
      : { status: "error" as const, error: t("auth:reset.invalidLink") }
  )

  const resetStatus = resetState.status
  const resetErrorMessage = resetStatus === "error" ? (resetState.error ?? "") : ""

  useEffect(() => {
    if (!resetPending && resetStatus === "error" && resetState.field) {
      if (resetState.field === "password") passwordRef.current?.focus()
      else if (resetState.field === "confirm") confirmRef.current?.focus()
    }
  }, [resetPending, resetStatus, resetState.field])

  const isSuccess = resetStatus === "success"

  return (
    <div className="min-h-screen bg-page text-text-primary flex items-center justify-center p-(--fluid-px) relative overflow-hidden">
      {/* Background decorative elements */}
      <div className="absolute top-0 left-0 w-full h-full pointer-events-none opacity-dim">
        <div className="absolute top-[-10%] right-[-5%] w-2/5 h-2/5 bg-(--glow-spotlight-primary) rounded-full blur-(--glow-blur-massive)" />
        <div className="absolute bottom-[-10%] left-[-5%] w-2/5 h-2/5 bg-(--glow-spotlight-secondary) rounded-full blur-(--glow-blur-massive)" />
      </div>

      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="w-full max-w-(--layout-max-modal) z-modal"
      >
        <SectionCard className="p-(--fluid-card-p) border-glass-border shadow-glass backdrop-blur-2xl rounded-4xl">
          <div className="space-y-8">
            <AnimatePresence mode="wait">
              {isSuccess ? (
                <motion.div
                  key="success"
                  initial={{ opacity: 0, scale: 0.95 }}
                  animate={{ opacity: 1, scale: 1 }}
                  className="space-y-6 pt-4 text-center"
                >
                  <div className="flex justify-center">
                    <div className="h-20 w-20 rounded-lg bg-success-bg flex items-center justify-center text-success-text">
                      <CheckCircle2 size={40} />
                    </div>
                  </div>
                  <div className="space-y-2">
                    <h2 className="text-2xl font-black tracking-tight text-text-primary">
                      {t("auth:reset.successTitle")}
                    </h2>
                    <p className="text-sm text-text-secondary font-medium leading-relaxed">
                      {t("auth:reset.successMessage")}
                    </p>
                  </div>
                  <div className="pt-4">
                    <Button
                      id="reset-success-login"
                      as={Link}
                      to="/login"
                      variant="solid"
                      className="w-full h-12 rounded-lg"
                    >
                      {t("auth:actions.goToLogin")}
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
                  <div className="text-center space-y-2">
                    <h1 className="text-5xl font-black tracking-tight text-text-primary">
                      {t("auth:reset.title")}
                    </h1>
                    <p className="text-sm text-text-secondary font-medium">
                      {t("auth:reset.subtitle")}
                    </p>
                  </div>

                  <form action={resetAction} autoComplete="off" className="space-y-6">
                    <div className="space-y-4">
                      <div className="space-y-2">
                        <TextField
                          id="reset-password-input"
                          label={t("auth:fields.password")}
                          name="password"
                          type={showPass ? "text" : "password"}
                          value={password}
                          onChange={(event: React.ChangeEvent<HTMLInputElement>) =>
                            onPass(event.target.value)
                          }
                          onKeyUp={(event: React.KeyboardEvent<HTMLInputElement>) =>
                            setCapsPass(event.getModifierState("CapsLock"))
                          }
                          onKeyDown={(event: React.KeyboardEvent<HTMLInputElement>) =>
                            setCapsPass(event.getModifierState("CapsLock"))
                          }
                          disabled={resetPending}
                          className="rounded-lg"
                          trailingIcon={
                            <button
                              id="reset-password-toggle"
                              type="button"
                              onClick={() => setShowPass(!showPass)}
                              className="p-1 hover:bg-black/(--opacity-subtle) dark:hover:bg-white/(--opacity-subtle) rounded-md transition-colors"
                              tabIndex={-1}
                            >
                              {showPass ? <VisibilityOff size={16} /> : <Visibility size={16} />}
                            </button>
                          }
                        />

                        {strength !== null && (
                          <div className="px-1 space-y-1">
                            <ProgressBar
                              value={STRENGTH_VALUES[strength]}
                              color={strength < 2 ? "error" : strength < 3 ? "warning" : "success"}
                              className="h-1.5"
                            />
                            <div className="flex justify-between items-center">
                              <p className="text-label-xs font-bold uppercase tracking-widest text-text-secondary opacity-strong">
                                {t("auth:register.passwordStrength")}
                              </p>
                              <p className="text-label-xs font-bold text-brand uppercase tracking-widest">
                                {
                                  [
                                    t("common:strength.very_weak"),
                                    t("common:strength.weak"),
                                    t("common:strength.medium"),
                                    t("common:strength.strong"),
                                    t("common:strength.very_strong"),
                                  ][strength]
                                }
                              </p>
                            </div>
                          </div>
                        )}
                      </div>

                      {!!feedback && (
                        <div className="flex gap-2 px-2 py-2 rounded-xs bg-brand/(--opacity-subtle) border border-brand/(--opacity-subtle)">
                          <ShieldCheck size={16} className="text-(--primary-main) shrink-0 mt-05" />
                          <p className="text-xs font-medium text-brand/(--opacity-hover) leading-relaxed">
                            {feedback}
                          </p>
                        </div>
                      )}

                      <div className="space-y-2">
                        <TextField
                          id="reset-confirm-input"
                          label={t("auth:fields.confirmPassword")}
                          name="confirm"
                          type={showConfirm ? "text" : "password"}
                          value={confirm}
                          onChange={(event: React.ChangeEvent<HTMLInputElement>) =>
                            setConfirm(event.target.value)
                          }
                          onKeyUp={(event: React.KeyboardEvent<HTMLInputElement>) =>
                            setCapsConfirm(event.getModifierState("CapsLock"))
                          }
                          onKeyDown={(event: React.KeyboardEvent<HTMLInputElement>) =>
                            setCapsConfirm(event.getModifierState("CapsLock"))
                          }
                          fullWidth
                          autoComplete="new-password"
                          ref={(input) => {
                            if (input) {
                              confirmRef.current = input as HTMLInputElement
                              // If you want to auto-focus on initial render of this field,
                              // you can uncomment the line below.
                              // setTimeout(() => input.focus(), 0);
                            }
                          }}
                          disabled={resetPending}
                          className="rounded-lg"
                          trailingIcon={
                            <button
                              id="reset-confirm-toggle"
                              type="button"
                              onClick={() => setShowConfirm(!showConfirm)}
                              className="p-1 hover:bg-black/(--opacity-subtle) dark:hover:bg-white/(--opacity-subtle) rounded-md transition-colors"
                              tabIndex={-1}
                            >
                              {showConfirm ? <VisibilityOff size={16} /> : <Visibility size={16} />}
                            </button>
                          }
                        />
                      </div>

                      {(capsPass || capsConfirm) && (
                        <div className="flex items-center gap-2 px-2 py-1.5 rounded-xs bg-warning-bg border border-warning-text/(--opacity-subtle) text-warning-text">
                          <AlertTriangle size={16} />
                          <p className="text-xs font-bold uppercase tracking-wider">
                            {t("auth:messages.capsLock")}
                          </p>
                        </div>
                      )}

                      {pwned && (
                        <Alert severity="warning" className="rounded-sm py-2">
                          {t("auth:reset.pwnedWarning")}
                        </Alert>
                      )}
                    </div>

                    {resetErrorMessage && (
                      <p className="text-sm font-bold text-error-text text-center animate-bounce">
                        {resetErrorMessage}
                      </p>
                    )}

                    <div className="space-y-4 pt-2">
                      <Button
                        id="reset-submit-btn"
                        type="submit"
                        variant="solid"
                        className="w-full h-14 rounded-lg text-base font-black shadow-premium hover:shadow-glass"
                        disabled={!canSubmit || resetPending}
                        loading={resetPending}
                        startIcon={<LockIcon size={20} />}
                      >
                        {t("auth:reset.saveButton")}
                      </Button>

                      <div className="pt-2 text-center">
                        <Link
                          to="/forgot-password"
                          className="inline-flex items-center gap-2 text-sm font-bold text-text-secondary hover:text-brand transition-colors group"
                        >
                          <ChevronLeft className="h-4 w-4 transition-transform group-hover:-translate-x-1" />
                          {t("auth:reset.linkHelp")}
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
