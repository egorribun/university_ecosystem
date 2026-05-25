import { useState, useEffect } from "react"
import api from "@/api/client"
import { useParams, useSearch, Link } from "@tanstack/react-router"
import { useTranslation } from "react-i18next"
import { m, AnimatePresence } from "framer-motion"
import {
  Eye as Visibility,
  EyeOff as VisibilityOff,
  ChevronLeft,
  Lock as LockIcon,
  CheckCircle2,
  ShieldCheck,
  AlertTriangle,
} from "lucide-react"
import { useForm } from "react-hook-form"
import { valibotResolver } from "@hookform/resolvers/valibot"

import { Button, TextField, SectionCard, Alert } from "@/components/settings"
import { ProgressBar } from "@/components/ui"
import AuthBackdrop from "@/components/auth/AuthBackdrop"
import useMediaQuery from "@/hooks/useMediaQuery"
import { newPasswordSchema, type NewPasswordValues } from "@/features/auth/schemas"

const RESET_URL = "/password/reset"
const STRENGTH_VALUES = [10, 30, 55, 75, 100]

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
  const { t } = useTranslation(["auth", "common"])
  // Wave 186 SW3 — useReducedMotion via project's useMediaQuery (jsdom-safe
  // per W184 SW6). Drops AuthBackdrop blur on mobile/reduced-motion.
  const prefersReducedMotion = useMediaQuery("(prefers-reduced-motion: reduce)")
  const routeParameters = useParams({ strict: false })
  const searchParameters = useSearch({ strict: false })
  const token =
    (routeParameters as { token?: string }).token ||
    (searchParameters as { token?: string }).token ||
    ""

  const [capsPass, setCapsPass] = useState(false)
  const [capsConfirm, setCapsConfirm] = useState(false)
  const [showPass, setShowPass] = useState(false)
  const [showConfirm, setShowConfirm] = useState(false)
  const [strength, setStrength] = useState<number | null>(null)
  const [feedback, setFeedback] = useState<string>("")
  const [pwned, setPwned] = useState(false)
  const [isSuccess, setIsSuccess] = useState(false)

  const {
    register,
    handleSubmit,
    watch,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<NewPasswordValues>({
    resolver: valibotResolver(newPasswordSchema),
    defaultValues: {
      password: "",
      confirmPassword: "",
    },
    mode: "onBlur",
  })

  const password = watch("password")
  const confirmPassword = watch("confirmPassword")

  // Password analysis effect
  useEffect(() => {
    if (!password) {
      setStrength(null)
      setPwned(false)
      setFeedback("")
      return
    }

    const checkPassword = async () => {
      try {
        const { zxcvbn, zxcvbnOptions } = await import("@zxcvbn-ts/core")
        const zxcvbnCommon = await import("@zxcvbn-ts/language-common")
        zxcvbnOptions.setOptions(zxcvbnCommon)
        const complexityResult = zxcvbn(password)
        setStrength(complexityResult.score)
        const tips =
          (complexityResult.feedback?.warning || "") +
          (complexityResult.feedback?.suggestions?.length
            ? " · " + complexityResult.feedback.suggestions.join(" · ")
            : "")
        setFeedback(tips)
      } catch {
        // ignore
      }

      try {
        const bad = await isPwnedPassword(password)
        setPwned(bad)
      } catch {
        // ignore
      }
    }

    // Debounce slightly to avoid heavy computation on every keystroke
    const handler = setTimeout(() => {
      void checkPassword()
    }, 300)

    return () => clearTimeout(handler)
  }, [password])

  const onSubmit = async (data: NewPasswordValues) => {
    if (!token) {
      setError("root", { message: t("auth:reset.invalidLink") })
      return
    }

    try {
      await api.post(RESET_URL, { token, password: data.password })
      setIsSuccess(true)
    } catch (error: unknown) {
      let errorMessage = t("auth:reset.errorGeneric")
      if (typeof error === "object" && error !== null && "response" in error) {
        const axiosError = error as { response?: { data?: { detail?: string } } }
        errorMessage = axiosError.response?.data?.detail || errorMessage
      }
      setError("root", { message: errorMessage })
    }
  }

  // Initial token check
  useEffect(() => {
    if (!token) {
      setError("root", { message: t("auth:reset.invalidLink") })
    }
  }, [token, setError, t])

  return (
    <div className="auth-theme min-h-screen bg-page text-text-primary flex items-center justify-center p-(--fluid-px) relative overflow-hidden">
      {/* Wave 186 SW3 — Replaces inline glow blocks (~20 lines of
          duplicated decorative code) with AuthBackdrop component.
          Teal/cyan ambient orbs scoped under .auth-theme. */}
      <AuthBackdrop prefersReducedMotion={prefersReducedMotion} />

      <m.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="w-full max-w-(--layout-max-modal) z-modal"
      >
        <SectionCard className="p-(--fluid-card-p) border-glass-border shadow-glass backdrop-blur-2xl rounded-4xl">
          <div className="space-y-8">
            <AnimatePresence mode="wait">
              {isSuccess ? (
                <m.div
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
                </m.div>
              ) : (
                <m.div
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

                  <form onSubmit={handleSubmit(onSubmit)} autoComplete="off" className="space-y-6">
                    <div className="space-y-4">
                      <div className="space-y-2">
                        <TextField
                          id="reset-password-input"
                          label={t("auth:fields.password")}
                          {...register("password")}
                          value={password}
                          type={showPass ? "text" : "password"}
                          onKeyUp={(event: React.KeyboardEvent<HTMLInputElement>) =>
                            setCapsPass(event.getModifierState("CapsLock"))
                          }
                          onKeyDown={(event: React.KeyboardEvent<HTMLInputElement>) =>
                            setCapsPass(event.getModifierState("CapsLock"))
                          }
                          disabled={isSubmitting}
                          className="rounded-lg"
                          error={!!errors.password}
                          helperText={errors.password?.message}
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
                          <ShieldCheck
                            size={16}
                            className="text-(--primary-main) shrink-0 mt-0.5"
                          />
                          <p className="text-xs font-medium text-brand/(--opacity-hover) leading-relaxed">
                            {feedback}
                          </p>
                        </div>
                      )}

                      <div className="space-y-2">
                        <TextField
                          id="reset-confirm-input"
                          label={t("auth:fields.confirmPassword")}
                          {...register("confirmPassword")}
                          value={confirmPassword}
                          type={showConfirm ? "text" : "password"}
                          onKeyUp={(event: React.KeyboardEvent<HTMLInputElement>) =>
                            setCapsConfirm(event.getModifierState("CapsLock"))
                          }
                          onKeyDown={(event: React.KeyboardEvent<HTMLInputElement>) =>
                            setCapsConfirm(event.getModifierState("CapsLock"))
                          }
                          fullWidth
                          autoComplete="new-password"
                          disabled={isSubmitting}
                          className="rounded-lg"
                          error={!!errors.confirmPassword}
                          helperText={errors.confirmPassword?.message}
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

                    {errors.root?.message && (
                      <p className="text-sm font-bold text-error-text text-center animate-bounce">
                        {errors.root.message}
                      </p>
                    )}

                    <div className="space-y-4 pt-2">
                      <Button
                        id="reset-submit-btn"
                        type="submit"
                        variant="solid"
                        className="w-full h-14 rounded-lg text-base font-black shadow-premium hover:shadow-glass"
                        disabled={isSubmitting}
                        loading={isSubmitting}
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
                </m.div>
              )}
            </AnimatePresence>
          </div>
        </SectionCard>
      </m.div>
    </div>
  )
}
