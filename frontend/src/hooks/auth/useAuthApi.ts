import { useCallback } from "react"
import { useTranslation } from "react-i18next"
import { isAxiosError } from "axios"
import type { TFunction } from "i18next"
import { useQueryClient } from "@tanstack/react-query"
import api, { API_UNAUTHORIZED_EVENT, type ApiRequestConfig } from "@/api/client"
import { SPOTIFY_REAUTH_EVENT } from "@/hooks/useNowPlaying"
import type { PendingMfaResponse, MfaVerifyPayload } from "@/types/Mfa"
import type { User } from "@/types/User"
import {
  type PendingMfaState,
  type SubmitMfaChallengePayload,
  type UserState,
  type SetUserArg,
  ChallengeLockedError,
} from "@/types/Auth"
import { fetchCurrentUser } from "./useProfileSync"
import i18n from "@/i18n/config"
import {
  recoverPushConsentFromBrowser,
  hasPushConsent,
  softSyncPushSubscription,
  setPushConsent,
} from "@/push/subscribe"
import type { WebAuthnAuthenticationOptionsOut } from "@/types/Auth"
import { logWarning, logError } from "@/app/logger"
import { incrementSessionEpoch } from "@/api/interceptors/etagCache"

type TokenWithProfileResponse = {
  user?: User
  session?: { signing_key: string } | null
}

const extractSigningKey = (value: TokenWithProfileResponse | undefined | null): string | null => {
  if (!value) return null
  const key = value.session?.signing_key
  return typeof key === "string" && key.length > 0 ? key : null
}

const isTokenWithProfileResponse = (
  value: unknown
): value is TokenWithProfileResponse & { user: User } => {
  if (!value || typeof value !== "object") {
    return false
  }
  const candidate = value as Record<string, unknown>
  if (!candidate.user || typeof candidate.user !== "object") {
    return false
  }
  return true
}

const formatLockoutDuration = (
  seconds: number | null | undefined,
  t: TFunction<"auth">
): string | null => {
  if (typeof seconds !== "number" || !Number.isFinite(seconds) || seconds <= 0) {
    return null
  }

  if (seconds < 60) {
    const value = Math.max(1, Math.ceil(seconds))
    return t("login.duration.seconds", { count: value })
  }

  if (seconds < 3600) {
    const value = Math.max(1, Math.ceil(seconds / 60))
    return t("login.duration.minutes", { count: value })
  }

  const value = Math.max(1, Math.ceil(seconds / 3600))
  return t("login.duration.hours", { count: value })
}

