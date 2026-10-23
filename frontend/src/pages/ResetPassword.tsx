import {
  useState,
  useEffect,
  useCallback,
  useRef,
  useSyncExternalStore,
  useEffectEvent,
  type FormEvent,
} from "react"
import api from "@/api/client"
import { useLocation, useNavigate, useRouter, Link } from "@tanstack/react-router"
import { useTranslation } from "react-i18next"
import { m, AnimatePresence } from "framer-motion"
import "@/styles/tokens/auth.css"
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
import { ProgressBar } from "@/components/ui/ProgressBar"
import { AuthBackdrop } from "@/components/auth/AuthBackdrop"
import useMediaQuery from "@/hooks/useMediaQuery"
import { newPasswordSchema, type NewPasswordValues } from "@/features/auth/schemas"
import {
  bindLegacyResetTokenTarget,
  clearLegacyResetTokenForMigration,
  type CapturedLegacyResetToken,
} from "@/features/auth/legacyResetTokenState"
import { analyzePasswordStrength } from "@/utils/passwordStrength"
import {
  captureActiveTelemetryContext,
  type CapturedTelemetryContext,
} from "@/utils/telemetryContext"

const RESET_URL = "/password/reset"
const MISSING_RESET_TOKEN_ERROR = "missing-token-source"
const UNAVAILABLE_RESET_TOKEN_ERROR = "unavailable-at-submit"
const STRENGTH_VALUES = [10, 30, 55, 75, 100]
const LEGACY_RESET_TOKEN_TTL_MS = 45 * 60 * 1000
const MAX_LEGACY_RESET_TOKEN_ENTRIES = 64
const MAX_TIMER_DELAY_MS = 2_147_483_647

type LegacyResetTokenEntry = { token: string; expiresAt: number }
type PendingLegacyMigration = {
  sourceKey: string
  sourceIndex: number | null
  targetPath: string
  targetKey?: string
}
type LegacyMigrationOwner = {
  targetObserved: boolean
  unsubscribeHistory: (() => void) | null
}

const legacyResetTokens = new Map<string, LegacyResetTokenEntry>()
const legacyResetTokenSubscribers = new Set<() => void>()
let legacyResetPruneTimer: number | null = null
let nextLegacyMigrationId = 0

function subscribeLegacyResetTokens(subscriber: () => void) {
  legacyResetTokenSubscribers.add(subscriber)
  return () => {
    legacyResetTokenSubscribers.delete(subscriber)
  }
}

function notifyLegacyResetTokenSubscribers() {
  for (const subscriber of legacyResetTokenSubscribers) subscriber()
}

function getEmptyLegacyResetTokenSnapshot() {
  return null
}

function getHistoryEntryKey(state: { key?: unknown; __TSR_key?: unknown }) {
  if (typeof state.__TSR_key === "string" && state.__TSR_key) return state.__TSR_key
  return typeof state.key === "string" && state.key ? state.key : ""
}

function getHistoryEntryIndex(state: { __TSR_index?: unknown }) {
  return typeof state.__TSR_index === "number" ? state.__TSR_index : null
}

function pruneLegacyResetTokens(now = Date.now()) {
  let changed = false
  for (const [key, entry] of legacyResetTokens) {
    if (entry.expiresAt <= now) {
      legacyResetTokens.delete(key)
      changed = true
    }
  }
  while (legacyResetTokens.size > MAX_LEGACY_RESET_TOKEN_ENTRIES) {
    const oldestKey = legacyResetTokens.keys().next().value!
    legacyResetTokens.delete(oldestKey)
    changed = true
  }
  return changed
}

function scheduleLegacyResetTokenPruning() {
  if (legacyResetPruneTimer !== null) {
    window.clearTimeout(legacyResetPruneTimer)
    legacyResetPruneTimer = null
  }
  const nextExpiry = Array.from(legacyResetTokens.values()).reduce(
    (soonest, entry) => Math.min(soonest, entry.expiresAt),
    Number.POSITIVE_INFINITY
  )
  if (!Number.isFinite(nextExpiry)) return
  const delay = Math.max(0, Math.min(nextExpiry - Date.now(), MAX_TIMER_DELAY_MS))
  legacyResetPruneTimer = window.setTimeout(() => {
    legacyResetPruneTimer = null
    if (pruneLegacyResetTokens()) notifyLegacyResetTokenSubscribers()
    scheduleLegacyResetTokenPruning()
  }, delay)
}