export const useAuthApi = (
  user: UserState,
  setUser: (value: SetUserArg) => void,
  updatePendingMfa: (value: PendingMfaState | null, options?: { broadcast?: boolean }) => void,
  handleUnauthorized: (options?: { broadcast?: boolean; persist?: boolean }) => void,
  updateSessionSigningKey: (value: string | null) => void,
  authOperation: boolean,
  setAuthOperation: (value: boolean) => void,
  resetEtagCache: () => void
) => {
  const { t } = useTranslation("auth")
  const queryClient = useQueryClient()

  const prefetchDashboardData = useCallback(
    async (profileUser: User) => {
      try {
        const activeLanguage = i18n.resolvedLanguage ?? i18n.language ?? "ru"
        const language = activeLanguage === "en" ? "en" : "ru"

        const [
          { prefetchDashboardStories },
          { prefetchDashboardNews },
          { prefetchDashboardEvents },
          { prefetchEventsListQuery, EVENTS_PAGE_SIZE },
        ] = await Promise.all([
          import("@/hooks/useDashboardStories"),
          import("@/hooks/useDashboardNews"),
          import("@/hooks/useDashboardEvents"),
          import("@/api/hooks/events"),
        ])

        void prefetchDashboardStories(queryClient)
        void prefetchDashboardNews(queryClient, language)
        void prefetchDashboardEvents(queryClient)

        if (profileUser.group_id) {
          void prefetchEventsListQuery(queryClient, {
            language,
            is_active: true,
            limit: EVENTS_PAGE_SIZE,
          })
        }
      } catch (error) {
        if (import.meta.env.DEV) {
          logWarning("Failed to prefetch dashboard data", { error })
        }
      }
    },
    [queryClient]
  )

  const login = useCallback(
    async (
      email: string,
      password: string,
      trustDevice = false
    ): Promise<PendingMfaState | null> => {
      if (authOperation) return null
      setAuthOperation(true)
      try {
        const params = new URLSearchParams()
        params.append("username", email)
        params.append("password", password)
        if (trustDevice) {
          params.append("trust_device", "true")
        }

        const response = await api.post<TokenWithProfileResponse | PendingMfaResponse>(
          "/auth/login",
          params,
          {
            headers: { "Content-Type": "application/x-www-form-urlencoded" },
            skipRateLimitQueue: true,
          } as ApiRequestConfig
        )

        if (response.status === 202) {
          const mfaResponse = response.data as PendingMfaResponse
          const pendingState: PendingMfaState = {
            ...mfaResponse,
            reason: "login",
          }
          updatePendingMfa(pendingState)
          return pendingState
        }

        const data = response.data as TokenWithProfileResponse
        if (isTokenWithProfileResponse(data)) {
          updateSessionSigningKey(extractSigningKey(data))
          // RED-02 (audit Wave 11): increment epoch AFTER new signing key is registered.
          // Any HMAC computations that started under the previous session see the epoch
          // change and discard their results, preventing cross-session data leakage.
          incrementSessionEpoch()
          setUser(data.user)
          updatePendingMfa(null)
          if (data.user.spotify_connected) {
            window.dispatchEvent(new Event(SPOTIFY_REAUTH_EVENT))
          }

          // Recover push consent if browser still has subscription after storage was cleared
          recoverPushConsentFromBrowser()
            .then((recovered) => {
              if (recovered || hasPushConsent()) {
                softSyncPushSubscription().catch(() => {})
              }
            })
            .catch(() => {})

          void prefetchDashboardData(data.user)
          return null
        }

        throw new Error("Invalid response from server")
      } catch (error) {
        if (isAxiosError(error) && error.response?.status === 423) {
          const retryAfter = error.response.headers["retry-after"]
          const seconds = retryAfter ? parseInt(retryAfter, 10) : null
          const duration = formatLockoutDuration(seconds, t)
          if (duration) {
            throw new Error(`${t("login.locked")} ${t("login.lockedRetry", { duration })}`)
          }
          throw new Error(t("login.locked"))
        }
        throw error
      } finally {
        setAuthOperation(false)
      }
    },
    [
      authOperation,
      prefetchDashboardData,
      setAuthOperation,
      setUser,
      t,
      updatePendingMfa,
      updateSessionSigningKey,
    ]
  )

  const logout = useCallback(async () => {
    try {
      if (user) {
        // Don't fully unsubscribe - just clear local consent
        // This allows push subscription to be recovered on next login
        // The browser subscription remains, server association is cleared
        if (hasPushConsent()) {
          setPushConsent(false)
        }
        await api.post("/auth/logout")
      }
    } catch (error) {
      logError("Logout failed", { error })
    } finally {
      handleUnauthorized()
    }
  }, [handleUnauthorized, user])

  const submitMfaChallenge = useCallback(
    async ({
      method = "totp",
      code,
      webauthnResponse,
      challengeToken,
      trustDevice,
    }: SubmitMfaChallengePayload) => {
      if (authOperation) return
      setAuthOperation(true)
      try {
        const payload: MfaVerifyPayload = {
          method,
          challenge_token: challengeToken || "",
          trust_device: trustDevice ?? false,
        }

        if (method === "totp" || method === "recovery_code") {
          payload.code = code
        } else if (method === "webauthn") {
          payload.webauthn_response = webauthnResponse as { [key: string]: unknown }
        }

        const response = await api.post<TokenWithProfileResponse>("/auth/mfa/verify", payload, {
          skipRateLimitQueue: true,
        } as ApiRequestConfig)
        const data = response.data

        if (isTokenWithProfileResponse(data)) {
          updateSessionSigningKey(extractSigningKey(data))
          incrementSessionEpoch() // RED-02 Wave 11: epoch bump after MFA login
          setUser(data.user)
          updatePendingMfa(null)
          if (data.user.spotify_connected) {
            window.dispatchEvent(new Event(SPOTIFY_REAUTH_EVENT))
          }

          // Recover push consent if browser still has subscription after storage was cleared
          recoverPushConsentFromBrowser()
            .then((recovered) => {
              if (recovered || hasPushConsent()) {
                softSyncPushSubscription().catch(() => {})
              }
            })
            .catch(() => {})

          void prefetchDashboardData(data.user)
        }
      } catch (error) {
        if (isAxiosError(error) && error.response?.status === 423) {
          const retryAfter = error.response.headers["retry-after"]
          const seconds = retryAfter ? parseInt(retryAfter, 10) : null
          const duration = formatLockoutDuration(seconds, t)
          const message = duration
            ? `${t("login.locked")} ${t("login.lockedRetry", { duration })}`
            : t("login.locked")
          throw new ChallengeLockedError(message, { refreshable: false })
        }
        throw error
      } finally {
        setAuthOperation(false)
      }
    },
    [
      authOperation,
      prefetchDashboardData,
      setAuthOperation,
      setUser,
      t,
      updatePendingMfa,
      updateSessionSigningKey,
    ]
  )

  const requireMfa = useCallback(async (): Promise<PendingMfaState | null> => {
    try {
      const response = await api.post<PendingMfaResponse>("/auth/mfa/step-up", null, {
        skipRateLimitQueue: true,
      } as ApiRequestConfig)
      if (response.status === 202) {
        const pendingState: PendingMfaState = { ...response.data, reason: "step-up" }
        updatePendingMfa(pendingState)
        return pendingState
      }
      return null
    } catch (error) {
      if (isAxiosError(error)) {
        if (error.response?.status === 401) {
          window.dispatchEvent(new Event(API_UNAUTHORIZED_EVENT))
          return null
        }
        if (error.response?.status === 409) {
          // Already fresh
          return null
        }
      }
      throw error
    }
  }, [updatePendingMfa])

  const refresh = useCallback(async () => {
    resetEtagCache()
    setAuthOperation(true)
    try {
      const profile = await fetchCurrentUser()
      setUser(profile as User)

      // Try to recover push consent if localStorage was cleared but browser still has subscription
      await recoverPushConsentFromBrowser()

      if (hasPushConsent()) {
        softSyncPushSubscription().catch(() => {
          /* ignore */
        })
      }
    } catch (error) {
      if (isAxiosError(error) && error.response?.status === 401) {
        handleUnauthorized()
      }
    } finally {
      setAuthOperation(false)
    }
  }, [handleUnauthorized, resetEtagCache, setAuthOperation, setUser])

  const loginWithPasskey = useCallback(
    async (email: string, trustDevice = false): Promise<void> => {
      if (authOperation) return
      setAuthOperation(true)
      try {
        const { startAuthentication } = await import("@simplewebauthn/browser")

        // 1. Get authentication options
        const optionsResponse = await api.post<WebAuthnAuthenticationOptionsOut>(
          "/auth/login/passkey/start",
          { email },
          { skipRateLimitQueue: true } as ApiRequestConfig
        )

        // 2. Start biometric authentication
        const authResponse = await startAuthentication({
          optionsJSON: optionsResponse.data.publicKey as unknown as Parameters<
            typeof startAuthentication
          >[0]["optionsJSON"],
        })

        // 3. Verify authentication response
        const response = await api.post<TokenWithProfileResponse>(
          "/auth/login/passkey/verify",
          {
            challenge_token: optionsResponse.data.challenge_token,
            webauthn_response: authResponse,
            trust_device: trustDevice,
          },
          { skipRateLimitQueue: true } as ApiRequestConfig
        )

        const data = response.data
        if (isTokenWithProfileResponse(data)) {
          updateSessionSigningKey(extractSigningKey(data))
          incrementSessionEpoch() // RED-02 Wave 11: epoch bump after passkey login
          setUser(data.user)
          updatePendingMfa(null)
          if (data.user.spotify_connected) {
            window.dispatchEvent(new Event(SPOTIFY_REAUTH_EVENT))
          }

          // Recover push consent if browser maintains subscription
          recoverPushConsentFromBrowser()
            .then((recovered) => {
              if (recovered || hasPushConsent()) {
                softSyncPushSubscription().catch(() => {})
              }
            })
            .catch(() => {})

          void prefetchDashboardData(data.user)
        }
      } catch (error) {
        if (isAxiosError(error) && error.response?.status === 423) {
          const retryAfter = error.response.headers["retry-after"]
          const seconds = retryAfter ? parseInt(retryAfter, 10) : null
          const duration = formatLockoutDuration(seconds, t)
          if (duration) {
            throw new Error(`${t("login.locked")} ${t("login.lockedRetry", { duration })}`)
          }
          throw new Error(t("login.locked"))
        }
        throw error
      } finally {
        setAuthOperation(false)
      }
    },
    [
      authOperation,
      prefetchDashboardData,
      setAuthOperation,
      setUser,
      t,
      updatePendingMfa,
      updateSessionSigningKey,
    ]
  )

  return {
    login,
    logout,
    submitMfaChallenge,
    requireMfa,
    loginWithPasskey,
    refresh,
  }
}