function rememberLegacyResetToken(key: string, token: string, expiresAt: number) {
  const now = Date.now()
  pruneLegacyResetTokens(now)
  legacyResetTokens.delete(key)
  legacyResetTokens.set(key, { token, expiresAt })
  pruneLegacyResetTokens(now)
  notifyLegacyResetTokenSubscribers()
  scheduleLegacyResetTokenPruning()
}

function forgetLegacyResetToken(key: string) {
  if (typeof window !== "undefined" && key && legacyResetTokens.delete(key)) {
    notifyLegacyResetTokenSubscribers()
    scheduleLegacyResetTokenPruning()
  }
}

function tokenFromHash(hash: string) {
  return new URLSearchParams(hash).get("token") ?? ""
}

function hashWithoutToken(hash: string) {
  const parameters = new URLSearchParams(hash)
  parameters.delete("token")
  return parameters.toString()
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

async function isPwnedPassword(pwd: string, signal: AbortSignal) {
  const hash = await sha1Hex(pwd)
  signal.throwIfAborted()
  const prefix = hash.slice(0, HASH_PREFIX_LEN)
  const suffix = hash.slice(HASH_PREFIX_LEN)
  const resp = await fetch(`${PWNED_API_URL}${prefix}`, { signal })
  if (!resp.ok) return false
  const text = await resp.text()
  return text.split("\n").some((line) => line.split(":")[0] === suffix)
}

export default function ResetPassword() {
  // Every key names its namespace explicitly ("auth:…", "common:…").
  const { t, i18n } = useTranslation()
  const passwordStrengthLanguage = i18n.resolvedLanguage ?? i18n.language
  // Wave 186 SW3 — useReducedMotion via project's useMediaQuery (jsdom-safe
  // per W184 SW6). Drops AuthBackdrop blur on mobile/reduced-motion.
  const prefersReducedMotion = useMediaQuery("(prefers-reduced-motion: reduce)")
  const navigate = useNavigate()
  const router = useRouter()
  const { pathname, search: searchParameters, state: locationState, hash } = useLocation()
  const [, pathParams, matchedRoute] = router.getMatchedRoutes(pathname)
  const routeToken =
    matchedRoute?.fullPath === "/reset-password/$token" && !pathParams["**"] ? pathParams.token : ""
  const queryToken = (searchParameters as { token?: string }).token || ""
  const routeStateToken =
    (locationState as { resetPasswordToken?: string }).resetPasswordToken || ""
  const fragmentToken = tokenFromHash(hash)
  const historyEntryKey = getHistoryEntryKey(locationState)
  const historyEntryIndex = getHistoryEntryIndex(locationState)
  const migrationMarker =
    (locationState as { __resetPasswordMigration?: string }).__resetPasswordMigration || ""
  const [capturedLegacyToken, setCapturedLegacyToken] = useState<CapturedLegacyResetToken | null>(
    null
  )
  const pendingLegacyMigrationRef = useRef<PendingLegacyMigration | null>(null)
  const legacyMigrationOwnerRef = useRef<LegacyMigrationOwner | null>(null)
  const componentMountedRef = useRef(false)
  const stopLegacyMigration = useCallback((owner: LegacyMigrationOwner) => {
    const unsubscribe = owner.unsubscribeHistory
    owner.unsubscribeHistory = null
    unsubscribe?.()
  }, [])
  const invalidateLegacyMigration = useCallback(
    (owner: LegacyMigrationOwner) => {
      stopLegacyMigration(owner)
      if (legacyMigrationOwnerRef.current === owner) {
        legacyMigrationOwnerRef.current = null
        pendingLegacyMigrationRef.current = null
      }
    },
    [stopLegacyMigration]
  )

  useEffect(() => {
    componentMountedRef.current = true
    return () => {
      componentMountedRef.current = false
      const owner = legacyMigrationOwnerRef.current
      if (!owner) return
      // StrictMode replays passive effects synchronously. Defer invalidation one
      // microtask so a replayed mount can retain the still-owned migration.
      queueMicrotask(() => {
        if (!componentMountedRef.current) invalidateLegacyMigration(owner)
      })
    }
  }, [invalidateLegacyMigration])
  const getCachedLegacyResetTokenSnapshot = useCallback(
    () => (historyEntryKey ? (legacyResetTokens.get(historyEntryKey) ?? null) : null),
    [historyEntryKey]
  )
  const cachedLegacyResetToken = useSyncExternalStore(
    subscribeLegacyResetTokens,
    getCachedLegacyResetTokenSnapshot,
    getEmptyLegacyResetTokenSnapshot
  )
  const getCapturedLegacyTokenValue = (now?: number) => {
    if (!capturedLegacyToken || (now !== undefined && capturedLegacyToken.expiresAt <= now)) {
      return ""
    }
    if (capturedLegacyToken.key === historyEntryKey) return capturedLegacyToken.token
    if (
      capturedLegacyToken.migrating &&
      capturedLegacyToken.targetKey === historyEntryKey &&
      migrationMarker === capturedLegacyToken.migrationId &&
      capturedLegacyToken.sourceIndex !== null &&
      capturedLegacyToken.sourceIndex === historyEntryIndex &&
      capturedLegacyToken.targetPath === pathname &&
      !queryToken &&
      !routeStateToken
    ) {
      return capturedLegacyToken.token
    }
    return ""
  }
  const resolveCurrentResetToken = (now?: number) => {
    if (fragmentToken) return fragmentToken

    const legacySourceToken = routeToken || queryToken || routeStateToken
    if (legacySourceToken) {
      const captured = capturedLegacyToken
      if (!captured || captured.token !== legacySourceToken) return ""
      return getCapturedLegacyTokenValue(now)
    }

    const capturedToken = getCapturedLegacyTokenValue(now)
    if (capturedToken) return capturedToken
    if (!cachedLegacyResetToken || (now !== undefined && cachedLegacyResetToken.expiresAt <= now)) {
      return ""
    }
    return cachedLegacyResetToken.token
  }
  const token = resolveCurrentResetToken()

  // Legacy tokens stay in memory only and expire from component state and the
  // bounded history-entry cache 45 minutes after first capture.
  useEffect(() => {
    if (!capturedLegacyToken) return
    const expire = () =>
      setCapturedLegacyToken((current) =>
        clearLegacyResetTokenForMigration(current, capturedLegacyToken.migrationId)
      )
    const remaining = capturedLegacyToken.expiresAt - Date.now()
    if (remaining <= 0) {
      expire()
      return
    }
    const timeout = window.setTimeout(expire, remaining)
    return () => window.clearTimeout(timeout)
  }, [capturedLegacyToken])

  // Replace legacy bearer URLs with a clean entry. Completion can retain a token
  // only for the exact REPLACE history key observed for this migration.
  useEffect(() => {
    const legacyToken = routeToken || queryToken || routeStateToken
    if (!legacyToken || !historyEntryKey) {
      const currentOwner = legacyMigrationOwnerRef.current
      if (currentOwner && !currentOwner.targetObserved) {
        invalidateLegacyMigration(currentOwner)
      }
      return
    }
    if (pendingLegacyMigrationRef.current?.sourceKey === historyEntryKey) return
    if (legacyMigrationOwnerRef.current) {
      invalidateLegacyMigration(legacyMigrationOwnerRef.current)
    }

    const migrationId = `reset-migration-${++nextLegacyMigrationId}`
    const expiresAt = Date.now() + LEGACY_RESET_TOKEN_TTL_MS
    const targetPath = routeToken ? "/reset-password" : pathname
    const pending: PendingLegacyMigration = {
      sourceKey: historyEntryKey,
      sourceIndex: historyEntryIndex,
      targetPath,
    }
    pendingLegacyMigrationRef.current = pending
    const owner: LegacyMigrationOwner = {
      targetObserved: false,
      unsubscribeHistory: null,
    }
    legacyMigrationOwnerRef.current = owner
    const ownsMigration = () =>
      componentMountedRef.current && legacyMigrationOwnerRef.current === owner
    if (!fragmentToken) {
      setCapturedLegacyToken({
        key: historyEntryKey,
        token: legacyToken,
        expiresAt,
        migrating: true,
        migrationId,
        sourceKey: historyEntryKey,
        sourceIndex: historyEntryIndex,
        targetPath,
      })
    }

    owner.unsubscribeHistory = router.history.subscribe(({ action, location }) => {
      if (!ownsMigration()) return
      if (action.type !== "REPLACE" || location.pathname !== targetPath) return
      const state = location.state as { __resetPasswordMigration?: string }
      if (state.__resetPasswordMigration !== migrationId) return
      if (historyEntryIndex !== null && location.state.__TSR_index !== historyEntryIndex) return
      if (new URLSearchParams(location.search).has("token")) return
      const targetKey = getHistoryEntryKey(location.state)
      if (!targetKey) return
      const current = pendingLegacyMigrationRef.current!
      owner.targetObserved = true
      current.targetKey = targetKey
      setCapturedLegacyToken((previous) =>
        bindLegacyResetTokenTarget(previous, migrationId, targetKey)
      )
    })

    void navigate({
      to: routeToken ? "/reset-password" : ".",
      search: (previous: Record<string, unknown>) => {
        const next = { ...previous }
        delete next.token
        return next
      },
      hash,
      state: (previous) => {
        const next = { ...previous } as Record<string, unknown>
        delete next.resetPasswordToken
        next.__resetPasswordMigration = migrationId
        return next
      },
      replace: true,
      viewTransition: false,
    })
      .then(() => {
        stopLegacyMigration(owner)
        if (!ownsMigration()) return
        const currentPending = pendingLegacyMigrationRef.current!
        const destination = router.state.location
        const destinationKey = getHistoryEntryKey(destination.state)
        const destinationState = destination.state as {
          __resetPasswordMigration?: string
          resetPasswordToken?: string
        }
        const destinationSearch = destination.search as { token?: string }
        const isExactDestination =
          !!currentPending.targetKey &&
          destinationKey === currentPending.targetKey &&
          getHistoryEntryKey(router.history.location.state) === currentPending.targetKey &&
          destinationState.__resetPasswordMigration === migrationId &&
          destination.pathname === targetPath &&
          !destinationSearch.token &&
          !destinationState.resetPasswordToken &&
          (historyEntryIndex === null ||
            router.history.location.state.__TSR_index === historyEntryIndex)

        if (!fragmentToken && isExactDestination && expiresAt > Date.now()) {
          rememberLegacyResetToken(destinationKey, legacyToken, expiresAt)
          forgetLegacyResetToken(historyEntryKey)
          setCapturedLegacyToken({
            key: destinationKey,
            token: legacyToken,
            expiresAt,
            migrating: false,
            migrationId,
            sourceKey: historyEntryKey,
            sourceIndex: historyEntryIndex,
            targetPath,
          })
        } else {
          setCapturedLegacyToken((current) =>
            clearLegacyResetTokenForMigration(current, migrationId)
          )
        }
        pendingLegacyMigrationRef.current = null
        legacyMigrationOwnerRef.current = null
      })
      .catch(() => {
        stopLegacyMigration(owner)
        if (!ownsMigration()) return
        // A router promise can reject after committing its REPLACE. Keep the
        // source-bound capture and migration identity only until their original
        // deadline; submit-time resolution separately gates raw legacy fields.
        legacyMigrationOwnerRef.current = null
      })

    return () => {
      if (owner.targetObserved) {
        stopLegacyMigration(owner)
        return
      }
      // An in-flight navigation must not outlive a real unmount. The mount
      // cleanup handles invalidation; this deferred check also survives StrictMode
      // effect replay without cancelling the replayed owner.
      queueMicrotask(() => {
        if (!componentMountedRef.current) invalidateLegacyMigration(owner)
      })
    }
  }, [
    fragmentToken,
    hash,
    historyEntryIndex,
    historyEntryKey,
    invalidateLegacyMigration,
    migrationMarker,
    navigate,
    pathname,
    queryToken,
    routeStateToken,
    routeToken,
    router,
    stopLegacyMigration,
  ])

  const [capsPass, setCapsPass] = useState(false)
  const [capsConfirm, setCapsConfirm] = useState(false)
  const [showPass, setShowPass] = useState(false)
  const [showConfirm, setShowConfirm] = useState(false)
  const [strength, setStrength] = useState<number | null>(null)
  const [feedback, setFeedback] = useState<string>("")
  const [pwned, setPwned] = useState(false)
  const [isSuccess, setIsSuccess] = useState(false)
  const [tokenSourceReady, setTokenSourceReady] = useState(false)
  const focusSuccessHeading = useCallback((heading: HTMLHeadingElement | null) => {
    heading?.focus()
  }, [])

  const {
    register,
    handleSubmit,
    watch,
    setError,
    clearErrors,
    formState: { errors, isSubmitting },
  } = useForm<NewPasswordValues>({
    resolver: valibotResolver(newPasswordSchema),
    defaultValues: {
      password: "",
      confirmPassword: "",
    },
    mode: "onBlur",
  })

  const { password, confirmPassword } = watch()

  // Password analysis effect
  useEffect(() => {
    if (!password) {
      setStrength(null)
      setPwned(false)
      setFeedback("")
      return
    }
    let active = true
    const controller = new AbortController()
    setPwned(false)

    const checkPassword = async () => {
      try {
        const complexityResult = await analyzePasswordStrength(password, passwordStrengthLanguage)
        if (!active) return
        setStrength(complexityResult.score)
        const tips =
          (complexityResult.feedback?.warning || "") +
          (complexityResult.feedback?.suggestions?.length
            ? " · " + complexityResult.feedback.suggestions.join(" · ")
            : "")
        setFeedback(tips)
      } catch {
        if (!active) return
        setStrength(null)
        setFeedback("")
      }

      try {
        const bad = await isPwnedPassword(password, controller.signal)
        if (active) setPwned(bad)
      } catch {
        // `pwned` was reset when this check started; an aborted or failed lookup keeps it clear.
      }
    }

    // Debounce slightly to avoid heavy computation on every keystroke
    const handler = setTimeout(() => {
      void checkPassword()
    }, 300)

    return () => {
      active = false
      clearTimeout(handler)
      controller.abort()
    }
  }, [password, passwordStrengthLanguage])

  const onSubmit = async (data: NewPasswordValues, telemetryContext: CapturedTelemetryContext) => {
    const submittedToken = resolveCurrentResetToken(Date.now())
    if (!submittedToken) {
      setError("root", {
        type: token ? UNAVAILABLE_RESET_TOKEN_ERROR : MISSING_RESET_TOKEN_ERROR,
        message: t("auth:reset.invalidLink"),
      })
      return
    }

    try {
      await telemetryContext.run(() =>
        api.post(RESET_URL, { token: submittedToken, password: data.password })
      )
      setIsSuccess(true)
      forgetLegacyResetToken(historyEntryKey)
      setCapturedLegacyToken(null)
      if (fragmentToken || routeToken || queryToken || routeStateToken) {
        void navigate({
          to: routeToken ? "/reset-password" : ".",
          search: (previous: Record<string, unknown>) => {
            const next = { ...previous }
            delete next.token
            return next
          },
          hash: hashWithoutToken(hash),
          state: (previous) => {
            const next = { ...previous } as Record<string, unknown>
            delete next.resetPasswordToken
            delete next.__resetPasswordMigration
            return next
          },
          replace: true,
          viewTransition: false,
        })
      }
    } catch (error: unknown) {
      const detail = (error as { response?: { data?: { detail?: unknown } } } | null | undefined)
        ?.response?.data?.detail
      setError("root", {
        type: "server",
        message: typeof detail === "string" && detail ? detail : t("auth:reset.errorGeneric"),
      })
    }
  }

  const handleTelemetrySubmit = (event: FormEvent<HTMLFormElement>) => {
    const telemetryContext = captureActiveTelemetryContext()
    return handleSubmit((data) => onSubmit(data, telemetryContext))(event)
  }

  // Resolve browser-only fragment tokens after hydration before showing an
  // invalid-link error, keeping the server and first client render identical.
  useEffect(() => {
    setTokenSourceReady(true)
  }, [])

  const reportMissingResetTokenError = useEffectEvent(() => {
    if (!tokenSourceReady || token || isSuccess) return
    if (!errors.root || errors.root.type === MISSING_RESET_TOKEN_ERROR) {
      setError("root", {
        type: MISSING_RESET_TOKEN_ERROR,
        message: t("auth:reset.invalidLink"),
      })
    }
  })

  useEffect(() => {
    reportMissingResetTokenError()
  }, [isSuccess, t, token, tokenSourceReady])

  const clearMissingResetTokenErrorOnTokenChange = useEffectEvent(() => {
    if (!tokenSourceReady || isSuccess || !token) return
    if (errors.root?.type === MISSING_RESET_TOKEN_ERROR) clearErrors("root")
  })

  useEffect(() => {
    clearMissingResetTokenErrorOnTokenChange()
  }, [isSuccess, token, tokenSourceReady])

  return (
    <div className="auth-theme min-h-screen bg-page text-text-primary flex items-center justify-center p-(--fluid-px) relative overflow-hidden">
      {/* Wave 186 SW3 — Replaces inline glow blocks (~20 lines of
          duplicated decorative code) with AuthBackdrop component.
          Teal/cyan ambient orbs scoped under .auth-theme. */}
      <AuthBackdrop prefersReducedMotion={prefersReducedMotion} />

      <m.div
        initial={!prefersReducedMotion && { opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="w-full max-w-(--layout-max-modal) z-modal"
      >
        <SectionCard className="p-(--fluid-card-p) border-glass-border shadow-glass backdrop-blur-2xl rounded-4xl">
          <div className="space-y-8">
            <AnimatePresence mode="wait">
              {isSuccess ? (
                <m.div
                  key="success"
                  initial={!prefersReducedMotion && { opacity: 0, scale: 0.95 }}
                  animate={{ opacity: 1, scale: 1 }}
                  className="space-y-6 pt-4 text-center"
                >
                  <div className="flex justify-center">
                    <div className="h-20 w-20 rounded-lg bg-success-bg flex items-center justify-center text-success-text">
                      <CheckCircle2 size={40} />
                    </div>
                  </div>
                  <div className="space-y-2">
                    <h2
                      ref={focusSuccessHeading}
                      tabIndex={-1}
                      className="text-2xl font-black tracking-tight text-text-primary"
                    >
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
                  initial={!prefersReducedMotion && { opacity: 0 }}
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

                  <form
                    method="post"
                    onSubmit={handleTelemetrySubmit}
                    autoComplete="on"
                    className="space-y-6"
                  >
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
                          autoComplete="new-password"
                          disabled={isSubmitting}
                          className="rounded-lg"
                          error={!!errors.password}
                          helperText={
                            errors.password?.message ? t(errors.password.message) : undefined
                          }
                          trailingIcon={
                            <button
                              id="reset-password-toggle"
                              type="button"
                              onClick={() => setShowPass(!showPass)}
                              className="inline-flex min-h-11 min-w-11 items-center justify-center rounded-md transition-colors hover:bg-black/[calc(var(--opacity-subtle)*100%)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand dark:hover:bg-white/[calc(var(--opacity-subtle)*100%)]"
                              aria-label={t(
                                showPass
                                  ? "auth:actions.hideCredential"
                                  : "auth:actions.showPassword"
                              )}
                              aria-pressed={showPass}
                            >
                              {showPass ? (
                                <VisibilityOff size={16} aria-hidden="true" />
                              ) : (
                                <Visibility size={16} aria-hidden="true" />
                              )}
                            </button>
                          }
                        />

                        {strength !== null && (
                          <div className="px-1 space-y-1">
                            <ProgressBar
                              value={STRENGTH_VALUES[strength]}
                              barClassName={
                                strength < 2
                                  ? "bg-error-text"
                                  : strength < 3
                                    ? "bg-warning-text"
                                    : "bg-success-text"
                              }
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
                        <div className="flex gap-2 px-2 py-2 rounded-xs bg-brand/[calc(var(--opacity-subtle)*100%)] border border-brand/[calc(var(--opacity-subtle)*100%)]">
                          <ShieldCheck
                            size={16}
                            className="text-(--primary-main) shrink-0 mt-0.5"
                          />
                          <p className="text-xs font-medium text-brand/[calc(var(--opacity-hover)*100%)] leading-relaxed">
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
                          helperText={
                            errors.confirmPassword?.message
                              ? t(errors.confirmPassword.message)
                              : undefined
                          }
                          trailingIcon={
                            <button
                              id="reset-confirm-toggle"
                              type="button"
                              onClick={() => setShowConfirm(!showConfirm)}
                              className="inline-flex min-h-11 min-w-11 items-center justify-center rounded-md transition-colors hover:bg-black/[calc(var(--opacity-subtle)*100%)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand dark:hover:bg-white/[calc(var(--opacity-subtle)*100%)]"
                              aria-label={t(
                                showConfirm
                                  ? "auth:actions.hideCredential"
                                  : "auth:actions.showPassword"
                              )}
                              aria-pressed={showConfirm}
                            >
                              {showConfirm ? (
                                <VisibilityOff size={16} aria-hidden="true" />
                              ) : (
                                <Visibility size={16} aria-hidden="true" />
                              )}
                            </button>
                          }
                        />
                      </div>

                      {(capsPass || capsConfirm) && (
                        <div className="flex items-center gap-2 px-2 py-1.5 rounded-xs bg-warning-bg border border-warning-text/[calc(var(--opacity-subtle)*100%)] text-warning-text">
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
                      <p role="alert" className="text-center text-sm font-bold text-error-text">
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
